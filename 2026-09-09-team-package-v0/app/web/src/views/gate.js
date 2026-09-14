import { $ } from "../util.js"
import { state } from "../state.js"

// ─────────────────────────────────────────────────────────────
// 로그인 게이트 — 비로그인 상태에서 보이는 유일한 화면.
//
// 원칙: 실적 금액·연도·건수 같은 운영 수치를 한 글자도 노출하지 않는다.
//   제목 · 소개 · 4단계 · 로그인 폼이 전부다. 숫자가 필요한 요약은
//   로그인 뒤 메인 화면(#/home)의 몫이다.
//
// 색: 어두운 톤. 로그인 뒤 작업공간은 밝은 톤(slate-50)이라 색이 바뀌며
//   "들어왔다"는 전환감이 생긴다.
// ─────────────────────────────────────────────────────────────

const STAGES = [
  ["①", "예산 계획 수립", "지사별 계획을 양식1로 취합"],
  ["②", "실적 집계·매칭", "SAP 전표를 계획 사업에 자동 귀속"],
  ["③", "예산 표준화", "정비등급별 표준금액 산출"],
  ["④", "중장기 전망", "2026~2035년 소요 추정"],
]

function stageHtml() {
  return STAGES.map(([n, title, desc]) => `
    <li class="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
      <p class="text-xs font-semibold text-amber-500">${n} ${title}</p>
      <p class="mt-1 text-xs leading-5 text-slate-400">${desc}</p>
    </li>`).join("")
}

export function renderGate() {
  return `
  <div class="min-h-screen bg-slate-950 text-slate-100 lg:grid lg:grid-cols-[1.05fr_.95fr]">

    <section class="flex flex-col justify-center gap-9 px-6 py-14 sm:px-10 lg:px-14">
      <div>
        <p class="text-xs font-semibold uppercase tracking-[0.22em] text-amber-500">
          THREEON · 발전플랜트 유지보수 예산
        </p>
        <h1 class="mt-5 text-3xl font-black leading-[1.15] tracking-tight sm:text-4xl">
          계획에서 실적,<br>실적에서 <span class="text-amber-500">10개년 소요 전망</span>까지
        </h1>
        <p class="mt-6 max-w-xl text-sm leading-7 text-slate-400">
          지사 19곳이 엑셀로 올리는 예산계획과 SAP 실적 전표(zrfm2)를 자동으로 맞춰 보고,
          그 결과를 정비등급별 표준금액과 2026~2035년 예산 전망의 근거로 넘기는 팀 프로젝트입니다.
        </p>
      </div>
      <ol class="grid max-w-xl gap-2.5 sm:grid-cols-2">${stageHtml()}</ol>
    </section>

    <section class="flex items-center justify-center px-6 pb-16 lg:bg-white/[0.02] lg:py-14">
      <form id="gateForm" class="w-full max-w-sm rounded-2xl border border-white/10 bg-slate-900/70 p-7 shadow-2xl" autocomplete="off">
        <h2 class="text-lg font-bold text-white">팀 로그인</h2>
        <p class="mt-1.5 text-xs leading-5 text-slate-400">
          팀 공용 비밀번호와 <b class="text-slate-200">작업자 이름</b>을 입력하세요.
          이름은 재배정·수정·삭제 등 모든 변경 이력에 기록됩니다.
        </p>

        <label for="gateName" class="mt-6 block text-xs font-semibold text-slate-300">작업자 이름</label>
        <input id="gateName" maxlength="40" placeholder="예: 홍길동" required
               class="mt-1.5 w-full rounded-xl border border-white/15 bg-slate-950/60 px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-600">

        <label for="gatePw" class="mt-4 block text-xs font-semibold text-slate-300">팀 공용 비밀번호</label>
        <input id="gatePw" type="password" autocomplete="current-password" required
               class="mt-1.5 w-full rounded-xl border border-white/15 bg-slate-950/60 px-3 py-2.5 text-sm text-slate-100">

        <p id="gateMsg" class="mt-3 min-h-[1.1rem] text-xs font-medium text-red-400"></p>

        <button type="submit"
                class="mt-2 w-full rounded-xl bg-amber-500 px-4 py-2.5 text-sm font-bold text-slate-950 transition hover:bg-amber-400">
          입장
        </button>
      </form>
    </section>

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

/** 로그인 후 돌아갈 화면. 401 로 튕기기 직전에 보던 화면을 기억해 둔다. */
export function rememberView(view) {
  if (view) state.returnView = view
}
