import { rateBadge } from "../components/badges.js"
import { openLockItems } from "../components/lockbanner.js"
import { STAGES } from "../components/sidebar.js"
import { emptyState } from "../components/widgets.js"
import { state } from "../state.js"
import { fvModel } from "./forecast_viz.js"
import { esc, fmt, fmtRate } from "../util.js"

// ─────────────────────────────────────────────────────────────
// 메인 대시보드 (#/home)
//
// 위에서 아래로 다섯 덩어리다.
//   ① 헤더 스트립      제목·단계·기준일·리비전·단위         — 설명이므로 고정 문구
//   ② 다년도 패널      최근 개년 막대 + 연도별 요약표
//   ③ 중장기 전망      전사 10개년 막대 + 상위 과목 — 표는 늦게 받아 따로 그린다(router.js)
//   ④ 현황 카드        계획/실적/집행률·미배정·DB·최근분석   — 전부 DB 실측치
//   ⑤ 다음 할 일 · STAGE 01~04
//   (2026-10-26 사용자 요청으로 다년도·전망을 맨 위로 올렸다)
//
// 원칙: 하드코딩하는 것은 설명 문구뿐이고, 숫자는 전부 DB에서 끌어온다.
// 메인을 열 때마다 현재 상태가 찍히므로 사내 이관 논의 때 이 화면 하나만 띄우면 된다.
//
// 자료가 없는 연도에서도 카드가 깨지지 않아야 한다 — 값이 없으면 "-" 로 둔다.
// ─────────────────────────────────────────────────────────────

const dash = '<span class="text-tri">-</span>'

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


function metaItem(label, value) {
  return `<div><dt class="font-semibold text-tri">${esc(label)}</dt><dd class="mt-0.5 font-bold text-ink">${value}</dd></div>`
}

function headerStrip() {
  return `
  <section class="panel p-5 sm:p-6">
    <div class="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
      <div class="min-w-0">
        <p class="text-sm font-semibold text-ink">메인</p>
        <h2 class="mt-1 font-hanan text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">발전플랜트 유지보수 예산 — 계획에서 10개년 전망까지</h2>
      </div>
      <dl class="grid shrink-0 grid-cols-3 gap-x-6 gap-y-2 text-xs">
        ${metaItem("기준일", today())}
        ${metaItem("리비전", esc(state.health?.rev || "-"))}
        ${metaItem("단위", "화면 천원 · 연계 원")}
      </dl>
    </div>
  </section>`
}

// ── ② 현황 카드 ──────────────────────────────────────────────

function card(title, badge, body) {
  return `<article class="metric-card h-full">
    <div class="flex items-start justify-between gap-2">
      <p class="text-sm font-semibold text-sub">${esc(title)}</p>${badge}
    </div>
    ${body}
  </article>`
}

const badgeOk = t => `<span class="badge bg-ok-bg text-ok">${esc(t)}</span>`
const badgeMuted = t => `<span class="badge bg-subtle text-sub">${esc(t)}</span>`
const badgeWarn = t => `<span class="badge bg-warn-bg text-warn">${esc(t)}</span>`

function budgetCard(budget) {
  const s = curRow()?.[budget]
  const body = s
    ? `<p class="mt-4 text-2xl font-bold tracking-tight text-ink">${fmt(s.실적)} <span class="text-sm font-semibold text-tri">천원</span></p>
       <p class="mt-2 flex flex-wrap items-center gap-1.5 text-sm text-sub">계획 ${fmt(s.계획)} · 집행률 ${rateBadge(s.계획, s.실적)}</p>`
    : `<p class="mt-4 text-2xl font-bold tracking-tight">${dash}</p>
       <p class="mt-2 text-sm text-sub">이 연도의 ${esc(budget)}예산 분석 이력이 없습니다.</p>`
  return card(`${state.year}년 ${budget}예산`, s ? badgeOk("분석 완료") : badgeMuted("미실행"), body)
}

function prevYearCard() {
  const prev = analyzedRows().filter(r => String(r.year) !== String(state.year)).slice(-1)[0]
  if (!prev) {
    return card("직전 분석 연도", badgeMuted("없음"),
      `<p class="mt-4 text-2xl font-bold tracking-tight">${dash}</p>
       <p class="mt-2 text-sm text-sub">비교할 다른 연도의 분석 이력이 아직 없습니다.</p>`)
  }
  const p = (prev["손익"]?.계획 || 0) + (prev["자본"]?.계획 || 0)
  const a = (prev["손익"]?.실적 || 0) + (prev["자본"]?.실적 || 0)
  return card(`${prev.year}년 집계 (손익+자본)`, badgeOk("분석 완료"),
    `<p class="mt-4 text-2xl font-bold tracking-tight text-ink">${fmt(a)} <span class="text-sm font-semibold text-tri">천원</span></p>
     <p class="mt-2 flex flex-wrap items-center gap-1.5 text-sm text-sub">계획 ${fmt(p)} · 집행률 ${rateBadge(p, a)}
     <button class="ml-1 font-semibold text-ink hover:text-brand" data-goyear="${esc(prev.year)}">이 연도로 전환 →</button></p>`)
}

function unmappedCard() {
  const {n, amt} = unmappedTotals()
  const locked = state.status ? !!state.status.locked : null
  const lockText = locked === null
    ? dash
    : locked
      ? '<b class="text-ink">마감됨</b> (수정 잠김)'
      : '<b class="text-warn">미마감</b> — 검토·수정 가능'
  return card("미배정 전표 · 연도 마감", n ? badgeWarn(`${n}건`) : badgeOk("없음"),
    `<p class="mt-4 text-2xl font-bold tracking-tight ${n ?"text-warn" : "text-ink"}">${fmt(n)} <span class="text-sm font-semibold text-tri">건</span></p>
     <p class="mt-2 text-sm text-sub">${n ? `금액 ${fmt(amt)}천원 · 종합표 미포함` : "모든 전표가 지사에 배정되었습니다."}</p>
     <p class="mt-1 text-sm text-sub">${esc(state.year)}년 ${lockText}</p>`)
}


function lastRunCard() {
  const c = curRow()
  const stamps = ["손익", "자본"].map(b => c?.[b]?.실행일시).filter(Boolean)
  const at = stamps.length ? stamps.slice().sort().slice(-1)[0] : (state.pending?.analyzed_at || null)
  const n = state.pending?.total || 0
  return card("최근 분석 일시", n ? badgeWarn(`미반영 ${n}건`) : badgeMuted(`${state.year}년 기준`),
    `<p class="mt-4 text-xl font-bold tracking-tight text-ink">${at ? esc(at) : dash}</p>
     <p class="mt-2 text-sm text-sub">${n
       ? `이후 저장된 변경 ${n}건이 아직 결과에 반영되지 않았습니다.`
       : "저장된 변경이 모두 반영된 상태입니다."}</p>`)
}

function statusCards() {
  // 6칸 격자: 윗줄 3장(2칸씩) · 아랫줄 2장(3칸씩) — 카드 5장이 빈칸 없이 찬다
  return `<section class="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
    <div class="xl:col-span-2">${budgetCard("손익")}</div><div class="xl:col-span-2">${budgetCard("자본")}</div><div class="xl:col-span-2">${prevYearCard()}</div>
    <div class="xl:col-span-3">${unmappedCard()}</div><div class="md:col-span-2 xl:col-span-3">${lastRunCard()}</div>
  </section>`
}

// ── ③ STAGE 카드 ─────────────────────────────────────────────

function stageCards() {
  return `<section>
    <h3 class="section-title">업무 단계</h3>
    <div class="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      ${STAGES.map(s => `
      <button type="button" data-view="${s.view}" class="metric-card text-left transition hover:border-ink">
        <p class="text-xs font-bold tracking-widest text-ink">STAGE ${esc(s.no)}</p>
        <p class="mt-2 text-base font-bold text-ink">${esc(s.title)}</p>
        <p class="mt-1.5 text-xs leading-5 text-sub">${esc(s.desc)}</p>
        <span class="mt-4 inline-block text-xs font-semibold text-ink">열기 →</span>
      </button>`).join("")}
    </div>
  </section>`
}

// ── ④ 다음 할 일 ────────────────────────────────────────────

/** 지금 해야 할 것. 조건에 맞는 것만, 급한 것부터. */
function nextActions() {
  const items = []
  const c = curRow()
  const {n: unmapped} = unmappedTotals()
  const pending = state.pending?.total || 0
  const learn = state.pending?.learn_pending || 0
  const locked = state.status ? !!state.status.locked : null

  items.push(...openLockItems())
  if (!c) {
    items.push({tone: "warn", view: "budget",
                text: `${state.year}년 분석 이력이 없습니다 — 계획본(양식1)과 zrfm2 를 올린 뒤 상단 분석 실행을 누르세요.`})
  }
  if (pending && state.yearLocked !== true) {      // 마감 연도엔 분석 반영을 권하지 않는다(423)
    items.push({tone: "warn", view: null,
                text: `저장된 변경 ${pending}건이 분석에 반영되지 않았습니다 — 상단 분석 반영을 누르세요.`})
  }
  const al = state.alerts?.summary;
  if (al?.high) {
    items.push({tone: "warn", view: "collect",
                text: `이상 알림 높음 ${al.high}건(전체 ${al.total}건) — 예산 초과·음수 실적·미매칭 비중을 실적 집계에서 확인하세요.`})
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

  const dot = {warn: "bg-warn", info: "bg-ink", ok: "bg-ok"}
  return `
  <article class="panel p-5 sm:p-6">
    <h3 class="section-title">다음 할 일</h3>
    <ul class="mt-4 grid gap-x-8 gap-y-3 border-t border-line pt-4 lg:grid-cols-2">
      ${items.slice(0, 4).map(it => `
      <li class="flex items-start gap-2.5 text-sm">
        <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full ${dot[it.tone]}"></span>
        <span class="text-sub">${esc(it.text)}
        ${it.view ? `<button class="ml-1 font-semibold text-ink hover:text-brand" data-view="${it.view}">바로가기 →</button>` : ""}</span>
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
      <div class="flex flex-wrap items-start justify-between gap-3"><div><h3 class="section-title">최근 ${recent.length}개년 실적 분석</h3><p class="section-help">검정=계획 · 초록=실적 (손익+자본, 천원)</p></div><span class="badge bg-subtle text-sub">${recent.length}개 연도</span></div>
      <div class="mt-7 space-y-6">
        ${recent.map(r => {
          const p = (r["손익"]?.계획 || 0) + (r["자본"]?.계획 || 0)
          const a = (r["손익"]?.실적 || 0) + (r["자본"]?.실적 || 0)
          return `<div><div class="mb-2 flex items-end justify-between gap-3"><div><span class="font-bold text-ink clickable" data-goyear="${r.year}">${r.year}</span><span class="ml-2 text-xs text-sub">집행률 ${fmtRate(p, a)}</span></div>
          <div class="text-right text-xs text-sub"><span class="font-semibold text-ink">${fmt(p)}</span><span class="mx-1">/</span><span class="font-semibold text-ok">${fmt(a)}</span></div></div>
          <div class="space-y-1.5"><div class="h-3 overflow-hidden rounded-full bg-subtle"><div class="h-full rounded-full bg-ink" style="width:${p / maxV * 100}%"></div></div>
          <div class="h-3 overflow-hidden rounded-full bg-subtle"><div class="h-full rounded-full bg-ok" style="width:${a / maxV * 100}%"></div></div></div></div>`
        }).join("")}
      </div>
      <p class="mt-6 flex items-center gap-2 text-xs text-sub"><span class="h-2 w-2 rounded-full bg-line-strong"></span>연도를 클릭하면 해당 연도로 전환됩니다. 자료가 없는 연도는 계산하지 않습니다.</p>
    </article>
    <article class="panel overflow-hidden">
      <div class="flex items-start justify-between gap-3 border-b border-line p-5 sm:p-6"><div><h3 class="section-title">연도별 요약</h3><p class="section-help">각 연도의 최신 분석 기준</p></div><button class="text-sm font-semibold text-ink hover:text-brand" data-view="branches">전체 지사 →</button></div>
      <div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-4 py-3">연도</th><th class="px-4 py-3">구분</th><th class="px-4 py-3 text-right">계획</th><th class="px-4 py-3 text-right">실적</th><th class="px-4 py-3 text-right">집행률</th></tr></thead>
      <tbody class="divide-y divide-line-subtle">${analyzed.slice().reverse().flatMap(r => ["손익", "자본"].filter(b => r[b]).map(b => `<tr class="hover:bg-subtle clickable" data-goyear="${r.year}"><td class="table-cell font-semibold text-ink">${r.year}</td><td class="table-cell">${b}</td><td class="table-cell text-right">${fmt(r[b].계획)}</td><td class="table-cell text-right">${fmt(r[b].실적)}</td><td class="table-cell text-right">${rateBadge(r[b].계획, r[b].실적)}</td></tr>`)).join("")}</tbody></table></div>
    </article>
  </section>`
}

// ── ③ 중장기 전망 패널 ──────────────────────────────────────
// 5번 탭과 같은 /api/forecast/table(전사 합계)을 쓴다. 막대를 누르면 5번 탭 «한눈에 보기» 그 해 구성으로.

const eok = v => { const x = v / 1e5; return Math.abs(x) >= 100 ? fmt(x) : x.toFixed(1) }

function forecastPanel() {
  const t = state.fc.table
  const head = (badge) => `<div class="flex flex-wrap items-start justify-between gap-3"><div><h3 class="section-title">중장기 소요 전망 ${t ? `${t.years[0]}~${t.years[t.years.length - 1]}` : "10개년"}</h3>
      <p class="section-help">전사 합계 · 단위 억원 · 기준연도 = 계획본 + 본사배분, 이후 = 표준금액 × 팩터</p></div>
      <div class="flex items-center gap-3">${badge}<button class="text-sm font-semibold text-ink hover:text-brand" data-homefc="">전망 자세히 →</button></div></div>`
  if (!t) return `<section class="panel p-5 sm:p-6">${head("")}<p class="mt-6 text-sm text-tri">${state.fc.homeErr ? "전망을 불러오지 못했습니다 — 5번 탭에서 확인하세요." : "전망을 불러오는 중…"}</p></section>`
  const m = fvModel(t, "", true)
  if (!m.years.length || !m.yearTot.some(v => v > 0)) return `<section class="panel p-5 sm:p-6">${head("")}<p class="mt-6 text-sm text-tri">아직 전망 금액이 없습니다 — 연도를 마감하면 5번 탭에서 전망을 만들 수 있습니다.</p></section>`
  const n = m.years.length, tot = m.yearTot.reduce((a, b) => a + b, 0)
  const cagr = m.yearTot[0] > 0 ? ((m.yearTot[n - 1] / m.yearTot[0]) ** (1 / (n - 1)) - 1) * 100 : null
  const peak = m.yearTot.indexOf(Math.max(...m.yearTot))
  // 10개년 막대 — 기준연도는 옅은 파랑(계획본), 이후는 파랑(전망). 막대 위에 억원, 마우스를 올리면 천원.
  const W = 760, H = 260, L = 8, R = 8, T = 30, B = 44, bw = (W - L - R) / n, max = Math.max(...m.yearTot) || 1
  let s = `<text x="${L}" y="12" font-size="12" font-weight="600" fill="#5D5D5D">(단위 억원)</text><line x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}" stroke="#C9C9C9"/>`
  m.yearTot.forEach((v, i) => {
    const h = v / max * (H - T - B), x = L + i * bw + bw * .2, w = bw * .6, y = H - B - h
    s += `<g class="clickable" data-homefc="${m.years[i]}"><title>전사 ${m.years[i]}년 ${fmt(v)}천원${i ? ` · 전년 대비 ${((v / m.yearTot[i - 1] - 1) * 100).toFixed(1)}%` : " · 기준연도"} (클릭: 그 해 과목 구성)</title>
      <rect x="${L + i * bw}" y="${T - 22}" width="${bw}" height="${H - T - B + 22}" fill="transparent"/>
      ${h > 0 ? `<path d="M${x},${H - B} V${y + Math.min(4, h)} q0,-4 4,-4 h${w - 8} q4,0 4,4 V${H - B} Z" fill="${i === 0 ? "#9ec5f4" : i === peak ? "#184f95" : "#256abf"}"/>` : ""}
      <text x="${x + w / 2}" y="${y - 7}" text-anchor="middle" font-size="12" font-weight="700" fill="#0D0D0D">${eok(v)}</text>
      <text x="${x + w / 2}" y="${H - B + 18}" text-anchor="middle" font-size="12" font-weight="600" fill="#5D5D5D">${m.years[i]}</text>
      ${i === 0 ? `<text x="${x + w / 2}" y="${H - B + 33}" text-anchor="middle" font-size="10" fill="#767676">기준연도</text>` : ""}</g>`
  })
  const top = m.acctRows.slice(0, 5), mx = top[0]?.total || 1
  const kpi = (k, v, sub) => `<div class="rounded-control bg-subtle px-4 py-3"><p class="text-xs font-semibold text-sub">${k}</p><p class="mt-1 text-lg font-bold text-ink">${v}</p><p class="text-xs text-tri">${sub}</p></div>`
  return `
  <section class="panel p-5 sm:p-6">
    ${head(`<span class="badge bg-subtle text-sub">기준 ${esc(t.base_year)}년</span>`)}
    <div class="mt-5 grid gap-3 sm:grid-cols-3">
      ${kpi("10년 누계", `${eok(tot)}<span class="ml-1 text-xs font-semibold text-tri">억원</span>`, `${fmt(tot)}천원`)}
      ${kpi("연평균 증감", cagr === null ? "-" : `${cagr >= 0 ? "+" : ""}${cagr.toFixed(1)}%`, `${m.years[0]} ${eok(m.yearTot[0])}억 → ${m.years[n - 1]} ${eok(m.yearTot[n - 1])}억`)}
      ${kpi("가장 많은 해", `${m.years[peak]}년`, `${eok(m.yearTot[peak])}억원`)}
    </div>
    <div class="mt-6 grid gap-6 xl:grid-cols-[1.6fr_1fr]">
      <div class="overflow-x-auto"><svg viewBox="0 0 ${W} ${H}" class="w-full min-w-[520px]" role="img" aria-label="전사 중장기 10개년 소요 전망">${s}</svg>
        <p class="flex items-center gap-2 text-xs text-sub"><span class="h-2 w-2 rounded-full bg-line-strong"></span>막대를 누르면 5번 탭에서 그 해 과목 구성을 봅니다. 옅은 막대 = 기준연도(계획본), 짙은 막대 = 가장 많은 해.</p></div>
      <div><h4 class="text-sm font-bold text-ink">10년 누계 상위 과목 <span class="font-semibold text-sub">(억원)</span></h4>
        <div class="mt-4 space-y-4">${top.map(r => `<div><div class="mb-1.5 flex items-end justify-between gap-3"><span class="truncate text-sm font-semibold text-ink">${esc(r.key)}</span><span class="shrink-0 text-xs text-sub"><span class="font-semibold text-ink">${eok(r.total)}억</span> · ${(r.total / tot * 100).toFixed(0)}%</span></div>
          <div class="h-3 overflow-hidden rounded-full bg-subtle"><div class="h-full rounded-full" style="width:${r.total / mx * 100}%;background:#256abf"></div></div></div>`).join("")}</div>
        ${m.acctRows.length > 5 ? `<p class="mt-4 text-xs text-tri">외 ${m.acctRows.length - 5}개 과목 ${eok(m.acctRows.slice(5).reduce((a, r) => a + r.total, 0))}억원</p>` : ""}</div>
    </div>
  </section>`
}

export function renderHome() {
  return `
    <div class="space-y-6">
      ${headerStrip()}
      ${multiYearPanels()}
      ${forecastPanel()}
      ${statusCards()}
      ${nextActions()}
      ${stageCards()}
    </div>`
}
