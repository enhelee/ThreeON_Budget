import { api } from "./api.js"
import { busy, toast } from "./components/feedback.js"
import { loadForecastBench, loadForecastState } from "./data.js"
import { navigate, renderPage } from "./router.js"
import { state } from "./state.js"
import { $ } from "./util.js"
import { TOTAL } from "./views/forecast.js"

// ─────────────────────────────────────────────────────────────
// 5번 탭 핸들러 — views/forecast.js 가 그린 DOM(data-fc*)을 읽어 상태를 바꾸고 저장한다.
// main.js 의 click/change 리스너가 먼저 여기로 위임하고, 처리했으면(true) 멈춘다.
//
// 저장 계약: 표별 PUT /api/forecast/state/<table> 에 그 기준연도 한 벌을 통째로 보낸다.
// 「연도 기준정보」와 같이 손댄 표(state.fc.dirty)만 보낸다.
// ─────────────────────────────────────────────────────────────

const TABLE_URL = {grades: "grades", hot_parts: "hot-parts", factors: "factors", hq_temp: "hq-temp",
                   surprise: "surprise", hq_ratio: "hq-ratio", hq_master: "hq-master"}
const INT_FIELDS = new Set(["연도"])
const NUM_FIELDS = new Set(["금액", "연간비율", "계약체결금액", "표준금액"])

const firstSite = () => state.fc.data?.sites?.[0] || ""
const firstAccount = () => (state.fc.data?.accounts?.["손익"] || [])[0] || ""
const NEW_ROW = {
  hot_parts: () => ({사업장: firstSite(), 연도: Number(state.fc.baseYear), 항목: "고온부품재생", 금액: 0}),
  factors: () => ({팩터명: "", 연간비율: 0, 활성: true}),
  hq_temp: () => ({사업명: "", 예산과목: firstAccount(), 연도: Number(state.fc.baseYear), 금액: 0}),
  surprise: () => ({사업장: firstSite(), 연도: Number(state.fc.baseYear), 예산과목: firstAccount(), 금액: 0, 사유: ""}),
  hq_ratio: () => ({사업장: firstSite(), 계약체결금액: 0}),
  hq_master: () => Object.fromEntries(state.fc.data.hq_master.columns.map((c, i) => [c, i < 3 ? "" : 0])),
}

const json = body => ({method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)})

function put(table, body) {
  return api(`/api/forecast/state/${table}`, json({base_year: state.fc.baseYear, ...body}))
}

function rowsOf(key) {
  const d = state.fc.data
  return key === "hq_master" ? d.hq_master.rows : d[key]
}

function markDirty(key) {
  state.fc.dirty.add(key)
  const btn = $("#fcSaveBtn")
  if (btn) { btn.disabled = false; btn.textContent = `저장 (${state.fc.dirty.size}표)` }
}

async function reload(withBench) {
  await loadForecastState()
  if (withBench || state.fc.tab === "bench") await loadForecastBench()
  renderPage()
}

// ── 저장 ─────────────────────────────────────────────────────

async function saveDirty() {
  const keys = [...state.fc.dirty]
  if (!keys.length) { toast("바뀐 내용이 없습니다."); return }
  busy(true, `${state.fc.baseYear}년 기준 전망 가정 저장 중...`)
  try {
    for (const key of keys) {
      const body = key === "hq_master"
        ? {columns: state.fc.data.hq_master.columns, rows: state.fc.data.hq_master.rows}
        : {rows: rowsOf(key)}
      await put(TABLE_URL[key], body)
    }
  } catch (err) { toast(`저장 실패: ${err.message}`); return }
  finally { busy(false) }
  await reload()
  toast(`${keys.length}개 표를 ${state.fc.baseYear}년 기준으로 저장했습니다 — 표준화·전망은 다음 조회에 반영됩니다.`)
}

async function saveBench() {
  const d = state.fc.data, ed = state.fc.benchEdits
  const methods = {}
  d.methods.forEach(r => { methods[`${r.사업장}|${r.예산과목}`] = r.방식 })
  Object.assign(methods, ed.methods)
  const overrides = {}
  d.overrides.forEach(r => { overrides[`${r.사업장}|${r.예산과목}|${r.등급}`] = r.표준금액 })
  Object.assign(overrides, ed.overrides)
  busy(true, "산출방식·표준금액 저장 중...")
  try {
    await put("methods", {rows: Object.entries(methods).map(([k, v]) => { const [s, a] = k.split("|"); return {사업장: s, 예산과목: a, 방식: v} })})
    await put("overrides", {rows: Object.entries(overrides).map(([k, v]) => { const [s, a, g] = k.split("|"); return {사업장: s, 예산과목: a, 등급: g, 표준금액: v} })})
  } catch (err) { toast(`저장 실패: ${err.message}`); return }
  finally { busy(false) }
  await reload(true)
  toast("표준화 변경을 저장했습니다 — 표가 다시 계산되었습니다.")
}

// ── 기준연도 ─────────────────────────────────────────────────

async function addBaseYear() {
  const known = [...state.fc.baseYears, state.fc.baseYear].filter(Boolean).map(Number)
  const suggest = String(Math.max(...known) + 1)
  const to = (prompt(`새 전망 기준연도를 입력하세요. ${state.fc.baseYear}년 기준 가정(정비등급·팩터·본사배분 등)을 복사해 시작합니다.`, suggest) || "").trim()
  if (!to) return
  if (!/^\d{4}$/.test(to)) { toast("기준연도는 4자리 숫자로 입력하세요."); return }
  if (to === state.fc.baseYear) { toast("지금 보고 있는 기준연도입니다."); return }
  busy(true, `${state.fc.baseYear} → ${to}년 기준 가정 복사 중...`)
  try {
    await api("/api/forecast/copy-base-year", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({from_year: state.fc.baseYear, to_year: to})})
    toast(`${to}년 기준 가정을 ${state.fc.baseYear}년 사본으로 만들었습니다.`)
  } catch (err) {
    if (err.status === 409) toast(`${to}년 기준 가정을 이미 손댔습니다 — 그대로 전환합니다.`)
    else { toast(`복사 실패: ${err.message}`); busy(false); return }
  } finally { busy(false) }
  state.fc.baseYear = to
  state.fc.preview = null
  await navigate("forecast")
}

// ── 가져오기 ─────────────────────────────────────────────────

async function uploadPreview(kind, file) {
  busy(true, "엑셀 읽는 중...")
  try {
    const fd = new FormData()
    fd.append("file", file)
    const res = await api(`/api/forecast/import?kind=${kind}&base_year=${state.fc.baseYear}`, {method: "POST", body: fd})
    state.fc.preview = res
    renderPage()
    document.getElementById("fcPreview")?.scrollIntoView({behavior: "smooth", block: "start"})
  } catch (err) { toast(err.message) }
  finally { busy(false) }
}

async function applyPreview(mode) {
  const p = state.fc.preview
  if (!p) return
  const d = state.fc.data
  busy(true, "가져온 자료 저장 중...")
  try {
    if (p.kind === "grades" || p.kind === "schedule") {
      const have = new Set(d.grades.map(r => `${r.사업장}|${r.연도}`))
      const rows = mode === "merge" ? [...d.grades, ...p.rows.filter(r => !have.has(`${r.사업장}|${r.연도}`))] : p.rows
      await put("grades", {rows})
    } else if (p.kind === "hot-parts") {
      const have = new Set(d.hot_parts.map(r => `${r.사업장}|${r.연도}|${r.항목}`))
      const rows = mode === "merge" ? [...d.hot_parts, ...p.rows.filter(r => !have.has(`${r.사업장}|${r.연도}|${r.항목}`))] : p.rows
      await put("hot-parts", {rows})
    } else if (p.kind === "hq-master") {
      await put("hq-master", {columns: p.columns, rows: p.rows, ratio_rows: p.ratio_rows})
    }
  } catch (err) { toast(`저장 실패: ${err.message}`); return }
  finally { busy(false) }
  state.fc.preview = null
  await reload()
  toast("가져온 자료를 저장했습니다.")
}

// ── 이벤트 위임 ──────────────────────────────────────────────

export async function fcClick(e) {
  if (state.view !== "forecast") return false
  const tab = e.target.closest("[data-fctab]")
  if (tab) { state.fc.tab = tab.dataset.fctab; state.fc.preview = null; await navigate("forecast"); return true }
  const add = e.target.closest("[data-fcadd]")
  if (add) {
    const key = add.dataset.fcadd
    rowsOf(key).push(NEW_ROW[key]())
    markDirty(key); renderPage(); return true
  }
  const del = e.target.closest("[data-fcdel]")
  if (del) {
    const key = del.dataset.fcdel
    rowsOf(key).splice(Number(del.dataset.idx), 1)
    markDirty(key); renderPage(); return true
  }
  const imp = e.target.closest("[data-fcimport]")
  if (imp) {
    const input = $("#fcImportFile")
    input.dataset.kind = imp.dataset.fcimport
    input.click()
    return true
  }
  const act = e.target.closest("[data-action]")?.dataset.action
  if (act === "fc-add-base") { await addBaseYear(); return true }
  if (act === "fc-save") { await saveDirty(); return true }
  if (act === "fc-save-bench") { await saveBench(); return true }
  if (act === "fc-apply-merge") { await applyPreview("merge"); return true }
  if (act === "fc-apply-replace") { await applyPreview("replace"); return true }
  if (act === "fc-cancel-preview") { state.fc.preview = null; renderPage(); return true }
  return false
}

export async function fcChange(e) {
  if (state.view !== "forecast") return false
  const t = e.target
  if (t.matches("[data-fcbase]")) {
    state.fc.baseYear = t.value; state.fc.preview = null; state.fc.dirty = new Set()
    await navigate("forecast"); return true
  }
  if (t.id === "fcImportFile") {
    const f = t.files[0], kind = t.dataset.kind
    t.value = ""
    if (f && kind) await uploadPreview(kind, f)
    return true
  }
  if (t.matches("[data-fcgroup]")) { state.fc.benchGroup = t.value; renderPage(); return true }
  if (t.matches("[data-fcsite]")) { state.fc.site = t.value || TOTAL; renderPage(); return true }
  const bench = t.dataset.fcbench
  if (bench) {
    // 편집만 기록한다 — 저장 버튼에서 기존 방식·수정값과 병합해 두 표를 한 번에 보낸다.
    if (bench === "method") state.fc.benchEdits.methods[t.dataset.key] = t.value
    else state.fc.benchEdits.overrides[t.dataset.key] = Number(t.value)
    const btn = document.querySelector('[data-action="fc-save-bench"]')
    const n = Object.keys(state.fc.benchEdits.methods).length + Object.keys(state.fc.benchEdits.overrides).length
    if (btn) { btn.disabled = false; btn.textContent = `변경 저장 (${n}건)` }
    t.closest("td")?.classList.add("bg-amber-50")
    return true
  }
  const fc = t.dataset.fc
  if (!fc) return false
  if (fc === "grade-cell") {
    // 넓은 표의 칸 하나 = 긴 표의 행 하나. 비우면 그 (지사,연도) 이력을 지운다.
    const site = t.dataset.site, year = Number(t.dataset.year), v = t.value.trim()
    const rows = state.fc.data.grades
    const i = rows.findIndex(r => r.사업장 === site && Number(r.연도) === year)
    if (!v) { if (i >= 0) rows.splice(i, 1) }
    else if (i >= 0) rows[i].등급 = v
    else rows.push({사업장: site, 연도: year, 등급: v})
    markDirty("grades")
    return true
  }
  const rows = rowsOf(fc)
  if (!rows) return false
  const row = rows[Number(t.dataset.idx)]
  if (!row) return false
  const f = t.dataset.field
  let v
  if (t.type === "checkbox") v = t.checked
  else if (INT_FIELDS.has(f)) v = t.value === "" ? null : parseInt(t.value, 10)
  else if (NUM_FIELDS.has(f) || (fc === "hq_master" && t.type === "number")) v = t.value === "" ? 0 : Number(t.value)
  else v = t.value
  row[f] = v
  markDirty(fc)
  return true
}
