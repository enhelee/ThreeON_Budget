import { esc } from "../util.js"

// ─────────────────────────────────────────────────────────────
// 사이드바 — 모든 화면에서 항상 고정. 어느 화면에 있든 클릭 한 번으로 이동한다.
//
// 메뉴를 «데이터»로 두는 이유: 같은 목록을 메인 대시보드의 STAGE 카드가
// 다시 쓴다. 두 곳에 손으로 적어 두면 한쪽만 고쳐지는 날이 반드시 온다.
//
// 활성 표시(.nav-button-active)는 router.renderPage() 가 data-view 기준으로
// 매번 맞춰 주므로 여기서는 뼈대만 그린다.
// ─────────────────────────────────────────────────────────────

export const MENU = [
  {view: "home", tag: "H", label: "메인"},
  {group: "업무 단계"},
  {view: "budget", tag: "1", label: "예산 계획"},
  {view: "collect", tag: "2", label: "실적 집계"},
  {view: "branches", tag: "3", label: "실적 분석"},
  {view: "detail", tag: "3+", label: "실적분석(상세)"},
  {view: "stats", tag: "4", label: "통계·내보내기"},
  {view: "forecast", tag: "5", label: "중장기 예측"},
  {group: "관리"},
  {view: "settings", tag: "S", label: "설정"},
]

// 업무 흐름 4단계 — 메인 대시보드의 STAGE 카드. 사이드바의 어느 화면으로 가는지가 view.
export const STAGES = [
  {no: "01", view: "budget", title: "예산 계획",
   desc: "계획본(양식1)을 올려 그 해 예산을 DB에 등록합니다."},
  {no: "02", view: "collect", title: "실적 집계·매칭",
   desc: "ERP(zrfm2) 전표를 올려 계획 사업에 자동으로 붙입니다."},
  {no: "03", view: "branches", title: "실적 분석·표준화",
   desc: "지사별 집행률을 확인하고 재배정·수정으로 근거를 확정합니다."},
  {no: "04", view: "forecast", title: "중장기 전망",
   desc: "정비등급별 표준금액으로 10개년 소요를 전망합니다."},
]

function navButton(m) {
  return `<button class="nav-button" data-view="${m.view}"><span class="grid h-7 w-7 place-items-center rounded-lg bg-slate-100 text-xs text-slate-600">${esc(m.tag)}</span>${esc(m.label)}</button>`
}

function groupLabel(text) {
  return `<p class="px-3 pb-1 pt-5 text-xs font-semibold uppercase tracking-wider text-slate-400">${esc(text)}</p>`
}

/** <aside id="sidebar"> 의 내용. 바깥 껍데기(위치·모바일 토글)는 index.html 이 갖는다. */
export function renderSidebar() {
  return `
    <div class="flex items-center gap-3 px-2">
      <div class="grid h-11 w-11 place-items-center rounded-2xl bg-blue-600 text-white shadow-sm" aria-hidden="true">
        <svg viewBox="0 0 24 24" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 21h18M5 21V9l7-5 7 5v12M9 21v-7h6v7M8 10h.01M12 10h.01M16 10h.01"/></svg>
      </div>
      <div>
        <p class="font-bold text-slate-950">예산·실적 분석</p>
        <p class="text-xs text-slate-500">발전플랜트 유지보수</p>
      </div>
    </div>

    <nav class="mt-8 flex-1 space-y-1" aria-label="주요 메뉴">
      ${MENU.map(m => m.group ? groupLabel(m.group) : navButton(m)).join("\n      ")}
    </nav>

    <div class="rounded-2xl bg-blue-50 p-4">
      <div class="flex items-center gap-2 text-sm font-semibold text-blue-900">
        <span class="h-2 w-2 rounded-full bg-emerald-500"></span>사내망 · 백엔드 DB 저장
      </div>
      <p class="mt-2 text-xs leading-5 text-blue-700">업로드 자료는 서버 DB에만 저장되고 원본 파일은 남지 않습니다. 화면에는 분석 결과만 표출됩니다.</p>
    </div>`
}
