import { lockedSay } from "../components/characters.js"
import { state } from "../state.js"
import { esc, fmt } from "../util.js"

// ─────────────────────────────────────────────────────────────
// 검토 큐 (2026-10-27) — «어디부터 볼지»를 돈으로 정해 주는 작업대.
//
// 서버(/api/review-queue)가 사업 한 줄마다 이유(차이·과다 귀속·저확신·음수)를 모아
// 검토 금액 × 위험 가중으로 줄 세워 준다. 이 화면은
//   ① 남은 검토 금액의 80% 를 덮는 건수와 처리 진행률(금액 기준) — 위 카드와 곡선
//   ② 한 줄씩 1클릭 처리 — 승인(이상 없음) · 사유 칩 · 추천 재배정
// 을 보여 준다. 처리하면 줄이 빠지고 진행률이 바로 오른다(서버 재계산은 뒤에서).
// 상호작용은 review_actions.js 가 맡는다(data-rq="…").
// ─────────────────────────────────────────────────────────────

export const RQ_REASONS = [["variance", "차이 사유"], ["overload", "과다 귀속"],
                           ["lowconf", "저확신 귀속"], ["negative", "음수 실적"]]
const RESOLVED = new Set(["moved", "approved", "noted"])
const COVER = 0.8

// 사유 칩 — 방향마다 자주 쓰는 사유. 누르면 바로 저장된다(1클릭). 칩 순서 = 단축키 1~5.
export const NOTE_CHIPS = {
  over: ["긴급·돌발 정비 추가", "단가·물량 증가", "전년 이월분 집행", "사업 통합 집행", "타 사업 전표 혼입(재배정 예정)"],
  under: ["차년도 이월", "계약·입찰 지연", "낙찰 차액", "사업 축소", "타 예산으로 집행"],
  none: ["미시행 — 차년도 이월", "미시행 — 계약·입찰 지연", "미시행 — 사업 취소·보류", "미시행 — 타 사업으로 통합"],
}

export function chipsFor(it) {
  if (!it.needsNote) return []
  if (it.actual === 0) return NOTE_CHIPS.none
  return it.dir === "over" ? NOTE_CHIPS.over : NOTE_CHIPS.under
}

// 서버 review_queue.summarize 와 같은 셈 — 처리 직후 화면을 바로 고치려고 둔다(서버 값이 오면 덮인다).
export function rqSort(items) {
  items.sort((a, b) => (a.resolved - b.resolved) || (b.score - a.score) || (b.amount - a.amount)
    || String(a.key).localeCompare(String(b.key)))
  let n = 0
  for (const it of items) it.rank = it.resolved ? null : ++n
  return items
}

export function rqCurve(items) {
  const open = items.filter(it => !it.resolved).map(it => it.amount)
  const total = open.reduce((a, b) => a + b, 0)
  let acc = 0
  return open.map(a => { acc += a; return total ? acc / total : 1 })
}

export function rqSummarize(items) {
  const curve = rqCurve(items)
  const total = items.reduce((a, it) => a + it.amount, 0)
  const done = items.filter(it => it.resolved).reduce((a, it) => a + it.amount, 0)
  const i80 = curve.findIndex(c => c >= COVER - 1e-9)
  const counts = Object.fromEntries(RQ_REASONS.map(([c]) => [c, 0]))
  for (const it of items) if (!it.resolved) for (const r of it.reasons) counts[r.code] = (counts[r.code] || 0) + 1
  return {total: items.length, open: curve.length, resolved: items.length - curve.length,
          high_open: items.filter(it => !it.resolved && it.risk === "높음").length,
          amount_total: total, amount_resolved: done, amount_open: total - done,
          progress: total ? done / total : 1, n80: i80 < 0 ? curve.length : i80 + 1, cover_target: COVER, counts}
}

export function isResolved(status) { return RESOLVED.has(status) }

// ── 표시 도우미 ───────────────────────────────────────────────

const pct = (v, d = 0) => `${(v * 100).toFixed(d)}%`

const REASON_CLS = {overload: "bg-err-bg text-err", negative: "bg-err-bg text-err",
                    lowconf: "bg-warn-bg text-warn", variance: "bg-info-bg text-info"}
const STATUS = {approved: ["승인됨", "bg-ok-bg text-ok"], noted: ["사유 입력됨", "bg-ok-bg text-ok"],
                moved: ["재배정 저장 · 분석 반영 대기", "bg-info-bg text-info"],
                stale: ["승인 뒤 숫자 바뀜 — 다시 확인", "bg-warn-bg text-warn"]}

function rateCls(rate) {
  if (rate === null || rate === undefined) return "text-sub"
  return rate > 120 ? "text-err" : rate >= 80 ? "text-ok" : "text-warn"
}

/** 계획(눈금) 대 실적(막대) — 같은 축. 계획보다 넘친 부분은 진하게. */
function bulletHtml(it) {
  const max = Math.max(it.plan, Math.abs(it.actual), 1)
  const a = Math.max(0, it.actual) / max * 100
  const p = it.plan / max * 100
  const over = it.actual > it.plan && it.plan > 0
  return `<div class="rq-bullet" aria-hidden="true">
      <span class="rq-bullet__bar ${over ? "rq-bullet__bar--over" : ""}" style="width:${a.toFixed(1)}%"></span>
      ${it.plan > 0 ? `<span class="rq-bullet__plan" style="left:calc(${p.toFixed(1)}% - 1px)"></span>` : ""}
    </div>`
}

// ── 요약 줄 — 건수·금액만(2026-10-27 사용자 결정: 큰 머리 카드·곡선은 두지 않는다) ──────────

function shownCount(r) {
  if (r.n === "all") return Infinity
  return Number(r.n) || 20
}

function summaryHtml(sm) {
  return `<section class="panel flex flex-wrap items-baseline gap-x-6 gap-y-1 px-5 py-3 text-sm text-sub" aria-label="검토 요약">
      <span>남은 검토 <b class="text-base text-ink">${fmt(sm.open)}</b>건</span>
      <span>남은 금액 <b class="text-base text-ink">${fmt(sm.amount_open)}</b> 천원</span>
      <span>처리 <b class="text-base text-ink">${fmt(sm.resolved)}</b>건 · ${fmt(sm.amount_resolved)} 천원</span>
      <span>위험 높음 <b class="text-base text-err">${fmt(sm.high_open)}</b>건</span>
    </section>`
}

// ── 거르기 ───────────────────────────────────────────────────

export function rqFiltered() {
  const r = state.rq
  return (r.data?.items || []).filter(it =>
    (r.show === "all" || (r.show === "done" ? it.resolved : !it.resolved))
    && (!r.reason || it.reasons.some(x => x.code === r.reason))
    && (!r.branch || it.branch === r.branch)
    && (r.budget === "all" || it.budget === r.budget))
}

function filterHtml(sm, items) {
  const r = state.rq
  const chip = (code, label, n) => `<button class="badge ${r.reason === code ? "bg-ink text-white" : "bg-subtle text-ink"}" data-rq="reason" data-code="${esc(code)}">${esc(label)} ${fmt(n)}</button>`
  const branches = [...new Set(items.map(it => it.branch))].sort((a, b) => a.localeCompare(b, "ko"))
  const show = (v, label) => `<button class="rq-seg ${r.show === v ? "rq-seg--on" : ""}" data-rq="show" data-v="${v}">${label}</button>`
  return `
    <section class="panel flex flex-wrap items-center gap-3 p-4">
      <div class="flex flex-wrap gap-2">${chip("", "전체", sm.open)}${RQ_REASONS.map(([c, l]) => chip(c, l, sm.counts?.[c] || 0)).join("")}</div>
      <div class="ml-auto flex flex-wrap items-center gap-2">
        <label class="text-sm text-sub">예산
          <select class="control ml-1 !w-auto" data-rq-sel="budget">
            ${[["all", "전체"], ["손익", "손익"], ["자본", "자본"]].map(([v, l]) => `<option value="${v}" ${r.budget === v ? "selected" : ""}>${l}</option>`).join("")}
          </select></label>
        <label class="text-sm text-sub">지사
          <select class="control ml-1 !w-auto" data-rq-sel="branch">
            <option value="">전체</option>
            ${branches.map(b => `<option value="${esc(b)}" ${r.branch === b ? "selected" : ""}>${esc(b)}</option>`).join("")}
          </select></label>
        <div class="rq-segs">${show("open", "미처리")}${show("done", "처리됨")}${show("all", "전체")}</div>
      </div>
    </section>`
}

// ── 한 줄(카드) ──────────────────────────────────────────────

function actionsHtml(it, locked) {
  const r = state.rq
  const k = esc(it.key)
  if (it.resolved) {
    const undo = it.status === "approved" ? `<button class="btn-secondary rq-btn" data-rq="unack" data-key="${k}">승인 취소</button>`
      : it.status === "noted" ? `<button class="btn-secondary rq-btn" data-rq="note-clear" data-key="${k}">사유 지우기</button>` : ""
    return `<div class="rq-actions">${undo}${detailBtn(it)}</div>`
  }
  const chips = chipsFor(it)
  const editing = r.noteKey === it.key
  const canMove = it.actual !== 0 || it.dir === "under"
  return `<div class="rq-actions">
      <button class="btn-primary rq-btn" data-rq="ack" data-key="${k}" title="이상 없음 — 단축키 A">✓ 이상 없음</button>
      ${chips.map((c, i) => `<button class="rq-chip" data-rq="chip" data-key="${k}" data-note="${esc(c)}" title="사유로 저장 — 단축키 ${i + 1}">${esc(c)}</button>`).join("")}
      ${it.needsNote ? `<button class="rq-chip rq-chip--ghost" data-rq="note-edit" data-key="${k}">직접 입력…</button>` : ""}
      <button class="btn-secondary rq-btn" data-rq="explain" data-key="${k}" aria-expanded="${r.explOpen === it.key}">${r.explOpen === it.key ? "근거 닫기 ▲" : "근거·초안 ▾"}</button>
      ${canMove ? `<button class="btn-secondary rq-btn" data-rq="expand" data-key="${k}" aria-expanded="${r.open === it.key}" title="단축키 E">${r.open === it.key ? "전표 닫기 ▲" : "전표·재배정 ▾"}</button>` : ""}
      ${detailBtn(it)}
    </div>
    ${editing ? `<div class="rq-noteedit">
        <textarea id="rqNoteText" class="control flex-1" rows="${r.draft?.key === it.key ? 4 : 1}" maxlength="500" placeholder="차이 사유 (500자 이내 · Enter 저장, Shift+Enter 줄바꿈)" data-key="${k}">${esc(r.draft?.key === it.key ? r.draft.text : (it.note || ""))}</textarea>
        <button class="btn-primary rq-btn" data-rq="note-save" data-key="${k}">저장</button>
        <button class="btn-secondary rq-btn" data-rq="note-cancel">취소</button>
      </div>` : ""}
    ${r.explOpen === it.key ? explainHtml(it) : ""}
    ${r.open === it.key ? suggestHtml(it, locked) : ""}`
}

// 근거 설명(B) — 분석 결과에 있는 사실만 문장으로. 원인은 «추정»으로만, 사유 저장은 사람이 고친 뒤.
function explainHtml(it) {
  const ex = state.rq.expl[it.key]
  if (!ex) return `<div class="rq-sugg"><p class="text-sm text-sub">근거를 모으는 중…</p></div>`
  if (ex.error) return `<div class="rq-sugg"><p class="text-sm text-err">${esc(ex.error)}</p></div>`
  return `<div class="rq-sugg">
      <h4 class="text-sm font-semibold text-ink">근거</h4>
      <ul class="mt-1.5 space-y-1 text-sm text-ink">${ex.facts.map(f => `<li>· ${esc(f)}</li>`).join("")}</ul>
      ${ex.hints.length ? `<h4 class="mt-3 text-sm font-semibold text-ink">추정 원인 <span class="text-xs font-normal text-tri">전표 글자·귀속 모양으로 짐작 — 확인 필요</span></h4>
        <ul class="mt-1.5 space-y-1 text-sm text-sub">${ex.hints.map(h => `<li>· ${esc(h)}</li>`).join("")}</ul>` : ""}
      ${it.needsNote && !it.resolved ? `<div class="mt-3 flex flex-wrap items-center gap-2">
          <button class="btn-primary rq-btn" data-rq="draft" data-key="${esc(it.key)}">초안을 사유 칸에 넣기</button>
          <span class="text-xs text-tri">넣은 뒤 고치고 [저장] — 바로 저장되지 않아요</span></div>` : ""}
    </div>`
}

function detailBtn(it) {
  return `<button class="rq-link" data-drill="${esc(it.branch)}" data-drill-item="${esc(it.item)}" data-drill-budget="${esc(it.budget)}" data-drill-name="${esc(it.name)}">3+ 상세 →</button>`
}

function voucherRow(v, it, locked, mode) {
  const dis = locked ? 'disabled title="마감 연도 — 재배정 불가"' : ""
  const text = v.텍스트 ? esc(v.텍스트) : '<span class="text-tri">(전표 글자 없음)</span>'
  const conf = v.확신도 === null || v.확신도 === undefined ? "" : Number(v.확신도).toFixed(2)
  let action
  if (mode === "in") {
    action = `<span class="min-w-0 flex-1 text-xs text-sub">지금 «${esc(v.from)}» · ${esc(v.why)}</span>
      <button class="btn-primary rq-btn" data-rq="pull" data-key="${esc(it.key)}" data-id="${v.erp_row_id}" ${dis}>이리로 가져오기</button>`
  } else if (v.suggest) {
    action = `<span class="min-w-0 flex-1"><span class="rq-rec">추천</span> <span class="font-semibold text-ink">→ ${esc(v.suggest.target)}</span>
        <span class="block text-xs text-sub">${esc(v.suggest.why)}</span></span>
      <button class="btn-primary rq-btn" data-rq="move" data-key="${esc(it.key)}" data-id="${v.erp_row_id}" data-target="${esc(v.suggest.target)}" ${dis}>추천대로 옮기기</button>`
  } else {
    const cands = state.rq.sugg[it.key]?.candidates || []
    const pick = state.rq.pick[v.erp_row_id] || ""
    action = cands.length ? `<select class="control min-w-0 flex-1 sm:max-w-[22rem]" data-rq-pick="${v.erp_row_id}" aria-label="옮길 사업" ${dis}>
        <option value="">옮길 사업 고르기 (잔액 큰 순)</option>
        ${cands.map(c => `<option value="${esc(c.name)}" ${pick === c.name ? "selected" : ""}>${esc(c.name)} · 잔액 ${fmt(c.remain)}천원</option>`).join("")}
      </select>
      <button class="btn-secondary rq-btn" data-rq="move" data-key="${esc(it.key)}" data-id="${v.erp_row_id}" ${dis}>옮기기</button>`
      : '<span class="text-xs text-tri">같은 과목에 옮길 계획 사업이 없어요</span>'
  }
  return `<li class="rq-voucher ${v.suggest ? "rq-voucher--rec" : ""}">
      <div class="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
        <span class="text-xs text-sub">${esc(v.전기일 || "")}</span>
        <span class="min-w-0 flex-1 break-all text-ink">${text}</span>
        <span class="font-semibold text-ink">${fmt(v.금액천원)}<span class="ml-0.5 text-xs text-tri">천원</span></span>
        <span class="text-xs text-sub">${esc(v.근거 || "")}${conf ? ` · ${conf}` : ""}</span>
      </div>
      <div class="mt-1.5 flex flex-wrap items-center gap-2">${action}</div>
    </li>`
}

function suggestHtml(it, locked) {
  const sg = state.rq.sugg[it.key]
  if (!sg) return `<div class="rq-sugg"><p class="text-sm text-sub">전표를 불러오는 중…</p></div>`
  if (sg.error) return `<div class="rq-sugg"><p class="text-sm text-err">${esc(sg.error)}</p></div>`
  // 추천이 붙은 전표를 맨 위로 — 나머지는 금액 큰 순 그대로
  const nominate = [...sg.nominate].sort((a, b) => (!!b.suggest - !!a.suggest))
  const recs = nominate.filter(v => v.suggest)
  const head = (t, extra = "") => `<div class="flex flex-wrap items-center justify-between gap-2"><h4 class="text-sm font-semibold text-ink">${t}</h4>${extra}</div>`
  const list = (rows, mode) => `<ul class="mt-2 space-y-2">${rows.map(v => voucherRow(v, it, locked, mode)).join("")}</ul>`
  return `<div class="rq-sugg">
      ${nominate.length ? head(`이 줄의 큰 전표 ${fmt(nominate.length)}건 / 전체 ${fmt(sg.voucher_total)}건${recs.length ? ` · 추천 ${recs.length}건` : ""}`,
          recs.length > 1 && !locked ? `<button class="btn-primary rq-btn" data-rq="move-all" data-key="${esc(it.key)}">추천 ${recs.length}건 모두 옮기기</button>` : "")
        + list(nominate, "out") : ""}
      ${sg.incoming.length ? `<div class="${nominate.length ? "mt-4" : ""}">${head("같은 과목 다른 사업에 붙었지만 이 사업 이름을 더 닮은 전표")}${list(sg.incoming, "in")}</div>` : ""}
      ${!nominate.length && !sg.incoming.length ? '<p class="text-sm text-sub">옮길 만한 전표가 없어요.</p>' : ""}
      <p class="mt-3 text-xs text-tri">추천 = 전표 글자가 다른 계획 사업 이름과 분명히 더 닮았을 때만(유사도 0.75↑, 설비·연도가 같을 때). 옮긴 전표는 상단 «분석 반영» 때 결과에 들어가요.</p>
    </div>`
}

function cardHtml(it, locked) {
  const st = STATUS[it.status]
  const r = state.rq
  return `<li class="rq-card ${it.resolved ? "rq-card--done" : ""} ${r.focus === it.key ? "rq-card--focus" : ""}" data-rq-card="${esc(it.key)}" tabindex="0">
      <div class="flex flex-wrap items-start gap-x-4 gap-y-2">
        <span class="rq-rank" aria-label="${it.rank ? `${it.rank}순위` : "처리됨"}">${it.rank ? it.rank : "✓"}</span>
        <div class="min-w-0 flex-1 basis-[12rem]">
          <div class="flex flex-wrap items-center gap-1.5">
            <span class="badge ${it.risk === "높음" ? "bg-err-bg text-err" : "bg-subtle text-sub"}">${esc(it.risk)}</span>
            ${it.reasons.map(x => `<span class="badge ${REASON_CLS[x.code] || "bg-subtle text-ink"}">${esc(x.label)}</span>`).join("")}
            ${st ? `<span class="badge ${st[1]}">${esc(st[0])}</span>` : ""}
          </div>
          <p class="mt-1.5 break-keep font-semibold text-ink">${esc(it.name)}</p>
          <p class="text-xs text-sub">${esc(it.branch)} · ${esc(it.budget)} · ${esc(it.item)}</p>
          <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span class="text-sub">계획 <b class="text-ink">${fmt(it.plan)}</b>천원 → 실적 <b class="text-ink">${fmt(it.actual)}</b>천원</span>
            ${it.rate !== null && it.rate !== undefined ? `<span class="font-bold ${rateCls(it.rate)}">${it.rate.toFixed(1)}%</span>` : ""}
          </div>
          ${bulletHtml(it)}
          <ul class="mt-2 space-y-0.5 text-sm text-ink">${it.reasons.map(x => `<li>${esc(x.text)}</li>`).join("")}</ul>
          ${it.ctx?.length ? `<ul class="mt-1 space-y-0.5 text-xs text-sub">${it.ctx.map(c => `<li>· ${esc(c)}</li>`).join("")}</ul>` : ""}
          ${it.note ? `<p class="mt-2 text-sm"><span class="font-semibold text-ink">사유</span> <span class="text-sub">${esc(it.note)}</span></p>` : ""}
          ${it.ack && it.status !== "approved" ? `<p class="mt-1 text-xs text-warn">승인 ${esc(it.ack.operator || "")} ${esc(it.ack.updated_at || "")} — 그때 실적 ${fmt(it.ack.actual)}천원</p>` : ""}
        </div>
        <div class="shrink-0 pl-[3.25rem] sm:pl-0 sm:text-right">
          <p class="text-xs font-semibold text-tri">검토 금액</p>
          <p class="text-xl font-bold text-ink">${fmt(it.amount)}<span class="ml-0.5 text-xs font-semibold text-tri">천원</span></p>
        </div>
      </div>
      ${actionsHtml(it, locked)}
    </li>`
}

// ── 화면 ─────────────────────────────────────────────────────

export function renderReview() {
  const r = state.rq
  const d = r.data
  const locked = !!(d?.locked ?? state.status?.locked)
  const title = `<section><p class="text-sm font-semibold text-ink">STAGE 3 · 검토</p>
      <h2 class="mt-1 font-hanan text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">검토 큐 — ${esc(state.year)}년</h2></section>`
  if (!d) return `<div class="space-y-6">${title}<section class="panel p-6 text-sm text-sub">검토 큐를 불러오지 못했어요.</section></div>`
  if (!d.analyzed) {
    return `<div class="space-y-6">${title}<section class="panel p-6 text-sm text-sub">${esc(state.year)}년 분석 결과가 없어요 — 실적 집계에서 분석을 먼저 실행하세요.</section></div>`
  }
  const items = d.items || []
  const sm = rqSummarize(items)
  const list = rqFiltered()
  const n = shownCount(r)
  const shown = list.slice(0, n)
  const rest = list.length - shown.length
  const openList = list.filter(it => !it.resolved)
  const covered = openList.slice(0, n).reduce((a, it) => a + it.amount, 0)
  const listAmt = openList.reduce((a, it) => a + it.amount, 0)
  const sub = r.reason || r.branch || r.budget !== "all"
  return `
    <div class="space-y-6">
      ${title}
      ${locked ? lockedSay("재배정은 막혀요. «이상 없음»·사유는 검토 기록으로만 남고 마감된 숫자는 바뀌지 않아요.") : ""}
      ${summaryHtml(sm)}
      ${filterHtml(sm, items)}
      <section aria-label="검토 목록">
        <div class="mb-3 flex flex-wrap items-baseline justify-between gap-2 text-sm text-sub">
          <span>${fmt(shown.length)} / ${fmt(list.length)}건 표시${sub && r.show === "open" && listAmt ? ` · 이 조건 남은 금액의 ${pct(covered / listAmt)}` : ""}</span>
          <span class="hidden sm:inline">단축키 J·K 이동 · A 승인 · 1~5 사유 칩 · E 전표</span>
        </div>
        ${shown.length ? `<ol class="space-y-3">${shown.map(it => cardHtml(it, locked)).join("")}</ol>`
          : `<p class="panel p-6 text-sm text-sub">${r.show === "done" ? "아직 처리한 줄이 없어요." : "이 조건에 남은 줄이 없어요."}</p>`}
        ${rest > 0 ? `<button class="btn-secondary mt-4" data-rq="more">${fmt(Math.min(rest, 50))}건 더 보기 (남은 ${fmt(rest)}건)</button>` : ""}
      </section>
    </div>`
}
