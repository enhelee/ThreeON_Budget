import { esc } from "../util.js"
import { charSvg } from "./characters.js"

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
  {view: "review", tag: "✓", label: "검토 큐"},
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
  // 사이드바와 같은 순서·표기(2026-10-27 사용자 지적: 04·검토 큐가 빠져 번호가 어긋났다)
  {no: "03 ✓", view: "review", title: "검토 큐",
   desc: "돈이 많이 걸린 사업부터 승인·사유·재배정으로 확인합니다."},
  {no: "04", view: "stats", title: "통계·내보내기",
   desc: "과목별 계획 대비 실적을 보고 재무팀 양식으로 내려받습니다."},
  {no: "05", view: "forecast", title: "중장기 전망",
   desc: "정비등급별 표준금액으로 10개년 소요를 전망합니다."},
]

function navButton(m) {
  return `<button class="nav-button" data-view="${m.view}" data-label="${esc(m.label)}"><span class="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-subtle text-xs text-sub">${esc(m.tag)}</span><span class="nav-label">${esc(m.label)}</span></button>`
}

function groupLabel(text) {
  return `<p class="nav-group px-3 pb-1 pt-5 text-xs font-semibold tracking-wider text-tri">${esc(text)}</p>`
}

/** <aside id="sidebar"> 의 내용. 바깥 껍데기(위치·모바일 토글)는 index.html 이 갖는다.
 *  로고는 CI 매뉴얼의 한글 가로 A타입 시그니처(SVG, 비율 4.33:1 → 184px 폭에 43px).
 *  데스크톱에서는 평소 번호만 남은 좁은 막대(76px)이고, 마우스를 올리거나 Tab 으로 들어오면
 *  본문 위로 펼쳐진다(main.js 사이드바 펼침). 본문은 밀리지 않는다.
 *  접힌 동안 로고·글자는 숨기고 캐릭터 머리만 남긴다(custom.css .sb-collapsed) — 대신 상단 머리글에
 *  같은 표지(renderHeaderBrand)가 나온다. 표지를 누르면 어디서든 메인으로 간다(button[data-view]). */
export function renderSidebar() {
  return `
    <button type="button" class="sb-brand brand-link block w-full px-2 text-left" data-view="home" aria-label="메인으로 — 한국지역난방공사 ThreeON">
      <img src="/assets/kdhc-signature-ko.svg" alt="한국지역난방공사" width="184" height="43" class="sb-full block h-auto w-[184px]">
      <span class="mt-2.5 flex items-center gap-1.5 text-[15px] font-bold tracking-tight text-ink"><span class="sb-full h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true"></span><span class="sb-full">ThreeON</span>${charSvg("mt", "sidebar-mascot", {head: true})}</span>
      <span class="sb-full mt-0.5 block text-[13px] leading-5 text-sub">예산·실적 분석 · 발전플랜트 유지보수</span>
    </button>

    <nav class="mt-8 flex-1 space-y-1" aria-label="주요 메뉴">
      ${MENU.map(m => m.group ? groupLabel(m.group) : navButton(m)).join("\n      ")}
    </nav>`
}

/** 사이드바를 접었을 때 상단 머리글 왼쪽에 나오는 표지 — 72px 머리글에 맞춰 가로로 낮게.
 *  index.html 의 #headerBrand 에 부팅 때 1회 채운다. 펼친 동안은 사이드바에 있으므로 숨는다. */
export function renderHeaderBrand() {
  return `
    <img src="/assets/kdhc-signature-ko.svg" alt="" width="138" height="32" class="block h-8 w-auto">
    <span class="header-brand__text">
      <span class="flex items-center gap-1 text-[14px] font-bold leading-5 tracking-tight text-ink"><span class="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden="true"></span>ThreeON${charSvg("mt", "header-brand__mascot", {head: true})}</span>
      <span class="block text-[12px] leading-4 text-sub">예산·실적 분석 · 발전플랜트 유지보수</span>
    </span>`
}
