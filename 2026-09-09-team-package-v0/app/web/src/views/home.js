import { rateBadge } from "../components/badges.js"
import { CHAR_IMG } from "../components/char_images.js"
import { NAMES } from "../components/characters.js"
import { openLockItems } from "../components/lockbanner.js"
import { STAGES } from "../components/sidebar.js"
import { emptyState } from "../components/widgets.js"
import { state } from "../state.js"
import { fvModel } from "./forecast_viz.js"
import { esc, fmt, fmtRate, today, todayLong } from "../util.js"

// ─────────────────────────────────────────────────────────────
// 메인 대시보드 (#/home)
//
// 위에서 아래로 다섯 덩어리다.
//   ① 헤더 스트립      제목·오늘 날짜                       — 설명이므로 고정 문구
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
// 기준일·단위 칸은 뺐다(2026-10-27 사용자 요청) — 기준일은 설정 › 데이터 «시스템 정보»로, 여기엔 오늘 날짜만.
// 남색 배너 + 오른쪽 캐릭터 셋(2026-10-27 grace 요청 — 남색 사이드바와 흰 본문이 따로 놀지 않게).
// 숫자는 넣지 않는다 — 현황은 아래 카드의 몫. 캐릭터 그림은 챗봇과 같은 한 벌(components/char_images.js).
// 아래 알약은 업무 흐름 4단계 — 누르면 그 화면으로 간다(STAGE 카드와 같은 STAGES 에서 뽑는다).

const HERO_STEPS = ["budget", "collect", "branches", "forecast"]

function headerStrip() {
  const steps = STAGES.filter(s => HERO_STEPS.includes(s.view))
  return `
  <section class="home-hero">
    <div class="home-hero__text">
      <p class="home-hero__kicker">ONDO · <span>예산의 온도를 읽다</span></p>
      <h2 class="home-hero__title font-hanan">발전플랜트 유지보수 예산,<br><em>계획에서 10개년 전망까지</em></h2>
      <p class="home-hero__desc">예산 계획과 ERP 전표를 자동으로 맞춰 보고, 차이를 살피고, 정비등급별 표준금액으로 10년 뒤를 예보합니다.</p>
      <div class="home-hero__gauge" aria-hidden="true"><i></i><span><em>계획</em><em>집행</em><em>과열</em></span></div>
      <p class="home-hero__date">오늘 <time datetime="${today()}">${todayLong()}</time></p>
      <div class="home-hero__steps">${steps.map(s => `<button type="button" data-view="${s.view}"><b>${esc(s.no)}</b>${esc(s.title)}</button>`).join("")}</div>
    </div>
    <div class="home-hero__cast">
      ${["mt", "gt", "yc"].map(id => `<img class="home-hero__char home-hero__char--${id}" src="${CHAR_IMG[id].full}" alt="${NAMES[id]}" width="160" height="160">`).join("")}
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
       <p class="mt-2 flex flex-wrap items-center gap-1.5 text-sm text-sub">계획 ${fmt(s.계획)} 천원 · 집행률 ${rateBadge(s.계획, s.실적)}</p>`
    : `<p class="mt-4 text-2xl font-bold tracking-tight">${dash}</p>
       <p class="mt-2 text-sm text-sub">이 연도의 ${esc(budget)}예산 분석 이력이 없습니다.</p>`
  const open = state.homeAcct === budget
  const more = s ? `<button type="button" class="home-acct-btn" data-homeacct="${budget}" aria-expanded="${open}">예산과목별 보기 <span aria-hidden="true">${open ? "▴" : "▾"}</span></button>` : ""
  return card(`${state.year}년 ${budget}예산`, s ? badgeOk("분석 완료") : badgeMuted("미실행"), body + more)
}

// 손익·자본 카드를 누르면 아래로 예산과목별 계획·실적·집행률(팀장 검토의견). /api/stats 는 main.js 가 처음 펼칠 때 받는다.
function acctPanel() {
  const b = state.homeAcct
  if (!b) return ""
  const st = state.stats && String(state.stats._year) === String(state.year) ? state.stats : null
  const items = (st?.budgets?.[b]?.items || []).filter(r => r.계획 || r.실적)
  const mx = Math.max(1, ...items.map(r => Math.max(r.계획 || 0, r.실적 || 0)))
  const body = !st ? `<p class="text-sm text-tri">불러오는 중…</p>`
    : !items.length ? `<p class="text-sm text-tri">이 연도의 ${esc(b)}예산 과목 자료가 없습니다.</p>`
    : `<div class="acct-list yr-one--${BT_KEY[b]}">${items.map(r => `<div class="acct-row"><span class="acct-row__k">${esc(r.예산과목)}</span>
        <div class="yr-one__track"><div class="yr-bar yr-bar--plan yr-one__plan" style="width:${(r.계획 || 0) / mx * 100}%"></div><div class="yr-bar yr-bar--act yr-one__act" style="width:${(r.실적 || 0) / mx * 100}%"></div></div>
        <span class="acct-row__v"><b>${fmt(r.실적 || 0)}</b> / ${fmt(r.계획 || 0)}</span><span>${rateBadge(r.계획, r.실적)}</span></div>`).join("")}</div>`
  return `<section class="panel p-5 sm:p-6 acct-panel"><div class="mb-4 flex items-center justify-between gap-3"><h3 class="section-title">${esc(state.year)}년 ${esc(b)}예산 · 예산과목별</h3>
    <div class="flex items-center gap-3"><span class="text-xs font-semibold text-tri">실적 / 계획 · 단위: 천원</span><button type="button" class="text-sm font-semibold text-sub hover:text-ink" data-homeacct="${esc(b)}">접기 ▴</button></div></div>${body}</section>`
}

// 연도 고르기 카드(팀장 검토의견) — 분석한 연도 버튼을 바로 눌러 전환. 값은 지금 연도의 손익+자본 합계.
function yearPickCard() {
  const years = analyzedRows().map(r => String(r.year))
  const row = curRow(), c = row && (row["손익"] || row["자본"]) ? row : null
  const p = c ? bv(c, "합계", "계획") : 0, a = c ? bv(c, "합계", "실적") : 0
  return card(`${state.year}년 합계 (손익+자본)`, c ? badgeOk("분석 완료") : badgeMuted("미실행"),
    `<p class="mt-4 text-2xl font-bold tracking-tight text-ink">${c ? `${fmt(a)} <span class="text-sm font-semibold text-tri">천원</span>` : dash}</p>
     <p class="mt-2 flex flex-wrap items-center gap-1.5 text-sm text-sub">${c ? `계획 ${fmt(p)} 천원 · 집행률 ${rateBadge(p, a)}` : "이 연도의 분석 이력이 없습니다."}</p>
     <div class="year-pick" role="group" aria-label="연도 고르기">${years.map(y => `<button type="button" data-goyear="${esc(y)}" aria-pressed="${y === String(state.year)}">${esc(y)}</button>`).join("")}</div>`)
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
     <p class="mt-2 text-sm text-sub">${n ? `금액 ${fmt(amt)} 천원 · 종합표 미포함` : "모든 전표가 지사에 배정되었습니다."}</p>
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
    <div class="xl:col-span-2">${budgetCard("손익")}</div><div class="xl:col-span-2">${budgetCard("자본")}</div><div class="xl:col-span-2">${yearPickCard()}</div>
    ${state.homeAcct ? `<div class="md:col-span-2 xl:col-span-6">${acctPanel()}</div>` : ""}
    <div class="xl:col-span-3">${unmappedCard()}</div><div class="md:col-span-2 xl:col-span-3">${lastRunCard()}</div>
  </section>`
}

// ── ③ STAGE 카드 ─────────────────────────────────────────────

function stageCards() {
  return `<section>
    <h3 class="section-title">업무 단계</h3>
    <div class="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      ${STAGES.map(s => `
      <button type="button" data-view="${s.view}" class="metric-card stage-card stage-card--${s.char} text-left transition hover:border-ink">
        <p class="stage-card__no text-xs font-bold tracking-widest">STAGE ${esc(s.no)}</p>
        <p class="mt-2 text-base font-bold text-ink">${esc(s.title)}</p>
        <p class="stage-card__desc mt-1.5 text-xs leading-5 text-sub">${esc(s.desc)}</p>
        <span class="mt-4 inline-block text-xs font-semibold text-ink">열기 →</span>
        <img class="stage-card__char" src="${CHAR_IMG[s.char].full}" alt="" width="72" height="72" loading="lazy">
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
  // 검토 큐(2026-10-27) — 이상 알림·차이 사유·저확신 귀속을 «돈이 걸린 순» 한 줄로 묶는다.
  //   «171건·1,405건»처럼 건수만 늘어놓으면 어디서 시작할지 모르고 미완성처럼 읽힌다.
  const rq = state.rqBrief?.analyzed ? state.rqBrief.summary : null
  const rqWaiting = state.rqBrief === null          // 화면을 먼저 그리고 뒤에서 받는 중
  if (rqWaiting) {
    items.push({tone: "info", view: "review", text: "검토 큐 확인 중…"})
  } else if (rq?.open) {
    items.push({tone: "warn", view: "review",
                text: `검토 큐 — 남은 ${fmt(rq.open)}건 · ${fmt(rq.amount_open)} 천원 (처리 ${fmt(rq.resolved)}건)`})
  } else if (rq?.total) {
    items.push({tone: "info", view: "review", text: `검토 큐 ${fmt(rq.total)}건을 모두 처리했습니다.`})
  }
  // 검토 큐를 못 받았을 때만 예전 두 줄(이상 알림은 실적 집계, 차이 사유는 3+)로 알린다.
  const al = rq || rqWaiting ? null : state.alerts?.summary;
  if (al?.high) {
    items.push({tone: "warn", view: "collect",
                text: `이상 알림 높음 ${al.high}건(전체 ${al.total}건) — 예산 초과·과다 귀속·미매칭 비중을 실적 집계에서 확인하세요.`})
  }
  // 차이 사유(집행률 ±20%p) — 마감 뒤에도 입력할 수 있고 보고 때 쓰인다.
  const varNeed = rq || rqWaiting ? 0 : (state.branches || []).reduce((a, r) => a + Math.max(0, (r.variance || 0) - (r.varianceNoted || 0)), 0)
  if (varNeed) {
    items.push({tone: "info", view: "detail",
                text: `차이 사유 미입력 ${varNeed}건(집행률 ±20%p 사업) — 3+ 상세에서 «사유 입력»으로 적어 두세요.`})
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
        ${it.view ? `<button class="ml-1 font-semibold text-ink hover:text-mint-ink" data-view="${it.view}">바로가기 →</button>` : ""}</span>
      </li>`).join("")}
    </ul>
  </article>`
}

// ── ⑤ 다년도 패널 ────────────────────────────────────────────

// 팀장 검토의견(2026-10-28): 계획·실적을 한 막대에(옅은 계획 막대 위에 실적 막대), 손익·자본·합계를 따로.
// 단위는 억원(막대에 마우스를 올리면 천원). 기준(최댓값)은 모든 연도의 합계 계획·실적 중 최댓값 하나 — 길이를 서로 비교할 수 있게.
const BT = ["손익", "자본", "합계"]
const BT_KEY = {손익: "pl", 자본: "cap", 합계: "sum"}   // 색(10/28 grace 확정 팔레트, custom.css --chart-*): 손익 파랑 · 자본 회청 · 합계 산호(옅은 막대 = 계획, 진한 막대 = 실적)
const bv = (r, b, k) => b === "합계" ? (r["손익"]?.[k] || 0) + (r["자본"]?.[k] || 0) : (r[b]?.[k] || 0)
const eokN = v => fmt(Math.round(v / 1e5))

function multiYearPanels() {
  const analyzed = analyzedRows()
  if (!analyzed.length) {
    return emptyState("아직 분석 이력이 없습니다. ① 계획 업로드 → ② zrfm2 업로드 → 상단 분석 실행을 눌러주세요.")
  }
  const recent = analyzed.slice(-3)                 // 최근 3개년(오름차순) — 오른쪽 비교표와 같은 연도
  const maxV = Math.max(1, ...recent.flatMap(r => [bv(r, "합계", "계획"), bv(r, "합계", "실적")]))
  const bar = (r, b) => {
    const p = bv(r, b, "계획"), a = bv(r, b, "실적")
    return `<div class="yr-one yr-one--${BT_KEY[b]}"><span class="yr-one__k">${b}</span>
      <div class="yr-one__track" title="${b} 계획 ${fmt(p)} 천원 · 실적 ${fmt(a)} 천원 · 집행률 ${fmtRate(p, a)}">
        <div class="yr-bar yr-bar--plan yr-one__plan" style="width:${p / maxV * 100}%"></div>
        <div class="yr-bar yr-bar--act yr-one__act" style="width:${a / maxV * 100}%"></div></div>
      <span class="yr-one__v"><b>${eokN(a)}</b> / ${eokN(p)}</span><span class="yr-one__r">${rateBadge(p, a)}</span></div>`
  }
  return `
  <section class="grid gap-6 xl:grid-cols-[1fr_1fr]">
    <article class="panel p-5 sm:p-6">
      <div class="flex flex-wrap items-start justify-between gap-3"><div><h3 class="section-title">최근 ${recent.length}개년 실적 분석</h3>
        <p class="section-help flex flex-wrap items-center gap-x-3 gap-y-1">${BT.map(b => `<span class="inline-flex items-center gap-1.5"><span class="yr-key yr-key--${BT_KEY[b]}"></span>${b}</span>`).join("")}<span>옅은 막대 계획 · 진한 막대 실적</span></p></div>
        <span class="text-xs font-semibold text-tri">단위: 억원</span></div>
      <div class="mt-6 space-y-5">
        ${recent.slice().reverse().map(r => `<div><p class="mb-2"><span class="font-bold text-ink clickable" data-goyear="${r.year}">${r.year}</span></p>
          <div class="space-y-1.5">${BT.map(b => bar(r, b)).join("")}</div></div>`).join("")}
      </div>
      <p class="mt-5 flex items-center gap-2 text-xs text-sub"><span class="h-2 w-2 rounded-full bg-line-strong"></span>연도를 클릭하면 해당 연도로 전환됩니다.</p>
    </article>
    ${summaryTable(recent)}
  </section>`
}

// 연도별 요약 = «유지보수예산 3개년 실적비교» 모양(팀장 검토의견): 연도를 가로로, 각 연도 아래 계획·실적, 줄마다 실적률.
function summaryTable(recent) {
  const head = recent.map(r => `<th colspan="2" class="sum3__y clickable" data-goyear="${r.year}">${r.year}년</th>`).join("")
  const sub = recent.map(() => `<th>계획</th><th>실적</th>`).join("")
  const rows = BT.map(b => `<tr class="sum3__row ${b === "합계" ? "sum3__row--sum" : ""}"><th rowspan="2" scope="row">${b}</th>${recent.map(r => `<td>${eokN(bv(r, b, "계획"))}</td><td>${eokN(bv(r, b, "실적"))}</td>`).join("")}</tr>
    <tr class="sum3__rate ${b === "합계" ? "sum3__row--sum" : ""}">${recent.map(r => `<td colspan="2">${rateBadge(bv(r, b, "계획"), bv(r, b, "실적"))}</td>`).join("")}</tr>`).join("")
  return `<article class="panel overflow-hidden">
      <div class="flex items-start justify-between gap-3 p-5 sm:p-6"><div><h3 class="section-title">연도별 요약</h3><p class="section-help">유지보수예산 ${recent.length}개년 실적비교 · 각 연도 최신 분석</p></div><div class="flex flex-col items-end gap-1.5"><button class="text-sm font-semibold text-ink hover:text-mint-ink" data-view="branches">전체 지사 →</button><span class="text-xs font-semibold text-tri">단위: 억원</span></div></div>
      <div class="overflow-x-auto px-5 pb-5 sm:px-6 sm:pb-6"><table class="sum3"><thead><tr><th rowspan="2">구분</th>${head}</tr><tr class="sum3__sub">${sub}</tr></thead><tbody>${rows}</tbody></table></div>
    </article>`
}

// ── ③ 중장기 전망 패널 ──────────────────────────────────────
// 5번 탭과 같은 /api/forecast/table(전사 합계)을 쓴다. 막대를 누르면 5번 탭 «한눈에 보기» 그 해 구성으로.

const eok = v => { const x = v / 1e5; return Math.abs(x) >= 100 ? fmt(x) : x.toFixed(1) }

function forecastPanel() {
  const t = state.fc.table
  // 머리(2026-10-27 사용자 결정): 제목 옆에 «전사 합계», 부제(단위·기준연도 규칙)는 없앤다 — 단위는 차트 오른쪽 위.
  const head = (badge) => `<div class="flex flex-wrap items-center justify-between gap-3"><h3 class="section-title">중장기 소요 전망 ${t ? `${t.years[0]}~${t.years[t.years.length - 1]}` : "10개년"} <span class="ml-1 align-middle text-base font-semibold text-sub">· 전사 합계</span></h3>
      <div class="flex items-center gap-3">${badge}<button class="text-sm font-semibold text-ink hover:text-mint-ink" data-homefc="">전망 자세히 →</button></div></div>`
  if (!t) return `<section class="panel p-5 sm:p-6" data-home-forecast>${head("")}<p class="mt-6 text-sm text-tri">${state.fc.homeErr ? "전망을 불러오지 못했습니다 — 5번 탭에서 확인하세요." : "전망을 불러오는 중…"}</p></section>`
  const m = fvModel(t, "", true)
  if (!m.years.length || !m.yearTot.some(v => v > 0)) return `<section class="panel p-5 sm:p-6" data-home-forecast>${head("")}<p class="mt-6 text-sm text-tri">아직 전망 금액이 없습니다 — 연도를 마감하면 5번 탭에서 전망을 만들 수 있습니다.</p></section>`
  const n = m.years.length, tot = m.yearTot.reduce((a, b) => a + b, 0)
  const cagr = m.yearTot[0] > 0 ? ((m.yearTot[n - 1] / m.yearTot[0]) ** (1 / (n - 1)) - 1) * 100 : null
  const peak = m.yearTot.indexOf(Math.max(...m.yearTot))
  // 10개년 누적 막대(팀장 검토의견 10/28): 아래 손익(파랑) + 위 자본(회청) — 3개년 막대와 같은 확정 팔레트(10/28 grace), 맨 위 합계(억원). 기준연도는 글자로만 표시.
  // 손익/자본 구분은 /api/forecast/table total_rows 의 «구분»(자본예산 과목 설정 기준). 없으면(옛 결과) 전부 손익으로 쌓인다.
  const cap = m.years.map(y => (t.total_rows || []).filter(r => r.구분 === "자본").reduce((a, r) => a + (Number(r[String(y)]) || 0), 0))
  const STK = [["손익", "#718CBF"], ["자본", "#ADB7C9"]]   // custom.css --chart-profit / --chart-capital
  const W = 760, H = 260, L = 8, R = 8, T = 30, B = 44, bw = (W - L - R) / n, max = Math.max(...m.yearTot) || 1
  let s = `<text x="${W - R}" y="12" text-anchor="end" font-size="12" font-weight="600" fill="#5D5D5D">단위: 억원</text><line x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}" stroke="#C9C9C9"/>`
  m.yearTot.forEach((v, i) => {
    const c = Math.min(cap[i], v), parts = [v - c, c], x = L + i * bw + bw * .2, w = bw * .6
    const h = v / max * (H - T - B), y = H - B - h
    let y0 = H - B, segs = ""
    parts.forEach((pv, k) => {
      const ph = pv / max * (H - T - B)
      if (ph <= 0) return
      const top = k === 1 || parts[1] <= 0
      segs += top
        ? `<path d="M${x},${y0} V${y0 - ph + Math.min(4, ph)} q0,-4 4,-4 h${w - 8} q4,0 4,4 V${y0} Z" fill="${STK[k][1]}"/>`
        : `<rect x="${x}" y="${y0 - ph}" width="${w}" height="${ph}" fill="${STK[k][1]}"/>`
      if (k === 0 && parts[1] > 0) segs += `<line x1="${x}" x2="${x + w}" y1="${y0 - ph}" y2="${y0 - ph}" stroke="#fff" stroke-width="2"/>`
      y0 -= ph
    })
    s += `<g class="clickable" data-homefc="${m.years[i]}"><title>전사 ${m.years[i]}년 ${fmt(v)} 천원 (손익 ${fmt(parts[0])} · 자본 ${fmt(parts[1])})${i ? ` · 전년 대비 ${((v / m.yearTot[i - 1] - 1) * 100).toFixed(1)}%` : " · 기준연도"} (클릭: 그 해 과목 구성)</title>
      <rect x="${L + i * bw}" y="${T - 22}" width="${bw}" height="${H - T - B + 22}" fill="transparent"/>${segs}
      <text x="${x + w / 2}" y="${y - 7}" text-anchor="middle" font-size="12" font-weight="700" fill="#0D0D0D">${eok(v)}</text>
      <text x="${x + w / 2}" y="${H - B + 18}" text-anchor="middle" font-size="12" font-weight="${i === peak ? 800 : 600}" fill="#5D5D5D">${m.years[i]}</text>
      ${i === 0 ? `<text x="${x + w / 2}" y="${H - B + 33}" text-anchor="middle" font-size="10" fill="#767676">기준연도</text>` : ""}</g>`
  })
  const top = m.acctRows.slice(0, 5), mx = top[0]?.total || 1
  const kpi = (k, v, sub) => `<div class="rounded-control bg-subtle px-4 py-3"><p class="text-xs font-semibold text-sub">${k}</p><p class="mt-1 text-lg font-bold text-ink">${v}</p><p class="text-xs text-tri">${sub}</p></div>`
  return `
  <section class="panel p-5 sm:p-6" data-home-forecast>
    ${head(`<span class="badge bg-subtle px-3 py-1 text-sm font-bold text-ink">기준 ${esc(t.base_year)}년</span>`)}
    <div class="mt-5 grid gap-3 sm:grid-cols-3">
      ${kpi("10년 누계", `${eok(tot)}<span class="ml-1 text-xs font-semibold text-tri">억원</span>`, `${fmt(tot)} 천원`)}
      ${kpi("연평균 증감", cagr === null ? "-" : `${cagr >= 0 ? "+" : ""}${cagr.toFixed(1)}%`, `${m.years[0]} ${eok(m.yearTot[0])}억원 → ${m.years[n - 1]} ${eok(m.yearTot[n - 1])}억원`)}
      ${kpi("가장 많은 해", `${m.years[peak]}년`, `${eok(m.yearTot[peak])}억원`)}
    </div>
    <div class="mt-6 grid gap-6 xl:grid-cols-[1.6fr_1fr]">
      <div class="overflow-x-auto"><svg viewBox="0 0 ${W} ${H}" class="w-full min-w-[520px]" role="img" aria-label="전사 중장기 10개년 소요 전망">${s}</svg>
        <p class="flex items-center gap-2 text-xs text-sub"><span class="h-2 w-2 rounded-full bg-line-strong"></span>* 막대를 누르면 그 해 과목 상세 구성 페이지로 이동됩니다.</p>
        <p class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-sub" aria-label="막대 색 기준(아래 손익, 위 자본, 막대 위 숫자는 합계)">${STK.map(([l, c]) => `<span class="inline-flex items-center gap-1.5"><span class="h-3 w-5 rounded-sm" style="background:${c}"></span>${l}</span>`).join("")}</p></div>
      <div><h4 class="text-sm font-bold text-ink">10년 누계 상위 과목 <span class="font-semibold text-sub">(억원)</span></h4>
        <div class="mt-4 space-y-4">${top.map(r => `<div><div class="mb-1.5 flex items-end justify-between gap-3"><span class="truncate text-sm font-semibold text-ink">${esc(r.key)}</span><span class="shrink-0 text-xs text-sub"><span class="font-semibold text-ink">${eok(r.total)}억원</span> · ${(r.total / tot * 100).toFixed(0)}%</span></div>
          <div class="h-3 overflow-hidden rounded-full bg-subtle"><div class="h-full rounded-full" style="width:${r.total / mx * 100}%;background:var(--chart-profit)"></div></div></div>`).join("")}</div>
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
