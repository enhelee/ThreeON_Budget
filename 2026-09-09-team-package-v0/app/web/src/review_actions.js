import { api } from "./api.js"
import { toast } from "./components/feedback.js"
import { loadPending, loadReviewQueue } from "./data.js"
import { renderPage } from "./router.js"
import { state } from "./state.js"
import { $ } from "./util.js"
import { chipsFor, isResolved, rqFiltered, rqSort } from "./views/review.js"

// ─────────────────────────────────────────────────────────────
// 검토 대기 핸들러 — views/review.js 가 그린 DOM(data-rq=…)을 읽는다.
// main.js 의 click/change/keydown 리스너가 먼저 여기로 위임하고, 처리했으면(true) 멈춘다.
//
// 1클릭 흐름: 저장 API 를 부르고 → 그 줄을 «처리됨»으로 바꿔 바로 다시 그린다(줄이 빠지고
// 진행률이 오른다) → 뒤에서 큐를 다시 받아 서버 계산으로 덮는다. 실패하면 되돌린다.
// ─────────────────────────────────────────────────────────────

const JSON_HDR = {"Content-Type": "application/json"}
const byKey = key => (state.rq.data?.items || []).find(it => it.key === key)

/** 줄 상태를 바꾸고 다시 줄 세운다. 반환: 되돌리기 함수. */
function patch(key, fields) {
  const it = byKey(key)
  if (!it) return () => {}
  const before = {...it}
  Object.assign(it, fields)
  if ("status" in fields) it.resolved = isResolved(it.status)
  rqSort(state.rq.data.items)
  return () => { Object.assign(it, before); rqSort(state.rq.data.items) }
}

/** 처리된 카드는 살짝 빠지는 동작을 보여 준 뒤 다시 그린다(동작 줄이기 설정이면 바로). */
async function leave(key) {
  const el = document.querySelector(`[data-rq-card="${CSS.escape(key)}"]`)
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  if (el && !reduce && state.rq.show === "open") {
    el.classList.add("rq-card--leave")
    await new Promise(r => setTimeout(r, 220))
  }
}

/** 서버 계산으로 덮어쓴다 — 실패해도 화면은 낙관적 상태로 남는다. */
let refreshTimer = null
function refreshSoon() {
  clearTimeout(refreshTimer)
  refreshTimer = setTimeout(async () => {
    try {
      await loadReviewQueue()
      if (state.view === "review") { renderPage(); refocus() }
    } catch { /* 다음 동작이나 새로고침 때 맞춰진다 */ }
  }, 600)
}

function nextFocusKey(key) {
  const list = rqFiltered()
  const i = list.findIndex(it => it.key === key)
  const nxt = list.slice(i + 1).find(it => !it.resolved) || list.slice(0, Math.max(i, 0)).reverse().find(it => !it.resolved)
  return nxt ? nxt.key : null
}

function refocus() {
  const k = state.rq.focus
  if (!k) return
  const el = document.querySelector(`[data-rq-card="${CSS.escape(k)}"]`)
  if (el && document.activeElement?.tagName !== "INPUT") el.focus({preventScroll: false})
}

async function resolveWith(key, status, fields, call, okMsg) {
  const focusNext = state.rq.focus === key ? nextFocusKey(key) : state.rq.focus
  await leave(key)
  const undo = patch(key, {...fields, status})
  if (state.rq.open === key) state.rq.open = null
  if (state.rq.noteKey === key) { state.rq.noteKey = null; state.rq.draft = null }
  state.rq.focus = focusNext
  renderPage(); refocus()
  try {
    await call()
    toast(okMsg)
    refreshSoon()
  } catch (err) {
    undo(); renderPage(); toast(err.message)
  }
}

const lineBody = it => ({year: state.year, budget: it.budget, 예산과목: it.item, 처지사: it.branch, 사업명: it.name})

async function ack(key, on) {
  const it = byKey(key)
  if (!it) return
  if (on) {
    await resolveWith(key, "approved", {ack: {actual: it.actual}}, () => api("/api/review-ack", {method: "PUT", headers: JSON_HDR,
      body: JSON.stringify({...lineBody(it), ack: true})}), `승인 — «${it.name}»`)
    return
  }
  const undo = patch(key, {status: "open", ack: null})
  renderPage()
  try {
    await api("/api/review-ack", {method: "PUT", headers: JSON_HDR, body: JSON.stringify({...lineBody(it), ack: false})})
    toast("승인을 취소했습니다."); refreshSoon()
  } catch (err) { undo(); renderPage(); toast(err.message) }
}

async function saveNote(key, note) {
  const it = byKey(key)
  if (!it) return
  note = (note || "").trim()
  const call = () => api("/api/variance-note", {method: "PUT", headers: JSON_HDR,
    body: JSON.stringify({...lineBody(it), note})})
  if (!note) {           // 지우기 — 다시 연다
    const undo = patch(key, {status: it.ack ? "stale" : "open", note: null})
    renderPage()
    try { await call(); toast("사유를 지웠습니다."); refreshSoon() }
    catch (err) { undo(); renderPage(); toast(err.message) }
    return
  }
  await resolveWith(key, "noted", {note}, call, `사유 저장 — «${note}»`)
}

async function loadExpl(key) {
  const it = byKey(key)
  if (!it) return
  try {
    const q = new URLSearchParams({year: state.year, budget: it.budget, branch: it.branch, item: it.item, name: it.name})
    state.rq.expl[key] = await api(`/api/review-explain?${q}`)
  } catch (err) { state.rq.expl[key] = {error: err.message} }
  if (state.view === "review") renderPage()
}

async function loadSugg(key) {
  const it = byKey(key)
  if (!it) return
  try {
    const q = new URLSearchParams({year: state.year, budget: it.budget, branch: it.branch, item: it.item, name: it.name})
    state.rq.sugg[key] = await api(`/api/review-suggest?${q}`)
  } catch (err) { state.rq.sugg[key] = {error: err.message} }
  if (state.view === "review") renderPage()
}

/** 전표 옮기기 — {target: [erp_row_id…]} 묶음마다 POST /api/override. 재배정은 분석 반영 때 결과에 들어간다. */
async function move(key, groups, label) {
  const it = byKey(key)
  if (!it) return
  const ids = Object.values(groups).flat()
  if (!ids.length) return
  await resolveWith(key, "moved", {}, async () => {
    for (const [target, rows] of Object.entries(groups)) {
      await api("/api/override", {method: "POST", headers: JSON_HDR,
        body: JSON.stringify({year: state.year, budget: it.budget, erp_row_ids: rows, target_name: target,
                              memo: `검토 대기 — ${label}`})})
    }
    delete state.rq.sugg[key]
    await loadPending()           // 헤더 «분석 반영 (N)» 배지
  }, `재배정 저장 — 전표 ${ids.length}건 · 상단 «분석 반영»을 누르면 결과에 들어가요.`)
}

// ── 클릭 ─────────────────────────────────────────────────────

export async function rqClick(e) {
  const t = e.target.closest("[data-rq]")
  if (!t || state.view !== "review") return false
  const r = state.rq
  const key = t.dataset.key
  if (key) r.focus = key
  switch (t.dataset.rq) {
    case "more": {
      const cur = rqFiltered().length
      const shown = document.querySelectorAll("[data-rq-card]").length
      r.n = String(Math.min(cur, shown + 50)); renderPage(); return true
    }
    case "show": r.show = t.dataset.v; r.n = "20"; renderPage(); return true
    case "reason": r.reason = t.dataset.code; r.n = "20"; renderPage(); return true
    case "ack": await ack(key, true); return true
    case "unack": await ack(key, false); return true
    case "chip": await saveNote(key, t.dataset.note); return true
    case "note-edit": r.noteKey = key; r.draft = null; renderPage(); $("#rqNoteText")?.focus(); return true
    case "note-cancel": r.noteKey = null; r.draft = null; renderPage(); return true
    case "explain":
      r.explOpen = r.explOpen === key ? null : key
      renderPage()
      if (r.explOpen && !r.expl[key]) await loadExpl(key)
      return true
    case "draft": {       // 근거 초안을 사유 칸에 — 저장은 사람이 고친 뒤 [저장]
      r.noteKey = key; r.draft = {key, text: r.expl[key]?.draft || ""}
      renderPage()
      const el = $("#rqNoteText")
      if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length) }
      return true
    }
    case "note-save": await saveNote(key, $("#rqNoteText")?.value); return true
    case "note-clear": await saveNote(key, ""); return true
    case "expand":
      r.open = r.open === key ? null : key
      renderPage()
      if (r.open && !r.sugg[key]) await loadSugg(key)
      return true
    case "move": {
      const id = Number(t.dataset.id)
      const target = t.dataset.target || r.pick[id]
      if (!target) { toast("옮길 사업을 고르세요."); return true }
      await move(key, {[target]: [id]}, `«${byKey(key)?.name}» → «${target}»`)
      return true
    }
    case "move-all": {
      const groups = {}
      for (const v of r.sugg[key]?.nominate || []) {
        if (v.suggest) (groups[v.suggest.target] ||= []).push(v.erp_row_id)
      }
      await move(key, groups, `«${byKey(key)?.name}» 추천 일괄`)
      return true
    }
    case "pull": {
      const it = byKey(key)
      await move(key, {[it.name]: [Number(t.dataset.id)]}, `«${it.name}»(으)로 가져오기`)
      return true
    }
  }
  return false
}

export function rqChange(e) {
  if (state.view !== "review") return false
  const sel = e.target.closest("[data-rq-sel]")
  if (sel) { state.rq[sel.dataset.rqSel] = sel.value; renderPage(); return true }
  const pick = e.target.closest("[data-rq-pick]")
  if (pick) { state.rq.pick[Number(pick.dataset.rqPick)] = pick.value; return true }
  return false
}

// ── 단축키(J·K 이동 · A 승인 · 1~5 사유 칩 · E 전표) ─────────────

export function rqKey(e) {
  if (state.view !== "review" || e.ctrlKey || e.metaKey || e.altKey) return false
  const tag = e.target?.tagName
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
    if (e.key === "Enter" && !e.shiftKey && e.target.id === "rqNoteText") { e.preventDefault(); saveNote(e.target.dataset.key, e.target.value); return true }
    if (e.key === "Escape" && e.target.id === "rqNoteText") { state.rq.noteKey = null; state.rq.draft = null; renderPage(); return true }
    return false
  }
  const k = e.key.toLowerCase()
  const cards = [...document.querySelectorAll("[data-rq-card]")]
  if (!cards.length) return false
  const cur = document.activeElement?.closest?.("[data-rq-card]")
  const idx = cur ? cards.indexOf(cur) : -1
  if (k === "j" || k === "k") {
    const n = k === "j" ? Math.min(idx + 1, cards.length - 1) : Math.max(idx - 1, 0)
    cards[n].focus(); cards[n].scrollIntoView({block: "nearest"})
    state.rq.focus = cards[n].dataset.rqCard
    return true
  }
  if (!cur) return false
  const key = cur.dataset.rqCard
  const it = byKey(key)
  if (!it || it.resolved) return false
  state.rq.focus = key
  if (k === "a") { ack(key, true); return true }
  if (k === "e") {
    state.rq.open = state.rq.open === key ? null : key
    renderPage(); refocus()
    if (state.rq.open && !state.rq.sugg[key]) loadSugg(key)
    return true
  }
  const chips = chipsFor(it)
  const n = Number(e.key)
  if (n >= 1 && n <= chips.length) { saveNote(key, chips[n - 1]); return true }
  return false
}
