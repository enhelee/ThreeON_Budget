import { esc } from "../util.js"
import { charImg } from "./characters.js"

// ─────────────────────────────────────────────────────────────
// 사이드바 — 모든 화면에서 항상 고정. 어느 화면에 있든 클릭 한 번으로 이동한다.
//
// 메뉴를 «데이터»로 두는 이유: 같은 목록을 메인 대시보드의 STAGE 카드가
// 다시 쓴다. 두 곳에 손으로 적어 두면 한쪽만 고쳐지는 날이 반드시 온다.
//
// 활성 표시(.nav-button-active)는 router.renderPage() 가 data-view 기준으로
// 매번 맞춰 주므로 여기서는 뼈대만 그린다.
// ─────────────────────────────────────────────────────────────

// 업무는 세 축(2026-11-03 팀장): ① 예산 실적 집계 → ② 표준화(정비등급별 표준금액) → ③ 중장기 예측
//   (표준금액 + 사람이 넣는 돌발·신규사업). 그룹 이름이 곧 축이다.
// sub = 바로 위 메뉴의 하위 메뉴(들여 쓴다).
export const MENU = [
  {view: "home", tag: "H", label: "메인"},
  {group: "① 예산 실적 집계"},
  // char = 그 화면을 맡은 캐릭터 — 메뉴 오른쪽 색 점(매칭이 청록·검토미 산호·예측이 보라)
  {view: "budget", tag: "1", label: "예산 계획", char: "mt"},
  {view: "collect", tag: "2", label: "실적 집계", char: "mt"},
  {view: "branches", tag: "3", label: "실적 분석", char: "gt"},
  {view: "detail", tag: "3-1", label: "지사 상세", char: "gt", sub: true},
  {view: "review", tag: "3-2", label: "검토 대기", char: "gt", sub: true},
  {view: "stats", tag: "4", label: "통계·내보내기", char: "gt"},
  {group: "② 표준화"},
  {view: "standard", tag: "5", label: "표준화", char: "yc"},
  {view: "stddetail", tag: "5-1", label: "표준화 세부", char: "yc", sub: true},
  {group: "③ 중장기 예측"},
  {view: "forecast", tag: "6", label: "중장기 예측", char: "yc"},
  {group: "관리"},
  {view: "settings", tag: "S", label: "설정"},
]

// 업무 흐름 4단계 — 메인 대시보드의 STAGE 카드. 사이드바의 어느 화면으로 가는지가 view.
// char = 카드에 서는 담당 캐릭터(한장이=계획본 한 장, 매칭이=전표 붙이기, 검토미=분석·검토, 예측이=전망)
export const STAGES = [
  {no: "01", view: "budget", title: "예산 계획", char: "hj",
   desc: "계획본(양식1)을 올려 그 해 예산을 DB에 등록합니다."},
  {no: "02", view: "collect", title: "실적 집계·매칭", char: "mt",
   desc: "ERP(zrfm2) 전표를 올려 계획 사업에 자동으로 붙입니다."},
  {no: "03", view: "branches", title: "실적 분석·표준화", char: "gt",
   desc: "지사별 집행률을 확인하고 재배정·수정으로 근거를 확정합니다."},
  // 사이드바와 같은 순서·표기(2026-10-27 사용자 지적: 04·검토 대기가 빠져 번호가 어긋났다)
  {no: "03 ✓", view: "review", title: "검토 대기", char: "gt",
   desc: "돈이 많이 걸린 사업부터 승인·사유·재배정으로 확인합니다."},
  {no: "04", view: "stats", title: "통계·내보내기", char: "gt",
   desc: "과목별 계획 대비 실적을 보고 재무팀 양식으로 내려받습니다."},
  {no: "05", view: "standard", title: "표준화", char: "yc",
   desc: "마감된 실적으로 지사 × 정비등급별 표준금액을 만듭니다."},
  {no: "06", view: "forecast", title: "중장기 전망", char: "yc",
   desc: "표준금액에 돌발·신규사업을 더해 10개년 소요를 전망합니다."},
]

function navButton(m) {
  return `<button class="nav-button${m.sub ? " nav-sub" : ""}" data-view="${m.view}" data-label="${esc(m.label)}"><span class="nav-tag grid h-7 w-7 shrink-0 place-items-center rounded-lg text-xs">${esc(m.tag)}</span><span class="nav-label">${esc(m.label)}</span></button>`
}

/** 메뉴 목록 → HTML. 하위 메뉴(sub)는 바로 위 메뉴 아래에 접어 두고(2026-11-03 grace: 스크롤 없이 짧게),
 *  위 메뉴 오른쪽 ▾ 를 누르면 펼친다(main.js data-sb-sub). 지금 화면이 하위 메뉴면 router 가 펼쳐 둔다. */
function navHtml(menu) {
  const out = []
  for (let i = 0; i < menu.length; i++) {
    const m = menu[i]
    if (m.group) { out.push(groupLabel(m.group)); continue }
    const subs = []
    while (menu[i + 1]?.sub) subs.push(menu[++i])
    if (!subs.length) { out.push(navButton(m)); continue }
    out.push(`<div class="nav-parent" data-parent="${m.view}">${navButton(m)}<button type="button" class="nav-sub-toggle" data-sb-sub="${m.view}" aria-expanded="false" aria-label="${esc(m.label)} 하위 메뉴 펼치기">▾</button></div>
      <div class="nav-subs" data-sub-of="${m.view}">${subs.map(navButton).join("")}</div>`)
  }
  return out.join("\n      ")
}

function groupLabel(text) {
  return `<p class="nav-group px-3 pb-1 pt-5 text-xs font-semibold tracking-wider text-tri">${esc(text)}</p>`
}

/** <aside id="sidebar"> 의 내용. 바깥 껍데기(위치·모바일 토글)는 index.html 이 갖는다.
 *  로고는 CI 매뉴얼의 한글 가로 A타입 시그니처(SVG, 비율 4.33:1 → 184px 폭에 43px). 바탕이 남색이라
 *  로고는 흰 판 위에 둔다(CI 색을 바꾸지 않기 위해). 그 아래 프로그램 이름 ONDO · by ThreeON.
 *  데스크톱은 번호만 남은 어두운 띠(76px)가 기본이고 마우스를 올리면 본문 위로 잠깐 펼쳐진다.
 *  «메뉴 펼치기»로 펼친 채 고정할 수 있다(main.js). 접힌 동안 로고·글자는 숨기고 캐릭터 머리만
 *  남긴다(custom.css .sb-collapsed) — 대신 상단 머리글에 같은 표지(renderHeaderBrand)가 나온다.
 *  표지를 누르면 어디서든 메인으로 간다(button[data-view]). */
export function setSubOpen(view, open) {
  document.querySelector(`#sidebar .nav-subs[data-sub-of="${view}"]`)?.classList.toggle("is-open", open)
  const t = document.querySelector(`#sidebar [data-sb-sub="${view}"]`)
  if (t) { t.setAttribute("aria-expanded", String(open)); t.setAttribute("aria-label", t.getAttribute("aria-label").replace(/펼치기|접기/, open ? "접기" : "펼치기")) }
}

/** 지금 화면이 하위 메뉴면 그 묶음을 펼친다(고른 메뉴가 접혀 안 보이는 일이 없게). */
export function openActiveSub(view) {
  const box = document.querySelector(`#sidebar .nav-subs [data-view="${view}"]`)?.closest(".nav-subs")
  if (box) setSubOpen(box.dataset.subOf, true)
}

export function renderSidebar() {
  return `
    <button type="button" class="sb-brand brand-link block w-full text-left" data-view="home" aria-label="메인으로 — 한국지역난방공사 ONDO by ThreeON">
      <span class="sb-full sb-ci"><img src="/assets/kdhc-signature-ko.svg" alt="한국지역난방공사" width="184" height="43" class="block h-auto w-full"></span>
      <span class="sb-name">${charImg("mt", "sidebar-mascot", {head: true})}<span class="sb-full sb-word ondo-word"><b>ON</b>DO</span><span class="sb-full sb-by">by ThreeON</span></span>
      <span class="sb-full sb-desc">예산·실적 분석 · 발전플랜트 유지보수</span>
    </button>

    <nav class="sb-nav mt-6 min-h-0 flex-1 space-y-1 overflow-y-auto overscroll-contain" aria-label="주요 메뉴">
      ${navHtml(MENU)}
    </nav>

    <button type="button" class="sb-fold" data-sb-fold aria-label="메뉴 접기"><span class="sb-fold__icon" aria-hidden="true">«</span><span class="sb-full sb-fold__text">메뉴 접기</span></button>`
}

/** 사이드바를 접었을 때 상단 머리글 왼쪽에 나오는 표지 — 72px 머리글에 맞춰 가로로 낮게.
 *  index.html 의 #headerBrand 에 부팅 때 1회 채운다. 펼친 동안은 사이드바에 있으므로 숨는다. */
export function renderHeaderBrand() {
  return `
    <img src="/assets/kdhc-signature-ko.svg" alt="" width="138" height="32" class="block h-8 w-auto">
    <span class="header-brand__text">
      <span class="text-[17px] font-bold leading-5 tracking-tight text-ink"><span class="header-brand__word ondo-word"><b>ON</b>DO</span></span>
    </span>`
}
