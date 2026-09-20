import { emptyState } from "../components/widgets.js"
import { state } from "../state.js"
import { esc, fmt } from "../util.js"

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

function panel(title, help, body, key) {
  const dirty = key && state.fc.dirty.has(key)
  return `<article class="panel overflow-hidden">
    <div class="border-b border-line p-5 sm:p-6">
      <h3 class="section-title">${esc(title)} ${dirty ? '<span class="badge bg-warn-bg text-warn">저장 안 됨</span>' : ""}</h3>
      <p class="section-help leading-6">${help}</p>
    </div>${body}</article>`
}

// ── 헤더: 기준연도 · 탭 ──────────────────────────────────────

function header() {
  const fc = state.fc
  const years = [...new Set([...fc.baseYears, fc.baseYear])].filter(Boolean).sort()
  const locked = fc.lockedYears?.length ? fc.lockedYears.join("·") : "없음"
  return `
  <section class="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
    <div>
      <p class="text-sm font-semibold text-ink">STAGE 03 · 04</p>
      <h2 class="mt-1 font-hanan text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">예산 표준화 · 중장기 전망</h2>
      <p class="section-help max-w-30 leading-6">마감된 연도(<b class="text-ink">${esc(locked)}</b>)의 분석 결과가 표준금액의 입력입니다. 가정(정비등급·고온부품·본사배분·팩터·임시·돌발사업)은 기준연도마다 한 벌 — 내년 전망을 시작해도 올해 가정이 남습니다.</p>
    </div>
    <div class="flex flex-wrap items-end gap-2">
      <label class="block"><span class="mb-1.5 block text-xs font-semibold text-sub">전망 기준연도</span>
        <select class="control" data-fcbase>${years.map(y => `<option value="${esc(y)}" ${y === fc.baseYear ? "selected" : ""}>${esc(y)}년 기준${fc.baseYears.includes(y) ? "" : " (아직 저장된 가정 없음)"}</option>`).join("")}</select></label>
      <button class="btn-secondary" data-action="fc-add-base" title="직전 기준연도의 가정을 복사해 새 기준연도를 만듭니다">＋기준연도</button>
    </div>
  </section>
  <div class="flex flex-wrap gap-2">${TABS.map(([k, l]) => `<button class="${fc.tab === k ?"btn-primary" : "btn-secondary"}" data-fctab="${k}">${esc(l)}</button>`).join("")}</div>`
}

// ── 기준정보(가정) 탭 ────────────────────────────────────────

function cellInput(key, i, c, v) {
  const a = `data-fc="${key}" data-idx="${i}" data-field="${esc(c.f)}"`
  if (c.type === "select") return sel(c.options, v ?? "", a)
  if (c.type === "bool") return `<input type="checkbox" ${a} ${v ? "checked" : ""}>`
  if (c.type === "num") return `<input class="control fc-num" type="number" step="any" ${a} value="${esc(num(v))}">`
  if (c.type === "int") return `<input class="control fc-int" type="number" step="1" ${a} value="${esc(num(v))}">`
  return `<input class="control" ${a} value="${esc(num(v))}">`
}

/** 긴 표 편집기 — 행 추가·삭제·셀 편집. cols: [{f, label, type, options}] */
function longTable(key, cols, rows, empty) {
  const head = cols.map(c => `<th class="px-3 py-2 ${c.type ==="num" ? "text-right" : ""}">${esc(c.label)}</th>`).join("") + '<th class="w-16"></th>'
  const body = rows.map((r, i) => `<tr>${cols.map(c => `<td class="px-2 py-1">${cellInput(key, i, c, r[c.f])}</td>`).join("")}
      <td class="px-2 py-1 text-right"><button class="btn-secondary" data-fcdel="${key}" data-idx="${i}">삭제</button></td></tr>`).join("")
  return `<div class="overflow-x-auto p-5"><table class="w-full"><thead class="table-head"><tr>${head}</tr></thead>
    <tbody class="divide-y divide-line-subtle">${body || `<tr><td class="table-cell text-tri" colspan="${cols.length + 1}">${esc(empty || "없음")}</td></tr>`}</tbody></table>
    <button class="btn-secondary mt-3" data-fcadd="${key}">＋ 행 추가</button></div>`
}

function gradesPanel(d) {
  const by = Number(state.fc.baseYear)
  const years = [...new Set([...d.grades.map(r => Number(r.연도)), ...Array.from({length: 10}, (_, i) => by + i)])].sort()
  const sites = [...new Set([...d.sites, ...d.grades.map(r => r.사업장)])]
  const cell = {}
  d.grades.forEach(r => { cell[`${r.사업장}|${r.연도}`] = r.등급 })
  return panel("정비등급 이력", "지사×연도 등급. 과거는 <b>표준화 참고 엑셀</b>, 미래(기준연도~)는 <b>정기점검보수공사 일정</b>에서 가져오거나 직접 칩니다. 중대형CHP MI·TI·CI·간이·HGPI·BSI, 소형CHP A·B·C. 빈 칸 = 그 해 이력 없음. 이력이 하나도 없는 지사는 등급 «표준» 한 종으로 표준화됩니다.", `
    <div class="flex flex-wrap gap-2 p-5 pb-0">
      <button class="btn-secondary" data-fcimport="grades">표준화 참고 엑셀에서 가져오기</button>
      <button class="btn-secondary" data-fcimport="schedule">정기점검 일정 엑셀에서 가져오기</button>
      <button class="btn-secondary" data-fcexport="schedule" title="지금 저장된 미래 등급이 채워진 원본 양식 — 고쳐서 다시 올릴 수 있습니다">현재값이 채워진 일정 양식 내려받기</button>
    </div>
    <div class="overflow-x-auto p-5"><table class="w-full"><thead class="table-head"><tr><th class="px-3 py-2">지사</th>${years.map(y => `<th class="px-1 py-2 text-center">${y}</th>`).join("")}</tr></thead>
      <tbody class="divide-y divide-line-subtle">${sites.map(s => `<tr><td class="table-cell font-semibold text-ink">${esc(s)}</td>${years.map(y =>
        `<td class="px-1 py-1 text-center"><input class="control fc-grade" data-fc="grade-cell" data-site="${esc(s)}" data-year="${y}" value="${esc(cell[`${s}|${y}`] || "")}"></td>`).join("")}</tr>`).join("")}</tbody></table></div>`, "grades")
}

function hqMasterPanel(d) {
  const cols = d.hq_master.columns
  const rows = d.hq_master.rows
  const body = rows.map((r, i) => `<tr>${cols.map((c, j) => `<td class="px-2 py-1">${cellInput("hq_master", i, {f: c, type: j < 3 ? "text" : "num"}, r[c])}</td>`).join("")}
      <td class="px-2 py-1 text-right"><button class="btn-secondary" data-fcdel="hq_master" data-idx="${i}">삭제</button></td></tr>`).join("")
  return panel("본사 원가분배 마스터", "«NN년 본사 원가분배» 양식의 배분 구조·금액을 그대로 씁니다 — 앱이 비율을 다시 계산하지 않습니다. 열은 대분류·중분류·세부내역·기준연도 예산·지사들. 아래 <b>배분비율(계약체결금액)</b>은 본사 임시사업을 지사에 나누는 기준입니다.", `
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

function manageBody() {
  const d = state.fc.data
  if (!d) return emptyState("전망 가정을 불러오지 못했습니다.")
  const acct = accountsAll()
  const n = state.fc.dirty.size
  return `
  <div class="space-y-6">
    ${gradesPanel(d)}
    ${panel("팩터", "미래 연도 금액에 곱하는 연간 비율. 활성인 팩터의 (1+비율)을 기준연도부터 복리로 곱합니다. 물가상승률 외에 노후화 등을 더할 수 있습니다.",
      longTable("factors", [{f: "팩터명", label: "팩터명"}, {f: "연간비율", label: "연간비율 (0.015 = 1.5%)", type: "num"}, {f: "활성", label: "활성", type: "bool"}], d.factors), "factors")}
    ${panel("고온부품 계획", "지사×연도×항목(고온부품재생/신품구매) 금액을 그대로 반영합니다 — 팩터를 곱하지 않습니다. «고온부품(NN)» 양식에서 가져올 수 있습니다.", `
      <div class="flex flex-wrap gap-2 p-5 pb-0">
        <button class="btn-secondary" data-fcimport="hot-parts">고온부품 엑셀에서 가져오기</button>
        <button class="btn-secondary" data-fcexport="hot-parts">현재값이 채워진 양식 내려받기</button>
      </div>
      ${longTable("hot_parts", [{f: "사업장", label: "지사", type: "select", options: d.sites}, {f: "연도", label: "연도", type: "int"}, {f: "항목", label: "항목", type: "select", options: HOT_ITEMS}, {f: "금액", label: "금액(천원)", type: "num"}], d.hot_parts, "고온부품 계획이 없습니다.")}`, "hot_parts")}
    ${hqMasterPanel(d)}
    ${panel("본사 일시적 사업", "계획에 없던 본사 사업. 위 배분비율(계약체결금액)로 지사에 자동 배분됩니다.",
      longTable("hq_temp", [{f: "사업명", label: "사업명"}, {f: "예산과목", label: "예산과목", type: "select", options: acct}, {f: "연도", label: "연도", type: "int"}, {f: "금액", label: "금액(천원)", type: "num"}], d.hq_temp, "없음"), "hq_temp")}
    ${panel("지사별 돌발 사업", "표준금액에 없던 지사 사업을 그 해 그 과목에 더합니다.",
      longTable("surprise", [{f: "사업장", label: "지사", type: "select", options: d.sites}, {f: "연도", label: "연도", type: "int"}, {f: "예산과목", label: "예산과목", type: "select", options: acct}, {f: "금액", label: "금액(천원)", type: "num"}, {f: "사유", label: "사유"}], d.surprise, "없음"), "surprise")}
    <div class="sticky bottom-4 z-10 flex flex-wrap items-center gap-3 rounded-card border border-line bg-white/95 p-4 shadow-float backdrop-blur">
      <button class="btn-primary" id="fcSaveBtn" data-action="fc-save" ${n ? "" : "disabled"}>저장${n ? ` (${n}표)` : ""}</button>
      <span class="text-xs text-sub">손댄 표만 ${esc(state.fc.baseYear)}년 기준으로 저장합니다. 표준화·전망 표는 저장 즉시 다시 계산됩니다.</span>
    </div>
  </div>`
}

// ── 가져오기 미리보기 ────────────────────────────────────────

const IMPORT_LABEL = {grades: "정비등급 이력(표준화 참고 엑셀)", schedule: "미래 정비등급(정기점검 일정)",
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
      <p class="section-help">${rows.length.toLocaleString()}건을 찾았습니다${p.ratio_rows ? ` · 배분비율 ${p.ratio_rows.length}개 지사` : ""}. 아직 저장되지 않았습니다 — 아래에서 적용 방식을 고르세요.</p>
      <div class="mt-3 flex flex-wrap gap-2">
        ${mergeable ? '<button class="btn-primary" data-action="fc-apply-merge">기존에 없는 것만 추가</button>' : ""}
        <button class="${mergeable ?"btn-secondary" : "btn-primary"}" data-action="fc-apply-replace">전체 교체</button>
        <button class="btn-secondary" data-action="fc-cancel-preview">취소</button>
      </div>
    </div>
    ${rows.length ? `<div class="max-h-80 overflow-auto p-5"><table class="w-full"><thead class="table-head"><tr>${cols.map(c => `<th class="px-3 py-2">${esc(c)}</th>`).join("")}</tr></thead>
      <tbody class="divide-y divide-line-subtle">${rows.slice(0, 100).map(r => `<tr>${cols.map(c => `<td class="table-cell">${esc(typeof r[c] === "number" ? fmt(r[c]) : r[c] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table>
      ${rows.length > 100 ? '<p class="mt-2 text-xs text-tri">앞 100건만 표시합니다.</p>' : ""}</div>`
      : '<p class="p-5 text-sm text-warn">이 파일에서 해당 자료를 찾지 못했습니다 — 양식·시트명을 확인하세요. 지사 시트명은 지사 이름에서 «지사»·«사업소»를 뗀 것(예: 화성)이어야 합니다.</p>'}
  </article>`
}

// ── 표준화(3단계) 탭 ─────────────────────────────────────────

function benchBody() {
  const b = state.fc.bench
  if (!b) return emptyState("표준화 결과를 불러오지 못했습니다.")
  const groups = state.fc.data?.site_groups || {}
  const g = state.fc.benchGroup || "all"
  const rows = b.rows.filter(r => g === "all" || groups[r.사업장] === g)
  const ed = state.fc.benchEdits
  const nEdits = Object.keys(ed.methods).length + Object.keys(ed.overrides).length
  const info = b.years_used.length
    ? `마감 연도 <b>${esc(b.years_used.join("·"))}</b> · 실적 ${b.population.rows.toLocaleString()}행 · ${fmt(b.population.total)}천원 → 표준금액 ${b.rows.length.toLocaleString()}행`
    : '<span class="text-warn">마감된 연도의 분석 결과가 없습니다 — 2단계에서 분석을 실행하고 설정에서 그 연도를 마감하면 여기 입력이 됩니다.</span>'
  return `
  <article class="panel overflow-hidden">
    <div class="border-b border-line p-5 sm:p-6">
      <h3 class="section-title">표준금액 (지사 × 예산과목 × 정비등급)</h3>
      <p class="section-help leading-6">${info}</p>
      <p class="section-help">«자동추천»은 실적 패턴(연도별 변동·등급별 편차)으로 방식을 골랐고 근거가 «추천사유»에 있습니다. <b>산출방식</b>을 바꾸면 그 (지사,과목)은 «사용자지정»으로, <b>표준금액</b>을 고치면 그 (지사,과목,등급)은 «수동수정»으로 고정됩니다.${b.has_ltsa ? "" : " ℹ️ «투자유형세부»가 없어 기계장치에서 LTSA/CRI 를 분리하지 못하고 총액을 씁니다."}</p>
      <div class="mt-3 flex flex-wrap items-end gap-3">
        <label class="block"><span class="mb-1.5 block text-xs font-semibold text-sub">지사그룹</span>
          ${sel(["all", ...GROUPS], g, "data-fcgroup", {all: "전체"})}</label>
        <button class="btn-primary" data-action="fc-save-bench" ${nEdits ? "" : "disabled"}>변경 저장${nEdits ? ` (${nEdits}건)` : ""}</button>
        <button class="btn-secondary" data-fcexport="standardization" title="재무팀 표준화 참고 양식(25시트)에 실적·정비등급·표준금액을 채워 내려받습니다">표준화 양식으로 내보내기 (xlsx)</button>
      </div>
      ${exportNote()}
    </div>
    <div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr>
      <th class="px-3 py-2">지사</th><th class="px-3 py-2">구분</th><th class="px-3 py-2">예산과목</th><th class="px-3 py-2">등급</th>
      <th class="px-3 py-2">산출방식</th><th class="px-3 py-2">방식출처</th><th class="px-3 py-2">추천사유</th>
      <th class="px-3 py-2 text-right">표준금액(천원)</th><th class="px-3 py-2">비고</th></tr></thead>
      <tbody class="divide-y divide-line-subtle">${rows.length ? rows.map(r => {
        const mk = `${r.사업장}|${r.예산과목}`, ak = `${mk}|${r.등급}`
        const mch = mk in ed.methods, ach = ak in ed.overrides
        return `<tr>
          <td class="table-cell font-semibold text-ink">${esc(r.사업장)}</td><td class="table-cell">${esc(r.구분)}</td>
          <td class="table-cell">${esc(r.예산과목)}</td><td class="table-cell">${esc(r.등급)}</td>
          <td class="px-2 py-1 ${mch ?"bg-warn-bg" : ""}">${sel(METHODS, ed.methods[mk] ?? r.산출방식, `data-fcbench="method" data-key="${esc(mk)}"`)}</td>
          <td class="table-cell text-sub">${esc(r.방식출처)}</td><td class="table-cell text-xs text-sub">${esc(r.추천사유 || "")}</td>
          <td class="px-2 py-1 text-right ${ach ?"bg-warn-bg" : ""}"><input class="control fc-num" type="number" step="any" data-fcbench="amount" data-key="${esc(ak)}" value="${esc(ach ? ed.overrides[ak] : Math.round(r.표준금액))}"></td>
          <td class="table-cell text-xs text-sub">${esc(r.비고 || "")}</td></tr>`
      }).join("") : '<tr><td class="table-cell text-tri" colspan="9">표준화 대상 실적이 없습니다.</td></tr>'}</tbody></table></div>
  </article>`
}

// ── 중장기 전망(4단계) 탭 ────────────────────────────────────

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
  return `
  <article class="panel overflow-hidden">
    <div class="border-b border-line p-5 sm:p-6">
      <h3 class="section-title">${esc(t.base_year)}~${esc(String(t.years[t.years.length - 1]))}년 소요 전망 · <span class="text-ink">${site === TOTAL ? "전사 합계" : esc(site)}</span></h3>
      <p class="section-help">기준연도는 계획본(있으면) + 본사배분, 이후는 표준금액 × 팩터 복리. 고온부품은 계획값 그대로, 임시·돌발사업은 그 해에 더합니다. 단위 천원.</p>
      ${notes.map(([tone, msg]) => `<p class="mt-2 rounded-control ${tone ==="warn" ? "bg-warn-bg text-warn" : "bg-subtle text-sub"} px-3 py-2 text-xs">${msg}</p>`).join("")}
      <div class="mt-3 flex flex-wrap items-end gap-3">
        <label class="block"><span class="mb-1.5 block text-xs font-semibold text-sub">지사</span>
          <select class="control" data-fcsite><option value="${TOTAL}" ${site === TOTAL ? "selected" : ""}>전사 합계 (${t.sites.length}개 지사)</option>${t.sites.map(s => `<option value="${esc(s)}" ${s === site ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></label>
        <button class="btn-secondary" data-fcexport="longterm" title="재무팀 중장기예산 참고 양식(지사 탭·본사 원가분배·총원가 배분·총괄표)에 결과를 채워 내려받습니다">중장기 예산 양식으로 내보내기 (xlsx)</button>
      </div>
      ${exportNote()}
    </div>
    <div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-3 py-2">예산과목</th>${t.years.map(y => `<th class="px-3 py-2 text-right">${y}</th>`).join("")}</tr></thead>
      <tbody class="divide-y divide-line-subtle">${rows.map(r => `<tr><td class="table-cell font-semibold text-ink">${esc(r.예산과목)}</td>${t.years.map(y => `<td class="table-cell text-right">${fmt(r[String(y)])}</td>`).join("")}</tr>`).join("")}
      <tr class="bg-subtle font-bold"><td class="table-cell text-ink">합계</td>${t.years.map(y => `<td class="table-cell text-right">${fmt(sums[y])}</td>`).join("")}</tr></tbody></table></div>
  </article>`
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
