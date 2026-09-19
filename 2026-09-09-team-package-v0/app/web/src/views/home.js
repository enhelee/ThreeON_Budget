import { rateBadge } from "../components/badges.js"
import { STAGES } from "../components/sidebar.js"
import { emptyState } from "../components/widgets.js"
import { state } from "../state.js"
import { esc, fmt, fmtRate } from "../util.js"

// ─────────────────────────────────────────────────────────────
// 메인 대시보드 (#/home)
//
// 위에서 아래로 다섯 덩어리다.
//   ① 헤더 스트립      제목·단계·기준일·리비전·단위         — 설명이므로 고정 문구
//   ② 현황 카드        계획/실적/집행률·미배정·DB·최근분석   — 전부 DB 실측치
//   ③ STAGE 01~04     카드가 곧 이동 버튼
//   ④ 이음새·다음 할 일  v2 연계 시각 + 지금 해야 할 것
//   ⑤ 다년도 패널      최근 개년 막대 + 연도별 요약표
//
// 원칙: 하드코딩하는 것은 설명 문구뿐이고, 숫자는 전부 DB에서 끌어온다.
// 메인을 열 때마다 현재 상태가 찍히므로 사내 이관 논의 때 이 화면 하나만 띄우면 된다.
//
// 자료가 없는 연도에서도 카드가 깨지지 않아야 한다 — 값이 없으면 "-" 로 둔다.
// ─────────────────────────────────────────────────────────────

const dash = '<span class="text-slate-400">-</span>'

function today() {
  const d = new Date()
  const p2 = n => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`
}

function curRow() {
  return (state.overview || []).find(r => String(r.year) === String(state.year))
}

function analyzedRows() {
  return (state.overview || []).filter(r => r["손익"] || r["자본"])
}

// 미배정(미매핑) 전표 — /api/status 에는 없고 /api/branches 의 가상 지사 행이 근거다.
function unmappedTotals() {
  const rows = state.branches || []
  return {
    n: rows.reduce((t, r) => t + (r.unmapped || 0), 0),
    amt: rows.reduce((t, r) => t + (r.unmappedAmt || 0), 0),
  }
}

// ── ① 헤더 스트립 ────────────────────────────────────────────

function stageFlow() {
  return STAGES.map((s, i) => `
    <span class="inline-flex items-center gap-1.5">
      <span class="grid h-5 w-5 place-items-center rounded-md bg-blue-50 text-[0.65rem] font-bold text-blue-700">${i + 1}</span>
      <span class="text-xs font-medium text-slate-600">${esc(s.title)}</span>
    </span>
    ${i < STAGES.length - 1 ? '<span class="text-slate-300" aria-hidden="true">→</span>' : ""}`).join("")
}

function metaItem(label, value) {
  return `<div><dt class="font-semibold text-slate-400">${esc(label)}</dt><dd class="mt-0.5 font-bold text-slate-700">${value}</dd></div>`
}

function headerStrip() {
  return `
  <section class="panel p-5 sm:p-6">
    <div class="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
      <div class="min-w-0">
        <p class="text-sm font-semibold text-blue-700">메인</p>
        <h2 class="mt-1 text-2xl font-bold tracking-tight text-slate-950">발전플랜트 유지보수 예산 — 계획에서 10개년 전망까지</h2>
        <p class="section-help max-w-30 leading-6">지사 19곳의 예산계획과 SAP 실적 전표를 자동으로 맞춰 보고, 그 결과를 정비등급별 표준금액과 2026~2035년 전망의 근거로 넘깁니다.</p>
      </div>
      <dl class="grid shrink-0 grid-cols-3 gap-x-6 gap-y-2 text-xs">
        ${metaItem("기준일", today())}
        ${metaItem("리비전", esc(state.health?.rev || "-"))}
        ${metaItem("단위", "화면 천원 · 연계 원")}
      </dl>
    </div>
    <div class="mt-5 flex flex-wrap items-center gap-x-2 gap-y-2 border-t border-slate-200 pt-4">
      ${stageFlow()}
    </div>
  </section>`
}

// ── ② 현황 카드 ──────────────────────────────────────────────

function card(title, badge, body) {
  return `<article class="metric-card">
    <div class="flex items-start justify-between gap-2">
      <p class="text-sm font-semibold text-slate-500">${esc(title)}</p>${badge}
    </div>
    ${body}
  </article>`
}

const badgeOk = t => `<span class="badge bg-emerald-50 text-emerald-700">${esc(t)}</span>`
const badgeMuted = t => `<span class="badge bg-slate-100 text-slate-500">${esc(t)}</span>`
const badgeWarn = t => `<span class="badge bg-amber-50 text-amber-700">${esc(t)}</span>`

function budgetCard(budget) {
  const s = curRow()?.[budget]
  const body = s
    ? `<p class="mt-4 text-2xl font-bold tracking-tight text-slate-950">${fmt(s.실적)} <span class="text-sm font-semibold text-slate-400">천원</span></p>
       <p class="mt-2 flex flex-wrap items-center gap-1.5 text-sm text-slate-500">계획 ${fmt(s.계획)} · 집행률 ${rateBadge(s.계획, s.실적)}</p>`
    : `<p class="mt-4 text-2xl font-bold tracking-tight">${dash}</p>
       <p class="mt-2 text-sm text-slate-500">이 연도의 ${esc(budget)}예산 분석 이력이 없습니다.</p>`
  return card(`${state.year}년 ${budget}예산`, s ? badgeOk("분석 완료") : badgeMuted("미실행"), body)
}

function prevYearCard() {
  const prev = analyzedRows().filter(r => String(r.year) !== String(state.year)).slice(-1)[0]
  if (!prev) {
    return card("직전 분석 연도", badgeMuted("없음"),
      `<p class="mt-4 text-2xl font-bold tracking-tight">${dash}</p>
       <p class="mt-2 text-sm text-slate-500">비교할 다른 연도의 분석 이력이 아직 없습니다.</p>`)
  }
  const p = (prev["손익"]?.계획 || 0) + (prev["자본"]?.계획 || 0)
  const a = (prev["손익"]?.실적 || 0) + (prev["자본"]?.실적 || 0)
  return card(`${prev.year}년 집계 (손익+자본)`, badgeOk("분석 완료"),
    `<p class="mt-4 text-2xl font-bold tracking-tight text-slate-950">${fmt(a)} <span class="text-sm font-semibold text-slate-400">천원</span></p>
     <p class="mt-2 flex flex-wrap items-center gap-1.5 text-sm text-slate-500">계획 ${fmt(p)} · 집행률 ${rateBadge(p, a)}
     <button class="ml-1 font-semibold text-blue-700 hover:text-blue-900" data-goyear="${esc(prev.year)}">이 연도로 전환 →</button></p>`)
}

function unmappedCard() {
  const {n, amt} = unmappedTotals()
  const locked = state.status ? !!state.status.locked : null
  const lockText = locked === null
    ? dash
    : locked
      ? '<b class="text-slate-700">마감됨</b> (수정 잠김)'
      : '<b class="text-amber-700">미마감</b> — 검토·수정 가능'
  return card("미배정 전표 · 연도 마감", n ? badgeWarn(`${n}건`) : badgeOk("없음"),
    `<p class="mt-4 text-2xl font-bold tracking-tight ${n ? "text-amber-700" : "text-slate-950"}">${fmt(n)} <span class="text-sm font-semibold text-slate-400">건</span></p>
     <p class="mt-2 text-sm text-slate-500">${n ? `금액 ${fmt(amt)}천원 · 종합표 미포함` : "모든 전표가 지사에 배정되었습니다."}</p>
     <p class="mt-1 text-sm text-slate-500">${esc(state.year)}년 ${lockText}</p>`)
}

function systemCard() {
  const h = state.health
  const db = !h ? dash : h.db === "postgresql" ? "PostgreSQL" : "SQLite"
  const auth = !h
    ? dash
    : h.auth
      ? '<b class="text-slate-700">세션 로그인</b> · 변경 이력 기록'
      : '<b class="text-slate-700">인증 꺼짐</b> (사내망 모드)'
  return card("시스템", h ? badgeOk("정상") : badgeMuted("확인 불가"),
    `<p class="mt-4 text-2xl font-bold tracking-tight text-slate-950">${db}</p>
     <p class="mt-2 text-sm text-slate-500">${auth}</p>
     <p class="mt-1 text-sm text-slate-500">리비전 ${esc(h?.rev || "-")}</p>`)
}

function lastRunCard() {
  const c = curRow()
  const stamps = ["손익", "자본"].map(b => c?.[b]?.실행일시).filter(Boolean)
  const at = stamps.length ? stamps.slice().sort().slice(-1)[0] : (state.pending?.analyzed_at || null)
  const n = state.pending?.total || 0
  return card("최근 분석 일시", n ? badgeWarn(`미반영 ${n}건`) : badgeMuted(`${state.year}년 기준`),
    `<p class="mt-4 text-xl font-bold tracking-tight text-slate-950">${at ? esc(at) : dash}</p>
     <p class="mt-2 text-sm text-slate-500">${n
       ? `이후 저장된 변경 ${n}건이 아직 결과에 반영되지 않았습니다.`
       : "저장된 변경이 모두 반영된 상태입니다."}</p>`)
}

function statusCards() {
  return `<section class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
    ${budgetCard("손익")}${budgetCard("자본")}${prevYearCard()}
    ${unmappedCard()}${systemCard()}${lastRunCard()}
  </section>`
}

// ── ③ STAGE 카드 ─────────────────────────────────────────────

function stageCards() {
  return `<section>
    <h3 class="section-title">업무 단계</h3>
    <p class="section-help">카드를 누르면 해당 화면으로 이동합니다. 왼쪽 메뉴와 같은 자리입니다.</p>
    <div class="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      ${STAGES.map(s => `
      <button type="button" data-view="${s.view}" class="metric-card text-left transition hover:border-blue-300 hover:shadow-md">
        <p class="text-xs font-bold tracking-widest text-blue-700">STAGE ${esc(s.no)}</p>
        <p class="mt-2 text-base font-bold text-slate-950">${esc(s.title)}</p>
        <p class="mt-1.5 text-xs leading-5 text-slate-500">${esc(s.desc)}</p>
        <span class="mt-4 inline-block text-xs font-semibold text-blue-700">열기 →</span>
      </button>`).join("")}
    </div>
  </section>`
}

// ── ④ 이음새 · 다음 할 일 ────────────────────────────────────

function bridgeBox() {
  const last = state.exportStatus?.last
  const thisYear = state.exportStatus?.files?.json || null
  return `
  <article class="panel p-5 sm:p-6">
    <h3 class="section-title">이음새 — 3·4단계는 이 앱 안에서</h3>
    <p class="section-help leading-6"><b class="text-slate-700">마감된 연도</b>의 분석 결과가 곧 5번 탭 표준화·중장기 전망의 입력입니다 — 파일을 옮길 필요가 없습니다. 아래 <b class="text-slate-700">팀연계_{연도}_사업실적연결.json</b> 은 외부 공유용으로 남아 있습니다(화면 금액 천원, 연계 파일 원 단위).</p>
    <button class="btn-secondary mt-3" data-view="forecast">중장기 예측 화면 열기 →</button>
    <dl class="mt-4 space-y-2 border-t border-slate-200 pt-4 text-sm">
      <div class="flex flex-wrap items-baseline gap-x-2">
        <dt class="font-semibold text-slate-500">마지막 내보내기</dt>
        <dd class="font-bold text-slate-800">${last ? `${esc(last.year)}년 · ${esc(last.at)}` : '<span class="text-amber-700">아직 내보낸 적 없습니다</span>'}</dd>
      </div>
      <div class="flex flex-wrap items-baseline gap-x-2">
        <dt class="font-semibold text-slate-500">${esc(state.year)}년 연계 JSON</dt>
        <dd class="font-bold text-slate-800">${thisYear ? esc(thisYear) : dash}</dd>
      </div>
    </dl>
    <button class="btn-secondary mt-4" data-view="stats">통계·내보내기 화면 열기</button>
  </article>`
}

/** 지금 해야 할 것. 조건에 맞는 것만, 급한 것부터. */
function nextActions() {
  const items = []
  const c = curRow()
  const {n: unmapped} = unmappedTotals()
  const pending = state.pending?.total || 0
  const learn = state.pending?.learn_pending || 0
  const locked = state.status ? !!state.status.locked : null

  if (!c) {
    items.push({tone: "warn", view: "budget",
                text: `${state.year}년 분석 이력이 없습니다 — 계획본(양식1)과 zrfm2 를 올린 뒤 상단 분석 실행을 누르세요.`})
  }
  if (pending) {
    items.push({tone: "warn", view: null,
                text: `저장된 변경 ${pending}건이 분석에 반영되지 않았습니다 — 상단 분석 반영을 누르세요.`})
  }
  if (unmapped) {
    items.push({tone: "warn", view: "detail",
                text: `미배정 전표 ${unmapped}건 — 3+ 상세에서 지사를 지정하면 종합표에 포함됩니다.`})
  }
  if (learn) {
    items.push({tone: "info", view: "settings",
                text: `학습 대기 ${learn}건 — 설정에서 학습을 실행하면 다음 분석의 자동 분류가 좋아집니다.`})
  }
  if (c && locked === false) {
    items.push({tone: "info", view: "settings",
                text: `${state.year}년 미마감 — 검토가 끝났으면 설정에서 마감해 수정을 잠그세요.`})
  }
  if (!items.length) {
    items.push({tone: "ok", view: "stats",
                text: "지금 처리할 일이 없습니다. 통계·내보내기에서 결과를 확인하거나 3·4단계로 넘기세요."})
  }

  const dot = {warn: "bg-amber-500", info: "bg-blue-500", ok: "bg-emerald-500"}
  return `
  <article class="panel p-5 sm:p-6">
    <h3 class="section-title">다음 할 일</h3>
    <p class="section-help">${esc(state.year)}년 기준으로 지금 필요한 작업입니다.</p>
    <ul class="mt-4 space-y-3 border-t border-slate-200 pt-4">
      ${items.slice(0, 4).map(it => `
      <li class="flex items-start gap-2.5 text-sm">
        <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full ${dot[it.tone]}"></span>
        <span class="text-slate-600">${esc(it.text)}
        ${it.view ? `<button class="ml-1 font-semibold text-blue-700 hover:text-blue-900" data-view="${it.view}">바로가기 →</button>` : ""}</span>
      </li>`).join("")}
    </ul>
  </article>`
}

// ── ⑤ 다년도 패널 ────────────────────────────────────────────

function multiYearPanels() {
  const analyzed = analyzedRows()
  if (!analyzed.length) {
    return emptyState("아직 분석 이력이 없습니다. ① 계획 업로드 → ② zrfm2 업로드 → 상단 분석 실행을 눌러주세요.")
  }
  const recent = analyzed.slice(-5)                 // 최근 최대 5개년(오름차순)
  const maxV = Math.max(1, ...recent.flatMap(r => ["손익", "자본"].flatMap(b =>
    r[b] ? [r[b].계획, r[b].실적] : [])))
  return `
  <section class="grid gap-6 xl:grid-cols-[1.05fr_.95fr]">
    <article class="panel p-5 sm:p-6">
      <div class="flex flex-wrap items-start justify-between gap-3"><div><h3 class="section-title">최근 ${recent.length}개년 실적 분석</h3><p class="section-help">파랑=계획 · 청록=실적 (손익+자본, 천원)</p></div><span class="badge bg-slate-100 text-slate-600">${recent.length}개 연도</span></div>
      <div class="mt-7 space-y-6">
        ${recent.map(r => {
          const p = (r["손익"]?.계획 || 0) + (r["자본"]?.계획 || 0)
          const a = (r["손익"]?.실적 || 0) + (r["자본"]?.실적 || 0)
          return `<div><div class="mb-2 flex items-end justify-between gap-3"><div><span class="font-bold text-slate-800 clickable" data-goyear="${r.year}">${r.year}</span><span class="ml-2 text-xs text-slate-500">집행률 ${fmtRate(p, a)}</span></div>
          <div class="text-right text-xs text-slate-500"><span class="font-semibold text-blue-700">${fmt(p)}</span><span class="mx-1">/</span><span class="font-semibold text-emerald-700">${fmt(a)}</span></div></div>
          <div class="space-y-1.5"><div class="h-3 overflow-hidden rounded-full bg-slate-100"><div class="h-full rounded-full bg-blue-500" style="width:${p / maxV * 100}%"></div></div>
          <div class="h-3 overflow-hidden rounded-full bg-slate-100"><div class="h-full rounded-full bg-emerald-500" style="width:${a / maxV * 100}%"></div></div></div></div>`
        }).join("")}
      </div>
      <p class="mt-6 flex items-center gap-2 text-xs text-slate-500"><span class="h-2 w-2 rounded-full bg-slate-300"></span>연도를 클릭하면 해당 연도로 전환됩니다. 자료가 없는 연도는 계산하지 않습니다.</p>
    </article>
    <article class="panel overflow-hidden">
      <div class="flex items-start justify-between gap-3 border-b border-slate-200 p-5 sm:p-6"><div><h3 class="section-title">연도별 요약</h3><p class="section-help">각 연도의 최신 분석 기준</p></div><button class="text-sm font-semibold text-blue-700 hover:text-blue-900" data-view="branches">전체 지사 →</button></div>
      <div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-4 py-3">연도</th><th class="px-4 py-3">구분</th><th class="px-4 py-3 text-right">계획</th><th class="px-4 py-3 text-right">실적</th><th class="px-4 py-3 text-right">집행률</th></tr></thead>
      <tbody class="divide-y divide-slate-100">${analyzed.slice().reverse().flatMap(r => ["손익", "자본"].filter(b => r[b]).map(b => `<tr class="hover:bg-slate-50 clickable" data-goyear="${r.year}"><td class="table-cell font-semibold text-slate-900">${r.year}</td><td class="table-cell">${b}</td><td class="table-cell text-right">${fmt(r[b].계획)}</td><td class="table-cell text-right">${fmt(r[b].실적)}</td><td class="table-cell text-right">${rateBadge(r[b].계획, r[b].실적)}</td></tr>`)).join("")}</tbody></table></div>
    </article>
  </section>`
}

export function renderHome() {
  return `
    <div class="space-y-6">
      ${headerStrip()}
      ${statusCards()}
      ${stageCards()}
      <section class="grid gap-6 xl:grid-cols-2">
        ${bridgeBox()}
        ${nextActions()}
      </section>
      ${multiYearPanels()}
    </div>`
}
