import { $ } from "../util.js"
import { state } from "../state.js"
import { CHAR_IMG } from "../components/char_images.js"
import { NAMES } from "../components/characters.js"
import { startIntro, stopIntro } from "../components/gate_intro.js"

// ─────────────────────────────────────────────────────────────
// 로그인 게이트 — 비로그인 상태에서 보이는 유일한 화면.
//
// 구성은 «제목 + 간단한 설명 + 로그인» 세 덩어리로 끝낸다.
// 운영 수치(금액·건수·집행률)는 한 글자도 노출하지 않는다 —
// 그건 로그인 뒤 메인 화면의 몫이다.
//
// 2026-10-28 grace 결정(B안): 화면 전체가 어두운 장면(«ONDO» 인트로 → 캐릭터 셋이 받는 데이터 흐름,
// components/gate_intro.js), 오른쪽에 반투명 로그인 카드가 떠 있다 — 입력 칸은 처음부터 보이고 바로 쓸 수 있다.
// 소개는 장면이 하므로 카드는 로고·ONDO·입력 칸·입장만 둔다.
// 카드는 앱과 **같은 컴포넌트 클래스**(.panel · .control · .btn-primary · .section-help)를 그대로 쓰므로
// 나중에 그 스타일을 고치면 게이트도 같이 따라온다.
// ─────────────────────────────────────────────────────────────

// 장면의 캐릭터 — 처음 표정(a)과 마우스를 올렸을 때 표정(b). 2026-10-27 grace 결정.
const CAST = [
  {id: "mt", a: "wow", b: "full", line: "가 전표와 예산을 잇고,"},
  {id: "gt", a: "full", b: "happy", line: "가 차이를 살피고,"},
  {id: "yc", a: "think", b: "full", line: "가 다음 10년을 내다봅니다."},
]

function scene() {
  return `
  <section class="gate-scene" aria-label="ONDO 소개">
    <canvas class="gate-canvas" aria-hidden="true"></canvas>
    <div class="gate-copy">
      <p class="gate-kicker">ONDO · <span>예산의 온도를 읽다</span></p>
      <h2 class="gate-title font-hanan">우리 부서 예산,<br><em>지금 몇 도인가요?</em></h2>
      <p class="gate-mean"><b>ON</b> + 온<b>도</b> · 오늘의 예산 온도부터 10년 뒤 예보까지</p>
    </div>
    <div class="gate-cast">
      ${CAST.map(c => `<div class="gate-char gate-char--${c.id}">
        <img class="gate-char__a" src="${CHAR_IMG[c.id][c.a]}" alt="${NAMES[c.id]}">
        <img class="gate-char__b" src="${CHAR_IMG[c.id][c.b]}" alt="" aria-hidden="true">
      </div>`).join("")}
    </div>
    <ul class="gate-lines">
      ${CAST.map(c => `<li><b class="gate-name--${c.id}">${NAMES[c.id]}</b>${c.line}</li>`).join("")}
    </ul>
  </section>`
}

export function renderGate() {
  return `
  <div class="gate">
  ${scene()}
  <div class="gate-panel">
    <div class="panel gate-card w-full max-w-sm p-7 sm:p-9">

      <img src="/assets/kdhc-signature-ko.svg" alt="한국지역난방공사" width="184" height="43" class="block h-auto w-[184px]">
      <h1 class="mt-6 flex items-baseline gap-2 tracking-tight text-ink"><span class="ondo-word gate-word"><b>ON</b>DO</span><span class="text-xs font-medium text-tri">by ThreeON</span></h1>
      <p class="mt-1 text-[13px] text-sub">예산·실적 분석 · 발전플랜트 유지보수</p>

      <form id="gateForm" class="mt-7" autocomplete="off">
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
  startIntro(gate.querySelector(".gate-scene"))
  $("#gateMsg").textContent = msg || ""
  try {
    const saved = localStorage.getItem("budget_operator")
    if (saved && !$("#gateName").value) $("#gateName").value = saved
  } catch {}
  setTimeout(() => ($("#gateName").value ? $("#gatePw") : $("#gateName")).focus(), 50)
}

/** 게이트를 닫고 작업공간을 보인다. */
export function hideGate() {
  stopIntro()                                   // 로그인하면 장면 애니메이션을 완전히 멈춘다
  const pw = $("#gatePw")
  if (pw) pw.value = ""
  $("#gate").hidden = true
  $("#appShell").hidden = false
}

/** 로그인 후 돌아갈 주소. 401 로 튕기기 직전에 보던 «#/...» 를 기억해 둔다. */
export function rememberView(hash) {
  if (hash) state.returnHash = hash
}
