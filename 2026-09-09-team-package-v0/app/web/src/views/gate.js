import { $ } from "../util.js"
import { state } from "../state.js"

// ─────────────────────────────────────────────────────────────
// 로그인 게이트 — 비로그인 상태에서 보이는 유일한 화면.
//
// 구성은 «제목 + 간단한 설명 + 로그인» 세 덩어리로 끝낸다.
// 운영 수치(금액·건수·집행률)는 한 글자도 노출하지 않는다 —
// 그건 로그인 뒤 메인 화면의 몫이다.
//
// 디자인은 작업공간(/app/)과 같은 컨셉으로 맞춘다. 배경 slate-50,
// 흰 panel 카드, 파란 강조. 실제로 앱과 **같은 컴포넌트 클래스**
// (.panel · .control · .btn-primary · .section-help)를 그대로 쓰므로
// 나중에 그 스타일을 고치면 게이트도 같이 따라온다.
// ─────────────────────────────────────────────────────────────

const STAGES = ["예산 계획", "실적 집계·매칭", "예산 표준화", "중장기 전망"]

function stageFlow() {
  return STAGES.map((s, i) => `
    <span class="inline-flex items-center gap-1.5">
      <span class="grid h-5 w-5 place-items-center rounded-md bg-subtle text-[0.65rem] font-bold text-ink">${i + 1}</span>
      <span class="text-xs font-medium text-sub">${s}</span>
    </span>
    ${i < STAGES.length - 1 ? '<span class="text-tri" aria-hidden="true">→</span>' : ""}`).join("")
}

export function renderGate() {
  return `
  <div class="flex min-h-screen items-center justify-center bg-base px-4 py-10">
    <div class="panel w-full max-w-md p-7 sm:p-9">

      <img src="/assets/kdhc-signature-ko.svg" alt="한국지역난방공사" width="184" height="43" class="block h-auto w-[184px]">
      <p class="mt-3 text-[13px] text-sub">예산·실적 분석 · 발전플랜트 유지보수</p>

      <h1 class="mt-7 font-hanan text-[28px] font-semibold leading-snug tracking-tight text-ink">
        계획에서 실적,<br>실적에서 10개년 소요 전망까지
      </h1>
      <p class="section-help leading-6">
        지사 19곳의 예산계획과 SAP 실적 전표를 자동으로 맞춰 보고,
        그 결과를 정비등급별 표준금액과 2026~2035년 예산 전망의 근거로 넘깁니다.
      </p>

      <div class="mt-5 flex flex-wrap items-center gap-x-2 gap-y-2 border-y border-line py-3">
        ${stageFlow()}
      </div>

      <form id="gateForm" class="mt-6" autocomplete="off">
        <label for="gateName" class="block text-xs font-semibold text-ink">작업자 이름</label>
        <input id="gateName" class="control mt-1.5 w-full" maxlength="40" placeholder="예: 홍길동" required>

        <label for="gatePw" class="mt-4 block text-xs font-semibold text-ink">팀 공용 비밀번호</label>
        <input id="gatePw" class="control mt-1.5 w-full" type="password" autocomplete="current-password" required>

        <p id="gateMsg" class="mt-3 min-h-[1.1rem] text-xs font-medium text-err"></p>

        <button type="submit" class="btn-primary w-full">입장</button>

        <p class="mt-4 text-xs leading-5 text-sub">
          작업자 이름은 재배정·수정·삭제 등 <b class="text-ink">모든 변경 이력에 기록</b>됩니다. 실명을 입력하세요.
        </p>
      </form>

    </div>
  </div>`
}

/** 게이트를 띄우고 앱 셸을 숨긴다. msg 가 있으면 사유를 표시한다. */
export function showGate(msg) {
  const gate = $("#gate")
  if (!gate.innerHTML) gate.innerHTML = renderGate()
  // ⚠ Tailwind 의 .hidden 을 쓰면 안 된다 — appShell 의 lg:flex 가 미디어쿼리라
  //   나중에 나와서 데스크톱에서 .hidden 을 이긴다(로그인 창 CSS 버그와 같은 종류).
  //   [hidden] 속성 + custom.css 의 !important 규칙으로 확실히 숨긴다.
  gate.hidden = false
  $("#appShell").hidden = true
  $("#gateMsg").textContent = msg || ""
  try {
    const saved = localStorage.getItem("budget_operator")
    if (saved && !$("#gateName").value) $("#gateName").value = saved
  } catch {}
  setTimeout(() => ($("#gateName").value ? $("#gatePw") : $("#gateName")).focus(), 50)
}

/** 게이트를 닫고 작업공간을 보인다. */
export function hideGate() {
  const pw = $("#gatePw")
  if (pw) pw.value = ""
  $("#gate").hidden = true
  $("#appShell").hidden = false
}

/** 로그인 후 돌아갈 주소. 401 로 튕기기 직전에 보던 «#/...» 를 기억해 둔다. */
export function rememberView(hash) {
  if (hash) state.returnHash = hash
}
