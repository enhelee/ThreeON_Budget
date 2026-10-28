import { api } from "./api.js"
import { busy, toast } from "./components/feedback.js"
import { loadForecastBench, loadForecastCapacity, loadForecastCompare, loadForecastRegular, loadForecastState } from "./data.js"
import { navigate, renderPage } from "./router.js"
import { state } from "./state.js"
import { $ } from "./util.js"
import { TOTAL } from "./views/forecast.js"
import { FV_LEVELS } from "./views/forecast_viz.js"

// ─────────────────────────────────────────────────────────────
// 5번 탭 핸들러 — views/forecast.js 가 그린 DOM(data-fc*)을 읽어 상태를 바꾸고 저장한다.
// main.js 의 click/change 리스너가 먼저 여기로 위임하고, 처리했으면(true) 멈춘다.
//
// 저장 계약: 표별 PUT /api/forecast/state/<table> 에 그 기준연도 한 벌을 통째로 보낸다.
// 「연도 기준정보」와 같이 손댄 표(state.fc.dirty)만 보낸다.
// ─────────────────────────────────────────────────────────────

const TABLE_URL = {grades: "grades", hot_parts: "hot-parts", factors: "factors", hq_temp: "hq-temp",
                   surprise: "surprise", hq_ratio: "hq-ratio", hq_master: "hq-master",
                   // 표준화 방향 반영(2026-10-26)
                   site_history: "site-history", site_event: "site-event", site_grade_eq: "site-grade-eq",
                   benchmark_rule: "benchmark-rule", actual_tag: "actual-tag", regular_contract: "regular-contract",
                   cri_rule: "cri-rule", investment_plan: "investment-plan",
                   site_capacity: "site-capacity", capacity_rule: "capacity-rule"}
const INT_FIELDS = new Set(["연도", "시작연도", "종료연도", "지급시차", "단가기준연도", "적용시작연도", "준공연도"])
const NUM_FIELDS = new Set(["금액", "연간비율", "계약체결금액", "표준금액", "기준단가"])
// 비우면 «없음»(null)인 칸 — 0 과 뜻이 다르다(보정률 0 ≠ 보정 없음)
const NULLABLE_FIELDS = new Set(["보정률", "조정액", "종료연도", "용량MW"])

const firstSite = () => state.fc.data?.sites?.[0] || ""
const firstAccount = () => (state.fc.data?.accounts?.["손익"] || [])[0] || ""
const NEW_ROW = {
  hot_parts: () => ({사업장: firstSite(), 연도: Number(state.fc.baseYear), 항목: "고온부품재생", 금액: 0}),
  factors: () => ({팩터명: "", 연간비율: 0, 활성: true}),
  hq_temp: () => ({사업명: "", 예산과목: firstAccount(), 연도: Number(state.fc.baseYear), 금액: 0}),
  surprise: () => ({사업장: firstSite(), 연도: Number(state.fc.baseYear), 예산과목: firstAccount(), 금액: 0, 사유: ""}),
  hq_ratio: () => ({사업장: firstSite(), 계약체결금액: 0}),
  hq_master: () => Object.fromEntries(state.fc.data.hq_master.columns.map((c, i) => [c, i < 3 ? "" : 0])),
  site_grade_eq: () => ({사업장: firstSite(), 연도: Number(state.fc.baseYear), 설비: "#1 GT", 등급: ""}),
  site_history: () => ({사업장: firstSite(), 시작연도: Number(state.fc.baseYear), 종료연도: null, 그룹: "", 설비: "", 비고: ""}),
  site_event: () => ({사업장: firstSite(), 연도: Number(state.fc.baseYear), 유형: "실적사용시작", 예산과목: "", 비고: ""}),
  benchmark_rule: () => ({사업장: firstSite(), 예산과목: firstAccount(), 등급: "*", 방식: "최근실적", 연도목록: "",
                          보정률: null, 참조지사: "", 참조등급: "", 조정액: null, 사유: ""}),
  regular_contract: () => ({사업장: firstSite(), 연도: Number(state.fc.baseYear), 항목: "GT LTSA",
                            예산과목: "수선유지비-열원정기유지보수", 금액: 0, 비고: ""}),
  cri_rule: () => ({사업장: firstSite(), 짝지사: "", 지급시차: 2, 기준단가: 0, 단가기준연도: Number(state.fc.baseYear) - 1, 활성: true, 비고: ""}),
  investment_plan: () => ({사업장: firstSite(), 연도: Number(state.fc.baseYear) + 1, 금액: 0, 비고: ""}),
  site_capacity: () => ({사업장: firstSite(), 설비: "", 구분: "발전설비", 용량MW: null, 준공연도: null, 비고: ""}),
  capacity_rule: () => ({사업장: firstSite(), 역할: "대상", 적용시작연도: Number(state.fc.baseYear), 용량MW: null, 정비제외연도: "", 비고: ""}),
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
  if (withBench || state.fc.tab === "bench") await Promise.all([loadForecastBench(), loadForecastRegular()])
  if (state.fc.compare || state.fc.manageTab === "ref") await loadForecastCompare()
  if (state.fc.manageTab === "capacity") await loadForecastCapacity()
  renderPage()
}

// ── 참고 엑셀(예산표준화 양식) — 미리보기 → 적용. 파일은 적용 때 한 번 더 보낸다(서버는 상태를 들고 있지 않음).
async function referenceUpload(file, apply) {
  busy(true, apply ? "참고 엑셀 적용 중..." : "참고 엑셀 읽는 중...")
  try {
    const fd = new FormData()
    fd.append("file", file)
    const res = await api(`/api/forecast/reference?base_year=${state.fc.baseYear}${apply ? "&apply=true" : ""}`, {method: "POST", body: fd})
    if (apply) {
      state.fc.refPreview = null; state.fc.refFile = null
      busy(false)
      await reload(true)
      toast(`참고 엑셀을 ${state.fc.baseYear}년 기준으로 적용했습니다 — 규칙 ${res.counts.benchmark_rule}건 · 표준금액 ${res.counts.reference_standard}건.`)
      return
    }
    state.fc.refPreview = res; state.fc.refFile = file
    renderPage()
  } catch (err) { toast(err.message) }
  finally { busy(false) }
}

// ── 저장 ─────────────────────────────────────────────────────

async function saveDirty() {
  const keys = [...state.fc.dirty]
  if (!keys.length) { toast("바뀐 내용이 없습니다."); return }
  busy(true, `${state.fc.baseYear}년 기준 전망 가정 저장 중...`)
  try {
    for (const key of keys) {
      if (key === "settings") {
        await api("/api/forecast/settings", json({base_year: state.fc.baseYear, values: state.fc.data.settings}))
        continue
      }
      const body = key === "hq_master"
        ? {columns: state.fc.data.hq_master.columns, rows: state.fc.data.hq_master.rows}
        : {rows: rowsOf(key)}
      await put(TABLE_URL[key], body)
    }
  } catch (err) { toast(`저장 실패: ${err.message}`); return }
  finally { busy(false) }
  state.fc.backtest = null            // 학습 기간이 바뀌었을 수 있다 — 다시 실행하게
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
      // 정비등급 양식(미래 일정)의 «전체 교체»는 그 파일의 해만 바꾼다 — 2016~ 과거 이력까지 지우지 않게
      const first = Math.min(...p.rows.map(r => Number(r.연도)))
      const past = p.kind === "schedule" ? d.grades.filter(r => Number(r.연도) < first) : []
      const rows = mode === "merge" ? [...d.grades, ...p.rows.filter(r => !have.has(`${r.사업장}|${r.연도}`))] : [...past, ...p.rows]
      await put("grades", {rows})
      // 정비등급 양식이면 설비별 등급(삼송 #1·#2 GT 등)도 — 지난 해 줄은 두고, 가져온 지사·설비의 같은 해만 바꾼다
      if (p.eq_rows?.length) {
        const key = r => `${r.사업장}|${r.설비}|${r.연도}`
        const got = new Set(p.eq_rows.map(key))
        const keep = mode === "merge" ? d.site_grade_eq : d.site_grade_eq.filter(r => !got.has(key(r)))
        const add = mode === "merge" ? p.eq_rows.filter(r => !new Set(d.site_grade_eq.map(key)).has(key(r))) : p.eq_rows
        await put("site-grade-eq", {rows: [...keep, ...add]})
      }
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

async function runBacktest() {
  busy(true, "백테스트 계산 중… 학습 기간 넷 × 시험 연도 다섯")
  try { state.fc.backtest = await api(`/api/forecast/backtest?base_year=${state.fc.baseYear}`) }
  catch (err) { toast(`백테스트 실패: ${err.message}`); return }
  finally { busy(false) }
  renderPage()
}

// ── 중장기 전망 한눈에 보기(views/forecast_viz.js) ───────────

/** 애니메이션 한 번만 — 그리고 나서 지워야 다음 renderPage 에서 다시 튀지 않는다. */
function fvGo({anim, origin} = {}) {
  const v = state.fc.viz
  v.anim = anim || null
  if (origin) v.origin = origin
  renderPage()
  v.anim = null
}

/** 누른 자리(단계 영역 기준 %)가 확대 기점. 키보드로 누르면(e.detail 0) 가운데. */
function fvOrigin(e) {
  const st = document.querySelector("[data-fvstage]")
  if (!st || !e.detail) return "50% 30%"
  const r = st.getBoundingClientRect()
  return `${((e.clientX - r.left) / r.width * 100).toFixed(1)}% ${((e.clientY - r.top) / r.height * 100).toFixed(1)}%`
}

function fvClick(e) {
  const v = state.fc.viz
  const mode = e.target.closest("[data-fvmode]")
  if (mode) { v.mode = mode.dataset.fvmode; fvGo({anim: "fade"}); return true }
  if (e.target.closest('[data-action="fv-present"]')) { fvPresent(!v.present); return true }
  const go = e.target.closest("[data-fvlevel]")
  if (!go) return false
  const d = go.dataset
  const from = FV_LEVELS.indexOf(v.level), to = FV_LEVELS.indexOf(d.fvlevel)
  const siteChange = d.fvsite !== undefined && d.fvsite !== state.fc.site
  if (d.fvsite !== undefined) state.fc.site = d.fvsite
  if (d.fvyear) v.year = Number(d.fvyear)
  if (d.fvacct !== undefined) v.acct = d.fvacct
  v.level = d.fvlevel
  // 깊어지거나 더 좁은 범위(지사)로 가면 확대, 얕아지거나 전사로 나오면 축소, 같은 단계 안 이동은 페이드
  const anim = to > from || (siteChange && d.fvsite !== TOTAL) ? "zoom-in" : to < from || siteChange ? "zoom-out" : "fade"
  fvGo({anim, origin: fvOrigin(e)})
  return true
}

/** 발표 모드 — 화면 전체(가능하면 Fullscreen API) + 패널만 크게. */
function fvPresent(on) {
  state.fc.viz.present = on
  if (on) document.documentElement.requestFullscreen?.().catch(() => {})
  else if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {})
  fvGo({anim: "fade"})
}
document.addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement && state.fc.viz.present) { state.fc.viz.present = false; if (state.view === "forecast") renderPage() }
})

/** 발표 모드 키 — ←→ 연도, ↑ 한 단계 위로, Esc 끝내기. 처리했으면 true. */
export function fcKey(e) {
  const v = state.fc.viz
  if (state.view !== "forecast" || state.fc.tab !== "table" || !v.present) return false
  if (e.target.matches?.("input, select, textarea")) return false
  if (e.key === "Escape") { fvPresent(false); return true }
  const years = (state.fc.table?.years || []).map(Number)
  if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && years.length) {
    const i = years.indexOf(v.year) + (e.key === "ArrowRight" ? 1 : -1)
    if (i < 0 || i >= years.length) return true
    v.year = years[i]
    if (v.level === "map") v.level = "year"
    fvGo({anim: "fade"}); return true
  }
  if (e.key === "ArrowUp") {
    const i = FV_LEVELS.indexOf(v.level)
    if (i > 0) { v.level = FV_LEVELS[i - 1]; fvGo({anim: "zoom-out", origin: "50% 30%"}) }
    else if (state.fc.site !== TOTAL) { state.fc.site = TOTAL; fvGo({anim: "zoom-out", origin: "50% 30%"}) }
    return true
  }
  return false
}

// ── 이벤트 위임 ──────────────────────────────────────────────

export async function fcClick(e) {
  if (state.view !== "forecast") return false
  const tab = e.target.closest("[data-fctab]")
  if (tab) { state.fc.tab = tab.dataset.fctab; state.fc.preview = null; await navigate("forecast"); return true }
  // 기준정보 안쪽 탭 — 다시 불러오지 않고 그리기만(손댄 값은 state.fc.data 에 남아 있다)
  const mtab = e.target.closest("[data-fcmtab]")
  if (mtab) {
    state.fc.manageTab = mtab.dataset.fcmtab
    if (state.fc.manageTab === "ref" && !state.fc.compare) {
      busy(true, "참고 엑셀과 대조 중...")
      try { await loadForecastCompare() } catch (err) { toast(err.message) } finally { busy(false) }
    }
    if (state.fc.manageTab === "capacity" && !state.fc.capacity) {
      busy(true, "용량 규칙 계산 중...")
      try { await loadForecastCapacity() } catch (err) { toast(err.message) } finally { busy(false) }
    }
    renderPage(); return true
  }
  const bview = e.target.closest("[data-fcbview]")
  if (bview) { state.fc.benchView = bview.dataset.fcbview; renderPage(); return true }
  if (fvClick(e)) return true
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
  // 양식 내보내기(6-7) — 파일은 그때그때 만들어 내려온다(저장 안 함). 세션 쿠키가 따라가므로 location 으로.
  const ex = e.target.closest("[data-fcexport]")
  if (ex) {
    toast("양식을 채우는 중… 시트가 많아 몇 초 걸립니다.")
    window.location.href = `/api/forecast/export?kind=${ex.dataset.fcexport}&base_year=${state.fc.baseYear}`
    return true
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
  if (act === "fc-ref-apply") { if (state.fc.refFile) await referenceUpload(state.fc.refFile, true); return true }
  if (act === "fc-backtest") { await runBacktest(); return true }
  if (act === "fc-ref-cancel") { state.fc.refPreview = null; state.fc.refFile = null; renderPage(); return true }
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
    if (f && kind === "reference") await referenceUpload(f, false)
    else if (f && kind) await uploadPreview(kind, f)
    return true
  }
  if (t.matches("[data-fcrange]")) { state.fc.showRange = t.checked; renderPage(); return true }
  if (t.matches("[data-fcsetting]")) {
    state.fc.data.settings = {...(state.fc.data.settings || {}), [t.dataset.fcsetting]: t.value}
    markDirty("settings"); return true
  }
  if (t.matches("[data-fccmpdiff]")) { state.fc.cmpOnlyDiff = t.checked; renderPage(); return true }
  if (t.dataset.fctag) {
    // 사업별 정기비용 유형 — 바꾼 것만 actual_tag 에 둔다(자동 판정과 같아져도 사람이 확정한 값으로 남김).
    const [site, year, acct, ...rest] = t.dataset.fctag.split("|")
    const name = rest.join("|")
    const rows = state.fc.data.actual_tag
    const i = rows.findIndex(r => r.사업장 === site && Number(r.연도) === Number(year) && r.예산과목 === acct && r.사업명 === name)
    if (i >= 0) rows[i].유형 = t.value
    else rows.push({사업장: site, 연도: Number(year), 예산과목: acct, 사업명: name, 유형: t.value})
    t.closest("td")?.classList.add("bg-warn-bg")
    markDirty("actual_tag")
    return true
  }
  if (t.matches("[data-fcgroup]")) { state.fc.benchGroup = t.value; renderPage(); return true }
  if (t.matches("[data-fcsite]")) { state.fc.site = t.value || TOTAL; fvGo({anim: "fade"}); return true }
  if (t.matches("[data-fvacctsel]")) { state.fc.viz.acct = t.value; fvGo({anim: "fade"}); return true }
  const bench = t.dataset.fcbench
  if (bench) {
    // 편집만 기록한다 — 저장 버튼에서 기존 방식·수정값과 병합해 두 표를 한 번에 보낸다.
    if (bench === "method") state.fc.benchEdits.methods[t.dataset.key] = t.value
    else state.fc.benchEdits.overrides[t.dataset.key] = Number(t.value)
    const btn = document.querySelector('[data-action="fc-save-bench"]')
    const n = Object.keys(state.fc.benchEdits.methods).length + Object.keys(state.fc.benchEdits.overrides).length
    if (btn) { btn.disabled = false; btn.textContent = `변경 저장 (${n}건)` }
    t.closest("td")?.classList.add("bg-warn-bg")
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
  else if (NULLABLE_FIELDS.has(f)) v = t.value === "" ? null : Number(t.value)
  else if (NUM_FIELDS.has(f) || (fc === "hq_master" && t.type === "number")) v = t.value === "" ? 0 : Number(t.value)
  else v = t.value
  row[f] = v
  markDirty(fc)
  return true
}
