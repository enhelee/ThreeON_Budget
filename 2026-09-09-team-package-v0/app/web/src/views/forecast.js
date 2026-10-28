import { charSay } from "../components/characters.js"
import { emptyState } from "../components/widgets.js"
import { state } from "../state.js"
import { esc, fmt } from "../util.js"
import { baseYearRule, fcVizHtml } from "./forecast_viz.js"

// ─────────────────────────────────────────────────────────────
// 5번 탭 — 예산 표준화(3단계) · 중장기 전망(4단계)  (#/forecast)
//
// Phase 6-6. 전망 앱(Streamlit) iframe 을 걷어내고 이 앱의 API(/api/forecast/*)로 그린다.
//
//   기준연도(base_year) — «어느 해에 세운 가정인가». 헤더의 대상연도(계획·실적 분석 연도)
//   와 다른 축이라 이 화면에 선택기를 따로 둔다. 기준연도마다 정비등급·고온부품·본사배분·
//   팩터·임시사업·돌발사업이 한 벌씩이고, 「＋기준연도」는 직전 벌을 복사해 시작한다.
//
//   하위 탭 셋 — 기준정보(가정 6종 편집·엑셀 가져오기) · 표준화(산출방식·표준금액 편집) ·
//   중장기 전망(지사별 10개년 표). 편집은 「연도 기준정보」와 같은 방식이다: 입력을 상태에
//   담고 손댄 표만 저장 버튼에서 보낸다. 핸들러는 forecast_actions.js.
//
//   단위는 천원(앱 표준). v2 는 원·억원이었다.
// ─────────────────────────────────────────────────────────────

const TABS = [["manage", "기준정보 (가정)"], ["bench", "표준화 (3단계)"], ["table", "중장기 전망 (4단계)"]]
// 기준정보 안쪽 탭 — [키, 이름, 그 탭에 든 표(저장 안 된 표가 있으면 탭에 점)]
const MANAGE_TABS = [["ref", "참고 엑셀·대조", []], ["grades", "정비등급", ["grade_plan", "grades", "site_grade_eq"]],
                     ["factor", "고온부품", ["hot_parts", "hot_parts_contract", "factors"]],
                     ["capacity", "설비용량·신규표준", ["site_capacity", "capacity_rule"]],
                     ["history", "지사 연혁·구조변화", ["site_history", "site_event"]],
                     ["regular", "정기계약·CRI·투자", ["regular_contract", "cri_rule", "investment_plan"]],
                     ["hq", "본사 배분·임시사업", ["hq_master", "hq_ratio", "hq_temp"]], ["surprise", "지사 돌발사업", ["surprise"]],
                     ["learn", "학습 기간·백테스트", ["settings"]]]
const BENCH_VIEWS = [["std", "표준금액"], ["rules", "산정 규칙"], ["regular", "정기비용 분리"]]
const TAG_LABEL = {기타: "기타(표준화)", LTSA: "LTSA", CRI: "CRI", 고온부품재생: "고온부품재생"}
const HOT_ITEMS = ["고온부품재생", "신품구매"]
export const METHODS = ["등급별 평균", "최근실적", "3개년 평균", "5개년 평균"]
const GROUPS = ["중대형CHP", "소형CHP", "DH", "본사"]
export const TOTAL = "__total__"

const num = v => (v === null || v === undefined) ? "" : v

function accountsAll() {
  const a = state.fc.data?.accounts || {}
  return [...(a["손익"] || []), ...(a["자본"] || [])]
}

function sel(opts, value, attrs, labels = {}) {
  return `<select class="control" ${attrs}>${opts.map(o => `<option value="${esc(o)}" ${String(o) === String(value) ? "selected" : ""}>${esc(labels[o] ?? o)}</option>`).join("")}</select>`
}

/** 내장 양식은 «26년» 라벨이 박힌 2026년 기준 참고 양식이다. 다른 기준연도로 내보내면 서버가 시트명·연도
 *  헤더·수식 참조를 그 기준연도로 옮긴 뒤 채운다(forecast_export.rebase_workbook_years). */
function exportNote() {
  const by = String(state.fc.baseYear)
  if (by === "2026") return ""
  return `<p class="mt-2 text-xs text-sub">ℹ️ 내장 양식은 2026년 기준 참고 양식입니다. ${esc(by)}년 기준으로 내려받으면 «26년 본사 원가분배»→«${esc(by.slice(2))}년 본사 원가분배»처럼 시트명·연도 헤더·수식 참조를 ${esc(by)}년 기준으로 옮겨 채웁니다. 전년 실측치 같은 참고 블록은 양식 그대로입니다.</p>`
}

/** 접기 단추 — 오른쪽 위. 접으면 제목 한 줄만 남는다(2026-10-28 사용자 요청: 아래로 긴 내용은 한 줄로). */
const foldBtn = (attr, open, what) => `<button class="btn-secondary min-h-[32px] shrink-0 px-3 text-xs" ${attr} aria-expanded="${open}" title="${open ? `${what} 한 줄로 접기` : `${what} 펼치기`}">${open ? "접기 ▴" : "펼치기 ▾"}</button>`

function panel(title, help, body, key) {
  const dirty = key && state.fc.dirty.has(key)
  const open = !(state.fc.closedPanels || new Set()).has(title)
  return `<article class="panel overflow-hidden">
    <div class="flex items-start justify-between gap-3 ${open ? "border-b border-line p-5 sm:p-6" : "px-5 py-3 sm:px-6"}">
      <div class="min-w-0"><h3 class="section-title">${esc(title)}${help ? ` <span class="cursor-help align-middle text-sm font-normal text-tri" title="${esc(String(help).replace(/<[^>]+>/g, ""))}" aria-label="설명">ⓘ</span>` : ""} ${dirty ? '<span class="badge bg-warn-bg text-warn">저장 안 됨</span>' : ""}</h3></div>
      ${foldBtn(`data-fcpanel="${esc(title)}"`, open, "이 표")}
    </div>${open ? body : ""}</article>`
}

// ── 헤더: 기준연도 · 탭 ──────────────────────────────────────

function header() {
  const fc = state.fc
  const years = [...new Set([...fc.baseYears, fc.baseYear])].filter(Boolean).sort()
  const locked = fc.lockedYears?.length ? fc.lockedYears.join("·") : "없음"
  return `
  <section class="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
    <div>
      <p class="text-sm font-semibold text-ink">STAGE 5</p>
      <h2 class="mt-1 font-hanan text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">예산 표준화 · 중장기 전망</h2>
    </div>
    <div class="flex flex-wrap items-end gap-2">
      <label class="block"><span class="field-label">전망 기준연도</span>
        <select class="control" data-fcbase>${years.map(y => `<option value="${esc(y)}" ${y === fc.baseYear ? "selected" : ""}>${esc(y)}년 기준${fc.baseYears.includes(y) ? "" : " (아직 저장된 가정 없음)"}</option>`).join("")}</select></label>
      <button class="btn-secondary" data-action="fc-add-base" title="직전 기준연도의 가정을 복사해 새 기준연도를 만듭니다">＋기준연도</button>
    </div>
  </section>
  ${fc.lockedYears?.length
    ? charSay({who: "yc", title: "마감된 숫자로만 다음 10년을 그려요.",
        body: `마감된 ${esc(locked)}년 실적으로 표준금액을 만들고, ${esc(fc.baseYear)}년 기준으로 10개년을 전망해요.`})
    : charSay({who: "yc", tone: "warn", title: "아직 마감된 연도가 없어요.",
        body: "2단계에서 분석을 실행하고 설정에서 그 연도를 마감하면, 그 숫자로 전망을 시작해요."})}
  <div class="flex flex-wrap gap-2">${TABS.map(([k, l]) => `<button class="${fc.tab === k ?"btn-primary" : "btn-secondary"}" data-fctab="${k}">${esc(l)}</button>`).join("")}</div>`
}

// ── 기준정보(가정) 탭 ────────────────────────────────────────

function cellInput(key, i, c, v) {
  const a = `data-fc="${key}" data-idx="${i}" data-field="${esc(c.f)}"`
  if (c.type === "select") return sel(c.options, v ?? "", a, c.labels || {"": "(빈 값)"})
  if (c.type === "bool") return `<input type="checkbox" ${a} ${v ? "checked" : ""}>`
  if (c.type === "num") return `<input class="control fc-num" type="number" step="any" ${a} value="${esc(num(v))}">`
  if (c.type === "int") return `<input class="control fc-int" type="number" step="1" ${a} value="${esc(num(v))}">`
  return `<input class="control" ${a} value="${esc(num(v))}">`
}

// 줄이 많은 표는 «지사(+항목·설비)» 묶음으로 — 묶음마다 오른쪽 ▾ 로 한 줄 요약 ↔ 펼침. 4줄 이상 묶음은 처음엔 접힌다.
const GROUP_MIN_ROWS = 7, GROUP_FOLD_AT = 4
function groupKeyOf(cols) {
  const fs = cols.map(c => c.f)
  if (!fs.includes("사업장")) return null
  return ["사업장", ...["항목", "설비"].filter(f => fs.includes(f)).slice(0, 1)]
}

/** 긴 표 편집기 — 행 추가·삭제·셀 편집. cols: [{f, label, type, options}] */
function longTable(key, cols, rows, empty) {
  const head = cols.map(c => `<th class="px-3 py-2 ${c.type ==="num" ? "text-right" : ""}">${esc(c.label)}</th>`).join("") + '<th class="w-16"></th>'
  const line = (r, i) => `<tr>${cols.map(c => `<td class="px-2 py-1">${cellInput(key, i, c, r[c.f])}</td>`).join("")}
      <td class="px-2 py-1 text-right"><button class="btn-secondary" data-fcdel="${key}" data-idx="${i}">삭제</button></td></tr>`
  const gk = rows.length >= GROUP_MIN_ROWS ? groupKeyOf(cols) : null
  let body
  if (!gk) body = rows.map(line).join("")
  else {
    const groupBy = fs => {
      const m = new Map()
      rows.forEach((r, i) => {
        const k = fs.map(f => r[f] ?? "").join(" · ")
        if (!m.has(k)) m.set(k, [])
        m.get(k).push(i)
      })
      return m
    }
    // 지사+설비가 줄마다 다르면(설비 현황) 지사로만 묶는다
    let groups = groupBy(gk)
    if (gk.length > 1 && Math.max(...[...groups.values()].map(v => v.length)) < 2) groups = groupBy(["사업장"])
    const opened = state.fc.groupOpen || {}
    const money = cols.find(c => c.f === "금액")
    body = [...groups].map(([k, idx]) => {
      if (idx.length < 2) return idx.map(i => line(rows[i], i)).join("")
      const id = `${key}|${k}`
      const open = opened[id] ?? idx.length < GROUP_FOLD_AT
      const years = idx.map(i => Number(rows[i].연도)).filter(Boolean)
      const span = years.length ? ` · ${Math.min(...years)}~${Math.max(...years)}` : ""
      const total = money ? ` · 금액 합계 ${fmt(idx.reduce((s, i) => s + Number(rows[i].금액 || 0), 0))}` : ""
      return `<tr class="bg-subtle"><td class="px-3 py-2 text-sm" colspan="${cols.length + 1}"><div class="sticky left-3 inline-flex max-w-[calc(100vw-8rem)] flex-wrap items-center gap-x-2 gap-y-1">${foldBtn(`data-fcgrp="${esc(id)}" data-open="${open}"`, open, "이 묶음")}<b class="text-ink">${esc(k)}</b><span class="text-sub">${idx.length}줄${span}${total}</span></div></td></tr>${open ? idx.map(i => line(rows[i], i)).join("") : ""}`
    }).join("")
  }
  return `<div class="overflow-x-auto p-5"><table class="w-full"><thead class="table-head"><tr>${head}</tr></thead>
    <tbody class="divide-y divide-line-subtle">${body || `<tr><td class="table-cell text-tri" colspan="${cols.length + 1}">${esc(empty || "없음")}</td></tr>`}</tbody></table>
    <button class="btn-secondary mt-3" data-fcadd="${key}">＋ 행 추가</button></div>`
}

// 정비등급 — 기준연도~10년은 사용자 엑셀 양식(발전설비·DH, 지사·설비 줄) 그대로(2026-10-28), 과거는 지사 한 줄 이력
const GRADE_COLOR = {TI: "#00B0F0", HGPI: "#00B0F0", CI: "#00B0F0", MI: "#FFFF00"}
const gradeStyle = v => GRADE_COLOR[v] ? `background:${GRADE_COLOR[v]};` : ""

function gradePlanTable() {
  const gp = state.fc.gradePlan
  if (!gp) return '<p class="p-5 text-sm text-tri">정비등급 양식을 불러오는 중입니다.</p>'
  let group = null, label = null
  const body = gp.lines.map((ln, i) => {
    const sep = ln.group !== group ? `<tr class="bg-subtle"><td class="fc-stick bg-subtle px-3 py-1.5 text-xs font-bold text-sub" colspan="${gp.years.length + 1}">${esc(ln.group || "")}</td></tr>` : ""
    group = ln.group
    const first = ln.label !== label
    label = ln.label
    const name = `${first ? `<b class="text-ink">${esc(ln.label)}</b>` : '<span class="text-tri">〃</span>'}${ln.unit ? ` <span class="text-xs text-sub">${esc(ln.unit)}</span>` : ""}`
    return `${sep}<tr><td class="fc-stick table-cell bg-white">${name}</td>${gp.years.map(y => {
      const v = ln.values[String(y)] || ""
      return `<td class="px-1 py-1"><input class="control fc-grade text-center" style="${gradeStyle(v)}" data-fc="gp-cell" data-idx="${i}" data-year="${y}" value="${esc(v)}"></td>`
    }).join("")}</tr>`
  }).join("")
  return `<div class="overflow-x-auto p-5"><table class="w-full"><thead class="table-head"><tr><th class="fc-stick bg-subtle px-3 py-2">지사 · 설비</th>${gp.years.map(y => `<th class="px-1 py-2 text-center">${y}</th>`).join("")}</tr></thead>
    <tbody class="divide-y divide-line-subtle">${body}</tbody></table>
    <p class="mt-2 text-xs text-sub"><span class="mr-1 inline-block h-3 w-5 rounded-sm align-middle" style="background:#00B0F0"></span>TI·HGPI·CI <span class="ml-3 mr-1 inline-block h-3 w-5 rounded-sm align-middle" style="background:#FFFF00"></span>MI · «-»·«준공»은 등급 아님</p></div>`
}

function gradesPanel(d) {
  const by = Number(state.fc.baseYear)
  const years = [...new Set(d.grades.map(r => Number(r.연도)))].filter(y => y < by).sort()
  const sites = [...new Set([...d.sites, ...d.grades.filter(r => Number(r.연도) < by).map(r => r.사업장)])]
  const cell = {}
  d.grades.forEach(r => { cell[`${r.사업장}|${r.연도}`] = r.등급 })
  const plan = panel(`정비등급 ${by}~${by + 9} (엑셀 양식 그대로)`, "«26~35년 전지사 정비등급» 양식과 같은 줄 — 화면에서 고친 값·올린 엑셀·내려받는 엑셀이 같은 규칙으로 읽힘 · 줄이 둘 이상인 지사(삼송·동탄·대구·강남)는 설비별로 저장되고 대표 등급은 GT 어휘 줄", `
    <div class="flex flex-wrap gap-2 p-5 pb-0">
      <button class="btn-secondary" data-fcimport="schedule" title="전지사 정비등급 양식(한 해 한 열) 또는 중장기예산 양식의 정기점검보수공사 일정 시트">정비등급 양식에서 가져오기</button>
      <button class="btn-secondary" data-fcexport="schedule" title="전지사 정비등급 양식 그대로, 등급 칸만 지금 저장된 값 — 고쳐서 다시 올릴 수 있습니다">정비등급 양식으로 내려받기 (xlsx)</button>
    </div>${gradePlanTable()}`, "grade_plan")
  const past = years.length ? panel(`정비등급 이력 (~${by - 1})`, "지난 해의 대표 등급(표준화 참고 엑셀) — 표준금액을 등급별로 나누는 데 씀 · 빈 칸 = 그 해 이력 없음", `
    <div class="flex flex-wrap gap-2 p-5 pb-0"><button class="btn-secondary" data-fcimport="grades">표준화 참고 엑셀에서 가져오기</button></div>
    <div class="overflow-x-auto p-5"><table class="w-full"><thead class="table-head"><tr><th class="fc-stick bg-subtle px-3 py-2">지사</th>${years.map(y => `<th class="px-1 py-2 text-center">${y}</th>`).join("")}</tr></thead>
      <tbody class="divide-y divide-line-subtle">${sites.map(s => `<tr><td class="fc-stick table-cell bg-white font-semibold text-ink">${esc(s)}</td>${years.map(y =>
        `<td class="px-1 py-1 text-center"><input class="control fc-grade" data-fc="grade-cell" data-site="${esc(s)}" data-year="${y}" value="${esc(cell[`${s}|${y}`] || "")}"></td>`).join("")}</tr>`).join("")}</tbody></table></div>`, "grades") : ""
  return plan + past
}

function hqMasterPanel(d) {
  const cols = d.hq_master.columns
  const rows = d.hq_master.rows
  const body = rows.map((r, i) => `<tr>${cols.map((c, j) => `<td class="px-2 py-1">${cellInput("hq_master", i, {f: c, type: j < 3 ? "text" : "num"}, r[c])}</td>`).join("")}
      <td class="px-2 py-1 text-right"><button class="btn-secondary" data-fcdel="hq_master" data-idx="${i}">삭제</button></td></tr>`).join("")
  return panel("본사 원가분배 마스터", "양식 금액을 그대로 사용 · 배분비율(계약체결금액)로 본사 임시사업을 나눔", `
    <div class="flex flex-wrap gap-2 p-5 pb-0">
      <button class="btn-secondary" data-fcimport="hq-master">본사 원가분배 엑셀에서 가져오기 (마스터 + 배분비율)</button>
      <button class="btn-secondary" data-fcexport="hq-master">현재값이 채워진 양식 내려받기</button>
    </div>
    <div class="overflow-x-auto p-5"><table class="w-full"><thead class="table-head"><tr>${cols.map(c => `<th class="px-3 py-2">${esc(c)}</th>`).join("")}<th class="w-16"></th></tr></thead>
      <tbody class="divide-y divide-line-subtle">${body || `<tr><td class="table-cell text-tri" colspan="${cols.length + 1}">마스터가 없습니다 — 엑셀에서 가져오세요.</td></tr>`}</tbody></table>
      <button class="btn-secondary mt-3" data-fcadd="hq_master">＋ 행 추가</button></div>
    <div class="border-t border-line px-5 pt-4"><h4 class="text-sm font-bold text-ink">배분비율 — 계약체결금액 ${state.fc.dirty.has("hq_ratio") ? '<span class="badge bg-warn-bg text-warn">저장 안 됨</span>' : ""}</h4></div>
    ${longTable("hq_ratio", [{f: "사업장", label: "지사", type: "select", options: d.sites}, {f: "계약체결금액", label: "계약체결금액(천원)", type: "num"}], d.hq_ratio, "배분비율이 없습니다 — 본사 임시사업이 지사에 배분되지 않습니다.")}`, "hq_master")
}

function saveBar() {
  const n = state.fc.dirty.size
  return `<div class="sticky bottom-4 z-10 flex flex-wrap items-center gap-3 rounded-card border border-line bg-white/95 p-4 shadow-float backdrop-blur">
      <button class="btn-primary" id="fcSaveBtn" data-action="fc-save" ${n ? "" : "disabled"}>저장${n ? ` (${n}표)` : ""}</button>
      <span class="text-xs text-sub">손댄 표만 ${esc(state.fc.baseYear)}년 기준으로 저장합니다. 표준화·전망 표는 저장 즉시 다시 계산됩니다.</span>
    </div>`
}

const opts = () => state.fc.data?.options || {}
const sitesOpt = (d, blank) => [...(blank ? [""] : []), ...new Set([...d.sites])]

function eqPanel(d) {
  return panel("설비별 정비등급", "#1 GT·#2 GT·ST·DH 행 그대로 · 위 표(대표 등급)가 표준화·전망에 쓰임 · 어느 설비든 MI 인 해·A 로 바뀐 해 = A급정비 일정(DH·SRF·PLB 줄 제외, 기준연도 뒤 등급이 있는 지사만)",
    longTable("site_grade_eq", [{f: "사업장", label: "지사", type: "select", options: sitesOpt(d)}, {f: "연도", label: "연도", type: "int"},
      {f: "설비", label: "설비"}, {f: "등급", label: "등급"}], d.site_grade_eq, "설비별 등급이 없습니다 — «참고 엑셀·대조» 탭에서 가져오세요."), "site_grade_eq")
}

// ── 설비용량·신규표준(2026-10-28) — 신규 발전설비 지사(양산·대구·청주·수원)의 등급별 표준금액을 용량으로 환산 ──
const eok1 = v => (Number(v || 0) / 1e5).toLocaleString("ko-KR", {minimumFractionDigits: 1, maximumFractionDigits: 1})
const CAP_GRADES = ["간이", "CI", "TI/HGPI", "MI"]

function capacityModelPanel() {
  const c = state.fc.capacity
  if (!c) return panel("용량 환산 규칙", "불러오는 중…", '<p class="p-5 text-sm text-tri">계산 중입니다.</p>')
  const m = c.model
  if (!m) return panel("용량 환산 규칙", "기준 지사·대상 지사가 있어야 계산합니다", '<p class="p-5 text-sm text-sub">아래 «용량 규칙» 표에 기준 지사와 대상 지사를 넣으세요.</p>')
  const refs = Object.keys(m.refs)
  const cell = {}
  m.table.forEach(r => { cell[`${r.사업장}|${r.등급}`] = r })
  const pct = v => v == null ? "-" : `${Math.round(v * 100)}%`
  const refRows = refs.map(s => `<tr><td class="table-cell font-semibold text-ink">${esc(s)}</td><td class="table-cell text-right">${fmt(m.refs[s])}</td>${CAP_GRADES.map(g => {
      const r = cell[`${s}|${g}`]
      return `<td class="table-cell text-right">${r ? `${eok1(r.평균금액)}<span class="ml-1 text-[11px] text-tri">${r.해수}해 · ${(r.MW당 / 1e5).toFixed(3)}/MW</span>` : '<span class="text-tri">-</span>'}</td>`
    }).join("")}</tr>`).join("")
  const tgtRows = c.targets.map(t => `<tr><td class="table-cell font-semibold text-ink">${esc(t.사업장)}</td><td class="table-cell text-right">${fmt(t.용량MW)}</td>
      <td class="table-cell">${t.적용시작연도 ?? "-"}년~${t.정비제외연도.length ? ` · 정비제외 ${t.정비제외연도.join("·")}` : ""}</td>
      ${["간이", "CI", "TI", "MI"].map(g => `<td class="table-cell text-right">${t.등급별[g] != null ? eok1(t.등급별[g]) : "-"}</td>`).join("")}
      <td class="table-cell text-right">${t.등급별["정비제외"] != null ? eok1(t.등급별["정비제외"]) : "-"}</td></tr>`).join("")
  return panel("용량 환산 규칙", "한 해 정비비 = 고정분 + 등급별 MW당 단가 × 설비용량 · 과목별로는 기준 지사의 그 등급 해 과목 비중으로 나눔", `
    <div class="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-5">
      <div class="rounded-control bg-subtle px-4 py-3"><p class="text-xs font-semibold text-sub">고정분 (지사 공통)</p><p class="mt-1 text-lg font-bold text-ink">${eok1(m.fixed)}<span class="ml-1 text-xs text-tri">억원</span></p></div>
      ${CAP_GRADES.map(g => `<div class="rounded-control bg-subtle px-4 py-3"><p class="text-xs font-semibold text-sub">${g} · MW당</p><p class="mt-1 text-lg font-bold text-ink">${(Number(m.k[g] || 0) / 1e5).toFixed(3)}<span class="ml-1 text-xs text-tri">억원</span></p><p class="text-[11px] text-tri">맞혀 본 오차 ${pct(m.loo[g])}</p></div>`).join("")}
    </div>
    <p class="px-5 text-xs text-sub">* 맞혀 본 오차 = 기준 지사 하나씩 빼고 나머지로 그 지사를 맞혔을 때 평균 오차(전체 ${pct(m.loo_all)}) · TI 와 HGPI 는 같은 등급 · 고온부품 신품구매·LTSA·CRI 는 따로 잡혀 여기서 뺌</p>
    <div class="overflow-x-auto p-5"><h4 class="mb-2 text-sm font-bold text-ink">기준 지사 — 등급 해 평균 (억원/년)</h4><table class="w-full"><thead class="table-head"><tr><th class="px-3 py-2">지사</th><th class="px-3 py-2 text-right">MW</th>${CAP_GRADES.map(g => `<th class="px-3 py-2 text-right">${g}</th>`).join("")}</tr></thead>
      <tbody class="divide-y divide-line-subtle">${refRows}</tbody></table></div>
    <div class="overflow-x-auto p-5 pt-0"><h4 class="mb-2 text-sm font-bold text-ink">대상 지사 — 등급별 한 해 표준금액 (억원, 기준연도 값 · 이후 팩터 곱함)</h4><table class="w-full"><thead class="table-head"><tr><th class="px-3 py-2">지사</th><th class="px-3 py-2 text-right">MW</th><th class="px-3 py-2">적용</th>${["간이", "CI", "TI/HGPI", "MI"].map(g => `<th class="px-3 py-2 text-right">${g}</th>`).join("")}<th class="px-3 py-2 text-right">정비제외</th></tr></thead>
      <tbody class="divide-y divide-line-subtle">${tgtRows || '<tr><td class="table-cell text-tri" colspan="8">대상 지사가 없습니다.</td></tr>'}</tbody></table>
      <p class="mt-2 text-xs text-sub">* MI 해에는 A급정비(외주비-열원정기점검) 포함 · 대상 지사의 적용시작 전 실적은 표준화에서 뺌 · 수동수정한 칸은 그대로 둠</p></div>`)
}

function capacityBody(d) {
  const sites = [...sitesOpt(d), "본사"]
  const mwSum = (d.site_capacity || []).filter(r => r.구분 === "발전설비").reduce((a, r) => a + Number(r.용량MW || 0), 0)
  return `${capacityModelPanel()}
  ${panel("용량 규칙", "역할 «기준» = 규칙을 찾는 지사 · «대상» = 용량으로 환산할 지사 · 용량 빈 칸 = 설비 현황의 가장 늦게 준공한 발전설비 · 정비제외연도 예: 2027~2028",
    longTable("capacity_rule", [{f: "사업장", label: "지사", type: "select", options: sitesOpt(d)}, {f: "역할", label: "역할", type: "select", options: ["기준", "대상"]},
      {f: "적용시작연도", label: "적용시작연도", type: "int"}, {f: "용량MW", label: "용량(MW)", type: "num"},
      {f: "정비제외연도", label: "정비제외연도"}, {f: "비고", label: "비고"}], d.capacity_rule || [], "규칙이 없습니다."), "capacity_rule")}
  ${panel("설비 현황", `발전설비 ${mwSum.toLocaleString("ko-KR")}MW · 출처 «한난_발전설비용량_261028.xlsx»(한난 홈페이지 전력사업·지사안내, KPX 등록 2023.3)`,
    longTable("site_capacity", [{f: "사업장", label: "지사", type: "select", options: sites}, {f: "설비", label: "설비"},
      {f: "구분", label: "구분", type: "select", options: ["발전설비", "기타 소형"]}, {f: "용량MW", label: "용량(MW)", type: "num"},
      {f: "준공연도", label: "준공연도", type: "int"}, {f: "비고", label: "비고"}], d.site_capacity || [], "설비가 없습니다."), "site_capacity")}`
}

// ── 고온부품 계획(2026-10-28) — 사용자 양식 «26~35년 전지사 고온부품» 모양 그대로: 지사 × (재생·신품) × 연도 ──
const HOT_LINES = [["고온부품재생", "기계장치", "고온부품재생"], ["신품구매", "건설중인자산", "신품구매"]]

function hotPartsPanel(d) {
  const by = Number(state.fc.baseYear)
  const years = Array.from({length: 10}, (_, i) => by + i)
  const contracts = d.hot_parts_contract || []
  const sites = [...new Set([...contracts.map(r => r.사업장), ...d.hot_parts.map(r => r.사업장)])]
  const amt = {}
  d.hot_parts.forEach(r => { amt[`${r.사업장}|${r.항목}|${Number(r.연도)}`] = Number(r.금액 || 0) })
  const colSum = Object.fromEntries(years.map(y => [y, 0]))
  const body = sites.map(s => {
    const ci = contracts.findIndex(r => r.사업장 === s)
    const c = ci >= 0 ? contracts[ci] : null
    return HOT_LINES.map(([item, acct, label], li) => {
      let rowSum = 0
      const cells = years.map(y => {
        const v = amt[`${s}|${item}|${y}`] || 0
        rowSum += v; colSum[y] += v
        return `<td class="px-1 py-1"><input class="control min-w-[6.5rem] px-2 text-right text-sm" inputmode="numeric" data-fc="hot-cell" data-site="${esc(s)}" data-item="${item}" data-year="${y}" value="${v ? Math.round(v) : ""}" placeholder="0"></td>`
      }).join("")
      // 지사 칸은 좁게(계약방식·계약기간을 위아래로) — 넓으면 연도가 두 해만 보인다
      const head = li === 0 ? `<td class="fc-stick table-cell w-40 min-w-[10rem] max-w-[11rem] whitespace-normal bg-white align-top" rowspan="2"><b class="text-ink">${esc(s)}</b>
          ${c ? `<div class="mt-1 grid gap-1 [&_input]:min-h-[32px] [&_input]:w-full [&_input]:px-2 [&_input]:text-xs">${cellInput("hot_parts_contract", ci, {f: "계약방식"}, c.계약방식)}${cellInput("hot_parts_contract", ci, {f: "계약기간"}, c.계약기간)}</div>` : ""}</td>` : ""
      return `<tr class="${li ? "" : "border-t-2 border-line"}">${head}<td class="table-cell text-xs text-sub">${acct}<br><span class="font-semibold text-ink">${label}</span></td>${cells}<td class="table-cell text-right font-semibold">${fmt(Math.round(rowSum))}</td></tr>`
    }).join("")
  }).join("")
  const total = Object.values(colSum).reduce((a, b) => a + b, 0)
  const notes = (d.options?.hot_parts_notes || []).map(n => `<li>${esc(n)}</li>`).join("")
  const addable = sitesOpt(d).filter(s => !sites.includes(s))
  return panel("고온부품 계획", "금액 그대로 반영 — 팩터를 곱하지 않음 · 기계장치 = 고온부품재생, 건설중인자산 = 신품구매(재생고온부품) · 단위 천원", `
    <div class="flex flex-wrap items-end gap-2 p-5 pb-0">
      <button class="btn-secondary" data-fcimport="hot-parts">고온부품 엑셀에서 가져오기</button>
      <button class="btn-secondary" data-fcexport="hot-parts" title="«26~35년 전지사 고온부품» 양식 그대로, 금액·계약 칸만 지금 저장된 값">고온부품 양식으로 내려받기 (xlsx)</button>
      ${addable.length ? `<label class="ml-auto flex items-center gap-2 text-xs text-sub">지사 추가 ${sel(["", ...addable], "", 'data-fc="hot-add-site"', {"": "(고르기)"})}</label>` : ""}
    </div>
    <div class="overflow-x-auto p-5"><table class="w-full"><thead class="table-head"><tr><th class="fc-stick bg-subtle px-3 py-2">지사 · 계약</th><th class="px-3 py-2">예산과목</th>${years.map(y => `<th class="px-3 py-2 text-right">${y}</th>`).join("")}<th class="px-3 py-2 text-right">합계</th></tr></thead>
      <tbody>${body || `<tr><td class="table-cell text-tri" colspan="${years.length + 3}">고온부품 계획이 없습니다 — 엑셀에서 가져오거나 지사를 추가하세요.</td></tr>`}
      ${body ? `<tr class="border-t-2 border-line bg-subtle font-bold"><td class="fc-stick table-cell bg-subtle text-ink">합계</td><td></td>${years.map(y => `<td class="table-cell text-right">${fmt(Math.round(colSum[y]))}</td>`).join("")}<td class="table-cell text-right">${fmt(Math.round(total))}</td></tr>` : ""}</tbody></table></div>
    ${notes ? `<div class="border-t border-line px-5 py-4"><h4 class="text-sm font-bold text-ink">작성 기준</h4><ul class="mt-2 list-none space-y-1 text-xs leading-5 text-sub">${notes}</ul></div>` : ""}`, "hot_parts")
}

function historyBody(d) {
  return `${panel("지사 연혁", "연도별 그룹·설비 구성 · 종료연도 빈 칸 = 현재까지",
    longTable("site_history", [{f: "사업장", label: "지사", type: "select", options: sitesOpt(d)}, {f: "시작연도", label: "시작연도", type: "int"},
      {f: "종료연도", label: "종료연도", type: "int"}, {f: "그룹", label: "그룹", type: "select", options: ["", ...(opts().groups || GROUPS)]},
      {f: "설비", label: "설비 구성"}, {f: "비고", label: "비고"}], d.site_history, "연혁이 없습니다."), "site_history")}
  ${panel("구조 변화", "«실적사용시작» = 그 해 이전 실적을 표준화에서 뺌(예산과목 빈 칸 = 전 과목) · 나머지 유형은 기록용",
    longTable("site_event", [{f: "사업장", label: "지사", type: "select", options: sitesOpt(d)}, {f: "연도", label: "연도", type: "int"},
      {f: "유형", label: "유형", type: "select", options: opts().event_types || []},
      {f: "예산과목", label: "예산과목", type: "select", options: ["", ...accountsAll()], labels: {"": "(전 과목)"}},
      {f: "비고", label: "비고"}], d.site_event, "없음"), "site_event")}`
}

function regularBody(d) {
  const acctOpts = ["수선유지비-열원정기유지보수", "기계장치"]
  return `${panel("정기계약(LTSA) 집행계획", "등급별 표준화 대신 이 금액을 그대로 반영 · 팩터를 곱하지 않음",
    longTable("regular_contract", [{f: "사업장", label: "지사", type: "select", options: sitesOpt(d)}, {f: "연도", label: "연도", type: "int"},
      {f: "항목", label: "항목", type: "select", options: opts().contract_items || []},
      {f: "예산과목", label: "회계 과목", type: "select", options: acctOpts},
      {f: "금액", label: "금액(천원)", type: "num"}, {f: "비고", label: "비고"}], d.regular_contract, "정기계약 계획이 없습니다."), "regular_contract")}
  ${panel("CRI 규칙", "MI 해 + 지급시차 년에 기준단가 × 자본 팩터(단가기준연도부터) · 반출 로터는 짝지사에 장착",
    longTable("cri_rule", [{f: "사업장", label: "지사", type: "select", options: sitesOpt(d)},
      {f: "짝지사", label: "짝지사(동일 기종)", type: "select", options: sitesOpt(d, true)},
      {f: "지급시차", label: "지급시차(년)", type: "int"}, {f: "기준단가", label: "기준단가(천원)", type: "num"},
      {f: "단가기준연도", label: "단가기준연도", type: "int"}, {f: "활성", label: "활성", type: "bool"}, {f: "비고", label: "비고"}],
      d.cri_rule, "CRI 규칙이 없습니다 — 전망에 CRI 가 잡히지 않습니다."), "cri_rule")}
  ${panel("투자계획", "기준연도 이후 투자비는 이 값만 사용 · 기준연도는 계획본(여기 같은 해 값이 있으면 이것)",
    longTable("investment_plan", [{f: "사업장", label: "지사", type: "select", options: sitesOpt(d)}, {f: "연도", label: "연도", type: "int"},
      {f: "금액", label: "금액(천원)", type: "num"}, {f: "비고", label: "비고"}], d.investment_plan, "투자계획이 없습니다 — 기준연도 이후 투자비는 0 입니다."), "investment_plan")}`
}

const pct = v => (v === null || v === undefined) ? "—" : `${(v * 100).toFixed(1)}%`
const sgn = v => {
  if (v === null || v === undefined) return "—"
  const n = Math.round(v * 100)
  return `${n > 0 ? "+" : ""}${n}%`
}
const WINDOWS = [["2", "최근 2개년"], ["3", "최근 3개년 (권장)"], ["5", "최근 5개년"], ["10", "최근 10개년"], ["0", "있는 해 전부"]]

/** 학습 기간 · 백테스트(다른 세션의 백테스트 제안 ③⑤를 옮김) */
function learnBody(d) {
  const win = String(d.settings?.학습기간 ?? "3")
  const bt = state.fc.backtest
  // 재학습 뒤 — 고른 기간의 백테스트 값을 학습 기간 칸 옆에 바로(2026-10-28 사용자 요청)
  const chosen = bt?.runs?.find(r => String(r.window) === win)
  const best = bt?.runs?.length ? bt.runs.reduce((a, r) => (r.account ?? 9) < (a.account ?? 9) ? r : a) : null
  const btBody = bt ? `<div class="overflow-x-auto p-5"><table class="w-full"><thead class="table-head"><tr>
      <th class="px-3 py-2">학습 기간</th><th class="px-3 py-2 text-right">과목 합계 오차</th><th class="px-3 py-2 text-right">지사 3년 누적 오차</th><th class="px-3 py-2 text-right">칸별 오차 (참고)</th></tr></thead>
      <tbody class="divide-y divide-line-subtle">${bt.runs.map(r => `<tr class="${String(r.window) === win ? "bg-subtle font-semibold" : ""}">
        <td class="table-cell">최근 ${esc(r.window)}개년${String(r.window) === win ? " · 지금 설정" : ""}</td>
        <td class="table-cell text-right">${pct(r.account)}</td><td class="table-cell text-right">${pct(r.site3)}</td><td class="table-cell text-right text-sub">${pct(r.cell)}</td></tr>`).join("")}</tbody></table>
      <p class="mt-2 text-xs text-sub">시험 연도 ${esc((bt.runs[0]?.targets || []).join("·") || "없음")} — 그 해보다 앞선 해로 표준금액을 만들어 맞혀 본 결과(마감 ${esc((bt.sources?.마감 || []).join("·") || "없음")} · 참고 엑셀 ${esc((bt.sources?.참고 || []).length)}개년). 고온부품재·LTSA·CRI·재생고온부품은 계획으로 받는 줄이라 뺐습니다.</p>
      ${bt.runs[0]?.overhaul ? `<p class="mt-1 text-xs text-sub">A급정비 일정 규칙: 실제 ${bt.runs[0].overhaul.events}건 중 ${bt.runs[0].overhaul.hits}건 맞힘 · 헛예측 ${bt.runs[0].overhaul.false_positive}칸 · 총액 ${sgn(bt.runs[0].overhaul.total)}</p>` : ""}</div>`
    : '<p class="p-5 text-sm text-tri">아직 실행하지 않았습니다.</p>'
  return `
    ${panel("학습 기간", "산정 규칙이 없는 칸(사용자지정·자동추천)이 쓰는 최근 실적 해 수 · 규칙은 엑셀처럼 연도를 직접 가리킴 · 백테스트로 비교해 고르세요", `
      <div class="flex flex-wrap items-end gap-3 p-5">
        <label class="block"><span class="field-label">학습 기간</span>${sel(WINDOWS.map(w => w[0]), win, 'data-fcsetting="학습기간"', Object.fromEntries(WINDOWS))}</label>
        ${state.fc.dirty.has("settings") ? '<button class="btn-primary" data-action="fc-relearn" title="학습 기간을 저장하고 표준금액·전망을 다시 계산한 뒤 백테스트로 그 기간의 오차를 보여 줍니다">재학습</button>' : ""}
        ${chosen ? `<p class="pb-2 text-sm text-sub">최근 ${esc(win)}개년 백테스트 · 과목 합계 오차 <b class="text-ink">${pct(chosen.account)}</b> · 지사 3년 누적 <b class="text-ink">${pct(chosen.site3)}</b>${best && String(best.window) !== win ? ` · 가장 작은 기간 = 최근 ${esc(best.window)}개년 (${pct(best.account)})` : ""}</p>` : ""}
      </div>`, "settings")}
    ${panel("백테스트", "평가 단위 = 과목 합계 · 지사 3년 누적 (칸 하나는 사람 연예산도 44~64% 틀림) · 마감 실적 + 참고 엑셀 실적", `
      <div class="flex flex-wrap gap-2 p-5 pb-0"><button class="btn-secondary" data-action="fc-backtest">백테스트 실행</button></div>${btBody}`)}`
}

function cmpTable(rows, cols, onlyDiff) {
  const list = (onlyDiff ? rows.filter(r => r.차이 === null || Math.abs(r.차이) >= 1) : rows)
    .slice().sort((a, b) => Math.abs(b.차이 ?? Infinity) - Math.abs(a.차이 ?? Infinity))
  if (!list.length) return '<p class="p-5 text-sm text-sub">차이가 없습니다.</p>'
  return `<div class="max-h-96 overflow-auto"><table class="w-full"><thead class="table-head"><tr>${cols.map(([k, l, n]) => `<th class="px-3 py-2 ${n ? "text-right" : ""}">${esc(l)}</th>`).join("")}</tr></thead>
    <tbody class="divide-y divide-line-subtle">${list.slice(0, 300).map(r => `<tr>${cols.map(([k, , n]) => `<td class="table-cell ${n ? "text-right" : "text-xs"} ${k === "차이" && r.차이 !== null && Math.abs(r.차이) >= 1 ? "text-warn font-semibold" : ""}">${n ? (r[k] === null ? "—" : fmt(r[k])) : esc(r[k] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table>
    ${list.length > 300 ? `<p class="p-3 text-xs text-tri">차이가 큰 300건만 표시 (전체 ${list.length.toLocaleString()}건)</p>` : ""}</div>`
}

function refBody(d) {
  const ref = d.reference || {}
  const p = state.fc.refPreview
  const c = state.fc.compare
  const only = state.fc.cmpOnlyDiff
  const LABEL = {reference_actual: "참고 실적", reference_standard: "표준금액(대조 기준)", site_grade_eq: "설비별 등급",
                 site_grade: "대표 등급", benchmark_rule: "산정 규칙", site_history: "지사 연혁", cri_rule: "CRI 규칙",
                 regular_contract: "LTSA 계약 초안"}
  const sum = x => x ? `${x.same.toLocaleString()} / ${x.rows.toLocaleString()}건 일치 · 앱 ${fmt(x.app_total)} · 엑셀 ${fmt(x.excel_total)} 천원` : ""
  return `
  ${panel("참고 엑셀 (예산표준화 양식)", `지사 시트의 실적·정비등급·표준화 표를 읽고, 표준화 표의 수식을 산정 규칙으로 바꿉니다 · 지금 ${esc(state.fc.baseYear)}년 기준: 참고 실적 ${(ref.reference_actual || 0).toLocaleString()}행 · 표준금액 ${(ref.reference_standard || 0).toLocaleString()}행`, `
    <div class="flex flex-wrap gap-2 p-5">
      <button class="btn-primary" data-fcimport="reference">참고 엑셀 올리기 (미리보기)</button>
    </div>
    ${p ? `<div class="border-t border-line bg-subtle p-5">
      <h4 class="text-sm font-bold text-ink">미리보기 — 아직 저장되지 않았습니다</h4>
      <div class="mt-2 flex flex-wrap gap-2">${Object.entries(p.counts).map(([k, n]) => `<span class="badge bg-white text-ink">${esc(LABEL[k] || k)} ${Number(n).toLocaleString()}</span>`).join("")}</div>
      ${(p.warnings || []).map(w => `<p class="mt-2 text-xs text-warn">${esc(w)}</p>`).join("")}
      <p class="mt-2 text-xs text-sub">적용하면 ${esc(state.fc.baseYear)}년 기준의 위 표들(정비등급 이력 포함)이 통째로 바뀝니다. LTSA 계약은 최근 실적을 기준연도부터 10년 유지하는 초안입니다.</p>
      <div class="mt-3 flex gap-2"><button class="btn-primary" data-action="fc-ref-apply">적용</button><button class="btn-secondary" data-action="fc-ref-cancel">취소</button></div>
    </div>` : ""}`)}
  ${c ? panel("대조 — 앱 계산 vs 참고 엑셀", `마감 연도 ${esc((c.locked_years || []).join("·") || "없음")} · 마감되지 않은 연도는 참고 실적으로 보충해 표준화합니다`, `
    <div class="flex items-center gap-3 px-5 pt-4"><label class="flex items-center gap-2 text-sm"><input type="checkbox" data-fccmpdiff ${only ? "checked" : ""}> 차이 나는 것만</label></div>
    <div class="px-5 pt-4"><h4 class="text-sm font-bold text-ink">① 마감 연도 실적 (지사 × 연도 × 예산과목)</h4><p class="text-xs text-sub">${sum(c.actual.summary)}</p></div>
    ${cmpTable(c.actual.rows, [["사업장", "지사"], ["연도", "연도"], ["예산과목", "예산과목"], ["앱", "앱", 1], ["엑셀", "엑셀", 1], ["차이", "차이", 1]], only)}
    <div class="border-t border-line px-5 pt-4"><h4 class="text-sm font-bold text-ink">② 표준금액 (지사 × 예산과목 × 등급)</h4><p class="text-xs text-sub">${sum(c.standard.summary)}</p></div>
    ${cmpTable(c.standard.rows, [["사업장", "지사"], ["예산과목", "예산과목"], ["등급", "등급"], ["앱", "앱", 1], ["엑셀", "엑셀", 1], ["차이", "차이", 1], ["산출방식", "산출방식"], ["근거", "근거"], ["엑셀수식", "엑셀 수식"]], only)}
  `) : ""}`
}

function manageBody() {
  const d = state.fc.data
  if (!d) return emptyState("전망 가정을 불러오지 못했습니다.")
  const acct = accountsAll()
  const mt = state.fc.manageTab || "grades"
  const tabs = `<div class="flex flex-wrap gap-2" role="tablist" aria-label="기준정보 묶음">${MANAGE_TABS.map(([k, l, keys]) => {
    const dirty = keys.some(x => state.fc.dirty.has(x))
    return `<button class="${mt === k ? "btn-primary" : "btn-secondary"} min-h-[36px] px-4 text-xs" role="tab" aria-selected="${mt === k}" data-fcmtab="${k}">${esc(l)}${dirty ? ' <span class="h-1.5 w-1.5 rounded-full bg-warn" title="저장 안 됨"></span>' : ""}</button>`
  }).join("")}</div>`
  return `
  <div class="space-y-6">
    ${tabs}
    ${mt === "ref" ? refBody(d) : ""}
    ${mt === "grades" ? `${gradesPanel(d)}${eqPanel(d)}` : ""}
    ${mt === "history" ? historyBody(d) : ""}
    ${mt === "learn" ? learnBody(d) : ""}
    ${mt === "regular" ? regularBody(d) : ""}
    ${mt === "capacity" ? capacityBody(d) : ""}
    ${mt === "factor" ? `${hotPartsPanel(d)}
    ${panel("팩터", "활성 팩터의 (1+비율)을 기준연도부터 복리로 곱함",
      longTable("factors", [{f: "팩터명", label: "팩터명"}, {f: "연간비율", label: "연간비율 (0.015 = 1.5%)", type: "num"}, {f: "활성", label: "활성", type: "bool"},
        {f: "적용구분", label: "적용구분", type: "select", options: opts().factor_scopes || ["전체", "손익", "자본"]}], d.factors), "factors")}
    ` : ""}
    ${mt === "hq" ? `${hqMasterPanel(d)}
    ${panel("본사 일시적 사업", "배분비율(계약체결금액)로 지사에 자동 배분",
      longTable("hq_temp", [{f: "사업명", label: "사업명"}, {f: "예산과목", label: "예산과목", type: "select", options: acct}, {f: "연도", label: "연도", type: "int"}, {f: "금액", label: "금액(천원)", type: "num"}], d.hq_temp, "없음"), "hq_temp")}
    ` : ""}
    ${mt === "surprise" ? `${panel("지사별 돌발 사업", "그 해 그 과목에 더함",
      longTable("surprise", [{f: "사업장", label: "지사", type: "select", options: d.sites}, {f: "연도", label: "연도", type: "int"}, {f: "예산과목", label: "예산과목", type: "select", options: acct}, {f: "금액", label: "금액(천원)", type: "num"}, {f: "사유", label: "사유"}], d.surprise, "없음"), "surprise")}
    ` : ""}
    ${saveBar()}
  </div>`
}

// ── 가져오기 미리보기 ────────────────────────────────────────

const IMPORT_LABEL = {grades: "정비등급 이력(표준화 참고 엑셀)", schedule: "미래 정비등급(정비등급 양식)",
                      "hot-parts": "고온부품 계획", "hq-master": "본사 원가분배 마스터 + 배분비율"}

function previewPanel() {
  const p = state.fc.preview
  if (!p) return ""
  const rows = p.rows || []
  const cols = p.columns || (rows[0] ? Object.keys(rows[0]) : [])
  const mergeable = p.kind !== "hq-master"
  return `
  <article class="panel overflow-hidden border-line-strong" id="fcPreview">
    <div class="border-b border-line bg-subtle p-5 sm:p-6">
      <h3 class="section-title">가져오기 미리보기 — ${esc(IMPORT_LABEL[p.kind] || p.kind)}</h3>
      <p class="section-help">${rows.length.toLocaleString()}건을 찾았습니다${p.ratio_rows ? ` · 배분비율 ${p.ratio_rows.length}개 지사` : ""}${p.eq_rows?.length ? ` · 설비별 등급 ${p.eq_rows.length}건(줄이 둘 이상인 지사)도 같이 저장` : ""}. 아직 저장되지 않았습니다 — 아래에서 적용 방식을 고르세요.</p>
      <div class="mt-3 flex flex-wrap gap-2">
        ${mergeable ? '<button class="btn-primary" data-action="fc-apply-merge">기존에 없는 것만 추가</button>' : ""}
        <button class="${mergeable ?"btn-secondary" : "btn-primary"}" data-action="fc-apply-replace">전체 교체</button>
        <button class="btn-secondary" data-action="fc-cancel-preview">취소</button>
      </div>
    </div>
    ${rows.length ? `<div class="max-h-80 overflow-auto p-5"><table class="w-full"><thead class="table-head"><tr>${cols.map(c => `<th class="px-3 py-2">${esc(c)}</th>`).join("")}</tr></thead>
      <tbody class="divide-y divide-line-subtle">${rows.slice(0, 100).map(r => `<tr>${cols.map(c => `<td class="table-cell">${esc(typeof r[c] === "number" && c !== "연도" ? fmt(r[c]) : r[c] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table>
      ${rows.length > 100 ? '<p class="mt-2 text-xs text-tri">앞 100건만 표시합니다.</p>' : ""}</div>`
      : '<p class="p-5 text-sm text-warn">이 파일에서 해당 자료를 찾지 못했습니다 — 양식·시트명을 확인하세요. 지사 시트명은 지사 이름에서 «지사»·«사업소»를 뗀 것(예: 화성)이어야 합니다.</p>'}
  </article>`
}

// ── 표준화(3단계) 탭 ─────────────────────────────────────────

function rulesBody(d) {
  return `<div class="space-y-6">${panel("산정 규칙", "규칙 > 산출방식(사용자지정) > 자동추천 · 수동수정 금액이 가장 앞섬 · 등급 «*» = 모든 등급 · 연도목록 예: 2023,2021 / 2021~2025",
    longTable("benchmark_rule", [{f: "사업장", label: "지사", type: "select", options: sitesOpt(d)},
      {f: "예산과목", label: "예산과목", type: "select", options: accountsAll()}, {f: "등급", label: "등급"},
      {f: "방식", label: "방식", type: "select", options: opts().rule_methods || METHODS}, {f: "연도목록", label: "연도목록"},
      {f: "보정률", label: "보정률", type: "num"}, {f: "참조지사", label: "참조지사", type: "select", options: sitesOpt(d, true), labels: {"": "(자기)"}},
      {f: "참조등급", label: "참조등급"}, {f: "조정액", label: "조정액·직접입력(천원)", type: "num"}, {f: "사유", label: "사유"}],
      d.benchmark_rule, "규칙이 없습니다 — «기준정보 › 참고 엑셀·대조»에서 엑셀 수식을 규칙으로 가져올 수 있습니다."), "benchmark_rule")}
    ${saveBar()}</div>`
}

function regularBreakdownBody(d) {
  const g = state.fc.regular
  if (!g) return state.fc.regularLoading ? computingHtml("정기비용 분리를 계산하는 중…") : emptyState("정기비용 분리 현황을 불러오지 못했습니다.")
  const tags = {}
  d.actual_tag.forEach(r => { tags[`${r.사업장}|${r.연도}|${r.예산과목}|${r.사업명}`] = r.유형 })
  const types = opts().tag_types || Object.keys(TAG_LABEL)
  const summary = `<div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-3 py-2">지사</th><th class="px-3 py-2">연도</th><th class="px-3 py-2">예산과목</th>
      <th class="px-3 py-2 text-right">총액</th>${types.map(t => `<th class="px-3 py-2 text-right">${esc(TAG_LABEL[t] || t)}</th>`).join("")}</tr></thead>
    <tbody class="divide-y divide-line-subtle">${g.summary.length ? g.summary.map(r => `<tr><td class="table-cell font-semibold text-ink">${esc(r.사업장)}</td><td class="table-cell">${r.연도}</td><td class="table-cell">${esc(r.예산과목)}</td>
      <td class="table-cell text-right">${fmt(r.총액)}</td>${types.map(t => `<td class="table-cell text-right ${t !== "기타" && r[t] ? "font-semibold text-ink" : ""}">${fmt(r[t])}</td>`).join("")}</tr>`).join("")
      : `<tr><td class="table-cell text-tri" colspan="${types.length + 4}">마감된 연도의 기계장치·정기유지보수 실적이 없습니다.</td></tr>`}</tbody></table></div>`
  const projects = g.projects.slice(0, 400)
  const list = `<div class="max-h-[32rem] overflow-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-3 py-2">지사</th><th class="px-3 py-2">연도</th><th class="px-3 py-2">예산과목</th><th class="px-3 py-2">사업명</th>
      <th class="px-3 py-2 text-right">실적(천원)</th><th class="px-3 py-2">유형</th></tr></thead>
    <tbody class="divide-y divide-line-subtle">${projects.map(r => {
      const k = `${r.사업장}|${r.연도}|${r.예산과목}|${r.사업명}`
      const v = tags[k] ?? r.유형
      const manual = k in tags || r.유형출처 === "수동"
      return `<tr><td class="table-cell">${esc(r.사업장)}</td><td class="table-cell">${r.연도}</td><td class="table-cell text-xs">${esc(r.예산과목)}</td>
        <td class="table-cell text-xs">${esc(r.사업명)}</td><td class="table-cell text-right">${fmt(r.금액)}</td>
        <td class="px-2 py-1 ${manual ? "bg-warn-bg" : ""}">${sel(types, v, `data-fctag="${esc(k)}"`, TAG_LABEL)}</td></tr>`
    }).join("")}</tbody></table>${g.projects.length > 400 ? `<p class="p-3 text-xs text-tri">앞 400건만 표시 (전체 ${g.projects.length.toLocaleString()}건)</p>` : ""}</div>`
  return `<div class="space-y-6">
    ${panel("정기비용 분리 현황", `마감 ${esc((g.years_used || []).join("·") || "없음")}년 · 기계장치의 고온부품재생·LTSA·CRI 와 정기유지보수의 LTSA 는 표준화에서 빠지고 고온부품·정기계약·CRI 계획으로 잡힘`, summary)}
    ${panel("사업별 판정", "사업명 키워드로 자동 판정 · 바꾼 것(노란 칸)만 저장되어 자동 판정보다 앞섬", list, "actual_tag")}
    ${saveBar()}</div>`
}

/** 무거운 계산이 끝나기 전 자리 — 화면 위(기준연도·탭)는 먼저 보이고 이 칸만 기다린다. */
function computingHtml(text) {
  return `<section class="panel flex items-center gap-3 p-6 text-sm text-sub" aria-busy="true"><span class="fc-spin" aria-hidden="true"></span>${esc(text)}</section>`
}

function benchBody() {
  const bv = state.fc.benchView || "std"
  const views = `<div class="flex flex-wrap gap-2">${BENCH_VIEWS.map(([k, l]) => `<button class="${bv === k ? "btn-primary" : "btn-secondary"} min-h-[36px] px-4 text-xs" data-fcbview="${k}">${esc(l)}</button>`).join("")}</div>`
  if (bv === "rules") return `<div class="space-y-6">${views}${state.fc.data ? rulesBody(state.fc.data) : ""}</div>`
  if (bv === "regular") return `<div class="space-y-6">${views}${state.fc.data ? regularBreakdownBody(state.fc.data) : ""}</div>`
  return `<div class="space-y-6">${views}${benchStd()}</div>`
}

/** 표준금액 표의 지사 묶음 — 지사마다 한 줄 요약(줄 수·표준금액 합) + 펼치기. 거르기·검색 중이면 다 펼친다. */
function benchSiteGroups(rows, filtered) {
  const by = new Map()
  rows.forEach(r => { if (!by.has(r.사업장)) by.set(r.사업장, []); by.get(r.사업장).push(r) })
  const opened = state.fc.benchOpen || {}
  return [...by].map(([site, list]) => {
    const open = filtered || opened[site] === true
    const total = list.reduce((s, r) => s + Number(r.표준금액 || 0), 0)
    const warn = list.filter(r => r.재무팀대비 != null && Math.abs(r.재무팀대비) > 0.3).length
    // 접기 단추는 줄 맨 앞 + 왼쪽에 붙임(sticky) — 좁은 화면에서 표가 가로로 넘쳐도 단추가 화면 밖으로 밀리지 않게
    const btn = filtered ? "" : `<button class="btn-secondary min-h-[32px] shrink-0 px-3 text-xs" data-fcbopen="${esc(site)}" aria-expanded="${open}">${open ? "접기 ▴" : "펼치기 ▾"}</button>`
    const head = `<tr class="bg-subtle"><td class="px-3 py-2 text-sm" colspan="9"><div class="sticky left-3 inline-flex max-w-[calc(100vw-8rem)] flex-wrap items-center gap-x-2 gap-y-1">${btn}<b class="text-ink">${esc(site)}</b><span class="text-sub">${list.length}줄 · 표준금액 합 ${fmt(Math.round(total))} 천원${warn ? ` · <span class="text-warn">재무팀 대비 ±30% 밖 ${warn}줄</span>` : ""}</span></div></td></tr>`
    return {head, list: open ? list : []}
  })
}

function benchStd() {
  const b = state.fc.bench
  if (!b) return state.fc.benchLoading ? computingHtml("표준화 결과를 계산하는 중… 처음 계산은 시간이 걸려요") : emptyState("표준화 결과를 불러오지 못했습니다.")
  const groups = state.fc.data?.site_groups || {}
  const g = state.fc.benchGroup || "all"
  const f = state.fc.benchFilter || {}
  const base = b.rows.filter(r => g === "all" || groups[r.사업장] === g)
  const siteList = [...new Set(base.map(r => r.사업장))]
  const acctList = [...new Set(base.map(r => r.예산과목))].sort()
  const gradeList = [...new Set(base.map(r => r.등급))].sort()
  const q = (f.q || "").trim().toLowerCase()
  const rows = base.filter(r => (!f.site || r.사업장 === f.site) && (!f.account || r.예산과목 === f.account) && (!f.grade || r.등급 === f.grade)
    && (!q || [r.사업장, r.예산과목, r.등급, r.산출방식, r.방식출처, r.추천사유, r.근거, r.비고].some(x => String(x ?? "").toLowerCase().includes(q))))
  const filtered = !!(f.site || f.account || f.grade || q)
  const ed = state.fc.benchEdits
  const nEdits = Object.keys(ed.methods).length + Object.keys(ed.overrides).length
  const info = b.years_used.length
    ? `마감 연도 <b>${esc(b.years_used.filter(y => !String(y).endsWith("(참고)")).join("·") || "없음")}</b>${refYears(b.years_used)} · 실적 ${b.population.rows.toLocaleString()}행 · ${fmt(b.population.total)} 천원 → 표준금액 ${b.rows.length.toLocaleString()}행`
    : '<span class="text-warn">마감된 연도의 분석 결과가 없습니다 — 2단계에서 분석을 실행하고 설정에서 그 연도를 마감하면 여기 입력이 됩니다.</span>'
  return `
  <article class="panel overflow-hidden">
    <div class="border-b border-line p-5 sm:p-6">
      <h3 class="section-title">표준금액 (지사 × 예산과목 × 정비등급) <span class="cursor-help align-middle text-sm font-normal text-tri" title="${esc(`${info.replace(/<[^>]+>/g, "")} · 학습 기간 ${b.window ? `최근 ${b.window}개년` : "전체"}(규칙 없는 칸) · 재무팀(참고 엑셀) 대비 ±30% 밖은 노랑 · 산출방식을 바꾸면 «사용자지정», 금액을 고치면 «수동수정» · 방식출처·추천사유는 예측이에게 «○○지사 ○○ 표준금액 근거»로 물어보세요`)}" aria-label="설명">ⓘ</span></h3>
      ${b.years_used.length ? "" : `<p class="section-help">${info}</p>`}${b.has_ltsa ? "" : '<p class="section-help">ℹ️ 정기비용 유형이 없어 기계장치에서 LTSA·CRI·고온부품을 분리하지 못하고 총액을 씁니다.</p>'}
      <div class="mt-3 flex flex-wrap items-end gap-3">
        <label class="block"><span class="field-label">지사그룹</span>
          ${sel(["all", ...GROUPS], g, "data-fcgroup", {all: "전체"})}</label>
        <label class="block"><span class="field-label">지사</span>${sel(["", ...siteList], f.site || "", 'data-fcbf="site"', {"": "전체"})}</label>
        <label class="block"><span class="field-label">예산과목</span>${sel(["", ...acctList], f.account || "", 'data-fcbf="account"', {"": "전체"})}</label>
        <label class="block"><span class="field-label">등급</span>${sel(["", ...gradeList], f.grade || "", 'data-fcbf="grade"', {"": "전체"})}</label>
        <label class="block"><span class="field-label">검색</span><input class="control w-44" type="search" placeholder="지사·과목·방식·근거" value="${esc(f.q || "")}" data-fcbf="q"></label>
        <button class="btn-primary" data-action="fc-save-bench" ${nEdits ? "" : "disabled"}>변경 저장${nEdits ? ` (${nEdits}건)` : ""}</button>
        <button class="btn-secondary" data-fcexport="standardization" title="재무팀 표준화 참고 양식(25시트)에 실적·정비등급·표준금액을 채워 내려받습니다">표준화 양식으로 내보내기 (xlsx)</button>
      </div>
      ${exportNote()}
    </div>
    <div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr>
      <th class="px-3 py-2">지사</th><th class="px-3 py-2">구분</th><th class="px-3 py-2">예산과목</th><th class="px-3 py-2">등급</th>
      <th class="px-3 py-2">산출방식</th>
      <th class="px-3 py-2 text-right">표준금액(천원)</th><th class="px-3 py-2 text-right">재무팀(천원)</th><th class="px-3 py-2 text-right">재무팀 대비</th><th class="px-3 py-2">근거</th></tr></thead>
      <tbody class="divide-y divide-line-subtle">${rows.length ? benchSiteGroups(rows, filtered).map(({head, list}) => head + list.map(r => {
        const mk = `${r.사업장}|${r.예산과목}`, ak = `${mk}|${r.등급}`
        const mch = mk in ed.methods, ach = ak in ed.overrides
        return `<tr>
          <td class="table-cell font-semibold text-ink">${esc(r.사업장)}</td><td class="table-cell">${esc(r.구분)}</td>
          <td class="table-cell">${esc(r.예산과목)}</td><td class="table-cell">${esc(r.등급)}</td>
          <td class="px-2 py-1 ${mch ?"bg-warn-bg" : ""}">${r.방식출처 === "규칙" || r.방식출처 === "용량규칙" ? `<span class="text-sm text-ink">${esc(r.산출방식)}</span>` : sel(METHODS, ed.methods[mk] ?? (METHODS.includes(r.산출방식) ? r.산출방식 : METHODS[0]), `data-fcbench="method" data-key="${esc(mk)}"`)}</td>
          <td class="px-2 py-1 text-right ${ach ?"bg-warn-bg" : ""}"><input class="control fc-num" type="number" step="any" data-fcbench="amount" data-key="${esc(ak)}" value="${esc(ach ? ed.overrides[ak] : Math.round(r.표준금액))}"></td>
          <td class="table-cell text-right text-sub">${r.재무팀금액 == null ? "—" : fmt(r.재무팀금액)}</td>
          <td class="table-cell text-right ${r.재무팀대비 != null && Math.abs(r.재무팀대비) > 0.3 ? "bg-warn-bg text-warn" : "text-sub"}">${sgn(r.재무팀대비)}</td>
          <td class="table-cell min-w-[14rem] whitespace-normal text-xs text-sub">${esc(r.근거 || r.비고 || "")}</td></tr>`
      }).join("")).join("") : `<tr><td class="table-cell text-tri" colspan="9">${filtered ? "조건에 맞는 줄이 없습니다." : "표준화 대상 실적이 없습니다."}</td></tr>`}</tbody></table></div>
  </article>`
}

// ── 중장기 전망(4단계) 탭 ────────────────────────────────────

// 상세 표 묶음(2026-10-28 사용자 요청) — 합친 금액 한 줄 + ▾ 를 누르면 세부 줄. 묶음은 첫 세부 줄 자리에 선다.
const DETAIL_GROUPS = [
  ["수선유지비-열원정기유지보수", ["수선유지비-열원정기유지보수", "수선유지비-열원정기유지보수_LTSA"]],
  ["기계장치", ["기계장치_고온부품재생", "기계장치_기타기계장치", "기계장치_LTSA", "기계장치_CRI"]],
]

/** [{row, kind: "row"|"group"|"child", key}] — 묶음 줄은 세부 줄 합계, 펼친 묶음만 세부 줄이 따라 나온다. */
function detailLines(rows, years) {
  const byLabel = Object.fromEntries(rows.map(r => [r.예산과목, r]))
  const groupOf = {}
  DETAIL_GROUPS.forEach(([g, kids]) => kids.forEach(k => { groupOf[k] = g }))
  const open = state.fc.openGroups || new Set()
  const out = [], done = new Set()
  for (const r of rows) {
    const g = groupOf[r.예산과목]
    if (!g) { out.push({row: r, kind: "row"}); continue }
    if (done.has(g)) continue
    done.add(g)
    const kids = DETAIL_GROUPS.find(([x]) => x === g)[1].map(k => byLabel[k]).filter(Boolean)
    const sum = {예산과목: g}
    years.forEach(y => { sum[String(y)] = kids.reduce((s, k) => s + (k[String(y)] || 0), 0) })
    out.push({row: sum, kind: "group", key: g, open: open.has(g), n: kids.length})
    if (open.has(g)) kids.forEach(k => out.push({row: k, kind: "child"}))
  }
  return out
}

function tableBody() {
  const t = state.fc.table
  if (!t) return emptyState("전망 표를 불러오지 못했습니다.")
  const site = state.fc.site || TOTAL
  const rows = site === TOTAL ? t.total_rows : (t.tables[site] || [])
  const notes = []
  if (t.notes.actuals_empty) notes.push(["warn", "마감된 연도의 분석 결과가 없어 표준금액이 비어 있습니다 — 기준연도 이후가 0 으로 보입니다."])
  if (t.notes.budget_plan_missing) notes.push(["info", `${esc(t.base_year)}년 계획본이 없어 투자비를 0 으로 두고, 표준화 대상 과목의 ${esc(t.base_year)}년도 표준금액으로 대체합니다. 1단계에서 ${esc(t.base_year)}년 계획본을 올리면 확정 예산을 씁니다.`])
  if (t.notes.grade_empty) notes.push(["info", "정비등급 이력이 없어 등급 «표준» 한 종으로 계산했습니다. 기준정보 탭에서 이력을 가져오면 등급별 표준금액이 살아납니다."])
  const sums = Object.fromEntries(t.years.map(y => [y, rows.reduce((s, r) => s + (r[String(y)] || 0), 0)]))
  const ranges = site === TOTAL ? {} : (t.ranges?.[site] || {})
  const show = state.fc.showRange && site !== TOTAL
  const ohy = site === TOTAL ? [] : (t.overhaul_years?.[site] || [])
  const cellOf = (r, y) => {
    const v = r[String(y)], rg = ranges[r.예산과목]?.[String(y)]
    const tip = rg ? ` title="학습 기간 실적 범위 ${fmt(rg[0])} ~ ${fmt(rg[1])}"` : ""
    return `<td class="table-cell text-right"${tip}>${fmt(v)}${show && rg ? `<div class="text-[11px] text-tri">${fmt(rg[0])}~${fmt(rg[1])}</div>` : ""}</td>`
  }
  return `
  <article class="panel overflow-hidden">
    <div class="border-b border-line p-5 sm:p-6">
      <h3 class="section-title">${esc(t.base_year)}~${esc(String(t.years[t.years.length - 1]))}년 소요 전망 · <span class="text-ink">${site === TOTAL ? "전사 합계" : esc(site)}</span></h3>
      <p class="section-help">${baseYearRule(t)} · 이후 = 표준금액 × 팩터 · 단위 천원 · 판단은 지사 3년 누적·과목 합계로${ohy.length ? ` · A급정비(외주비-열원정기점검) 일정 ${esc(ohy.filter(y => y >= Number(t.base_year)).join("·") || "기간 안 없음")}` : ""}</p>
      ${notes.map(([tone, msg]) => `<p class="mt-2 rounded-control ${tone ==="warn" ? "bg-warn-bg text-warn" : "bg-subtle text-sub"} px-3 py-2 text-xs">${msg}</p>`).join("")}
      <div class="mt-3 flex flex-wrap items-end gap-3">
        <label class="block"><span class="field-label">지사</span>
          <select class="control" data-fcsite><option value="${TOTAL}" ${site === TOTAL ? "selected" : ""}>전사 합계 (${t.sites.length}개 지사)</option>${t.sites.map(s => `<option value="${esc(s)}" ${s === site ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></label>
        ${site === TOTAL ? "" : `<label class="flex items-center gap-2 text-sm text-sub"><input type="checkbox" data-fcrange ${state.fc.showRange ? "checked" : ""}> 예측 범위 보기</label>`}
        <button class="btn-secondary" data-fcexport="longterm" title="재무팀 중장기예산 참고 양식(지사 탭·본사 원가분배·총원가 배분·총괄표)에 결과를 채워 내려받습니다">중장기 예산 양식으로 내보내기 (xlsx)</button>
      </div>
      ${exportNote()}
    </div>
  </article>
  ${fcVizHtml(t, site, site === TOTAL)}
  <article class="panel overflow-hidden">
    <div class="flex flex-wrap items-end justify-between gap-x-4 gap-y-1 border-b border-line px-5 py-3"><h3 class="section-title">10개년 상세 표 · ${site === TOTAL ? "전사 합계" : esc(site)}</h3><p class="text-right text-xs text-tri"><span class="hidden sm:inline">Shift + 마우스 휠 = 좌우 이동 · </span>단위 <b class="font-semibold text-sub">천원</b></p></div>
    <div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="fc-stick bg-subtle px-3 py-2">예산과목</th>${t.years.map(y => `<th class="px-3 py-2 text-right">${y}</th>`).join("")}</tr></thead>
      <tbody class="divide-y divide-line-subtle">${detailLines(rows, t.years).map(({row: r, kind, key, open, n}) => kind === "group"
        ? `<tr><td class="fc-stick table-cell bg-white font-semibold text-ink"><button class="inline-flex items-center gap-1.5 text-left" data-fcdgrp="${esc(key)}" aria-expanded="${open}" title="${open ? "세부 내역 접기" : `세부 내역 ${n}개 보기`}">${esc(r.예산과목)}<span class="text-xs text-sub" aria-hidden="true">${open ? "▴" : "▾"}</span></button></td>${t.years.map(y => cellOf(r, y)).join("")}</tr>`
        : kind === "child"
          ? `<tr class="bg-subtle/60"><td class="fc-stick table-cell bg-subtle pl-8 text-sm text-sub">└ ${esc(r.예산과목)}</td>${t.years.map(y => cellOf(r, y)).join("")}</tr>`
          : `<tr><td class="fc-stick table-cell bg-white font-semibold text-ink">${esc(r.예산과목)}</td>${t.years.map(y => cellOf(r, y)).join("")}</tr>`).join("")}
      <tr class="bg-subtle font-bold"><td class="fc-stick table-cell bg-subtle text-ink">합계</td>${t.years.map(y => `<td class="table-cell text-right">${fmt(sums[y])}</td>`).join("")}</tr></tbody></table></div>
  </article>
  ${criPanel(t, site)}`
}

function criPanel(t, site) {
  const ev = (t.cri_events || []).filter(r => site === TOTAL || r.사업장 === site)
  return `<article class="panel mt-6 overflow-hidden">
    <div class="border-b border-line p-5 sm:p-6"><h3 class="section-title">CRI 일정</h3>
      <p class="section-help">MI 연도 → 이듬해 로터 반출(짝지사 장착) → 지급연도에 «기계장치_CRI» 행으로 반영 · 규칙은 기준정보 › 정기계약·CRI·투자</p></div>
    ${ev.length ? `<div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-3 py-2">지사</th><th class="px-3 py-2">MI</th><th class="px-3 py-2">로터 반출</th><th class="px-3 py-2">짝지사</th><th class="px-3 py-2">지급</th><th class="px-3 py-2 text-right">금액(천원)</th></tr></thead>
      <tbody class="divide-y divide-line-subtle">${ev.map(r => `<tr><td class="table-cell font-semibold text-ink">${esc(r.사업장)}</td><td class="table-cell">${r.MI연도}</td><td class="table-cell">${r.반출연도}</td><td class="table-cell">${esc(r.짝지사)}</td><td class="table-cell">${r.지급연도}</td><td class="table-cell text-right">${fmt(r.금액)}</td></tr>`).join("")}</tbody></table></div>`
      : '<p class="p-5 text-sm text-sub">전망 기간에 잡힌 CRI 가 없습니다 — CRI 규칙과 미래 MI 일정을 확인하세요.</p>'}
  </article>`
}

/** «2016(참고)…2022(참고)» → « · 참고 실적 2016~2022» (연도 순, 마감 연도와 나눠 읽게). */
function refYears(used) {
  const ys = (used || []).filter(y => String(y).endsWith("(참고)")).map(y => parseInt(y, 10)).sort((a, b) => a - b)
  if (!ys.length) return ""
  return ` · 참고 실적 ${ys[0]}${ys.length > 1 ? `~${ys[ys.length - 1]}` : ""}`
}

export function renderForecast() {
  const tab = state.fc.tab || "manage"
  const body = tab === "bench" ? benchBody() : tab === "table" ? tableBody() : manageBody()
  return `
  <div class="space-y-6">
    ${header()}
    ${previewPanel()}
    ${body}
    <input id="fcImportFile" class="hidden" type="file" accept=".xlsx" data-kind="">
  </div>`
}
