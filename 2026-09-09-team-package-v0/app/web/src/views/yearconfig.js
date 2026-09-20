import { state } from "../state.js"
import { esc } from "../util.js"

const GROUPS = ["본사", "중대형CHP", "소형CHP", "DH"]

const TABS = [["depts", "지사 구성"], ["손익", "손익 과목"], ["자본", "자본 과목"],
              ["alias", "별칭"], ["master", "마스터"]]

// 지사그룹은 지금까지 4번 통계의 막대에만 나타났고 고칠 곳이 없었다 — 바꾸려면
// 개발자 PC 의 JSON 을 고쳐 재배포해야 했다. 지사는 준공·이관으로 성격이 바뀌므로
// (양산·대구·청주) 팀이 그 해 기준을 직접 반영할 수 있어야 한다.
function deptTable(locked) {
  const rows = state.yearConfig?.depts || []
  return `<div class="overflow-x-auto"><table class="w-full"><thead class="table-head">
    <tr><th class="px-4 py-3">지사</th><th class="px-4 py-3">지사그룹</th>
    <th class="px-4 py-3 text-center">포함</th></tr></thead>
    <tbody class="divide-y divide-line-subtle">${rows.map((r, i) => `
      <tr><td class="table-cell font-semibold text-ink">${esc(r.이름)}</td>
      <td class="table-cell"><select class="control" data-yc="dept" data-idx="${i}" data-field="그룹" ${locked ? "disabled" : ""}>
        ${GROUPS.map(g => `<option value="${esc(g)}" ${g === r.그룹 ? "selected" : ""}>${esc(g)}</option>`).join("")}
      </select></td>
      <td class="table-cell text-center"><input type="checkbox" data-yc="dept" data-idx="${i}" data-field="포함" ${r.포함 ? "checked" : ""} ${locked ? "disabled" : ""}></td></tr>`).join("")}
    </tbody></table></div>`
}

function itemTable(budget, locked) {
  const rows = state.yearConfig?.items?.[budget] || []
  return `<div class="overflow-x-auto"><table class="w-full"><thead class="table-head">
    <tr><th class="px-4 py-3">예산과목</th><th class="px-4 py-3">대분류</th>
    <th class="px-4 py-3 text-center">심의대상</th><th class="px-4 py-3 text-center">포함</th>
    <th class="px-4 py-3 text-center">실적반영</th></tr></thead>
    <tbody class="divide-y divide-line-subtle">${rows.map((r, i) => `
      <tr><td class="table-cell font-semibold text-ink">${esc(r.과목)}</td>
      <td class="table-cell text-sub">${esc(r.대분류 || "")}</td>
      ${["심의대상", "포함", "실적반영"].map(f => `<td class="table-cell text-center">
        <input type="checkbox" data-yc="item" data-budget="${esc(budget)}" data-idx="${i}" data-field="${f}" ${r[f] ? "checked" : ""} ${locked ? "disabled" : ""}></td>`).join("")}
      </tr>`).join("")}
    </tbody></table></div>`
}

// 별칭은 연도 축이 없다 — 오래된 표기가 몇 년 뒤 자료에 다시 나타나기 때문이다.
// 시드 항목은 잠근다: 읽을 때마다 시드를 병합하므로 지워도 되살아난다.
// 지울 수 있는 것처럼 보여 놓고 되살아나는 쪽이 더 나쁘다(사용자 결정 2026-09-19).
function aliasTable() {
  const kind = state.ycAliasKind || "dept"
  const map = state.yearConfig?.alias?.[kind] || {}
  const seeded = new Set(state.yearConfig?.aliasSeeded?.[kind] || [])
  const [srcLabel, dstLabel] = kind === "dept"
    ? ["ERP 원표기", "계획 처지사"] : ["옛 과목명", "현 과목명"]
  const keys = Object.keys(map).sort((a, b) =>
    (seeded.has(a) === seeded.has(b)) ? a.localeCompare(b) : (seeded.has(a) ? 1 : -1))
  const kindBtn = (k, label) => `<button class="${kind === k ?"btn-primary" : "btn-secondary"}" data-ycalias="${k}">${label}</button>`
  return `
    <div class="p-5 sm:p-6">
      <div class="flex flex-wrap gap-2">${kindBtn("dept", "처지사 별칭")}${kindBtn("item", "예산과목 별칭")}</div>
      <p class="section-help mt-3">표기가 흔들리는 자료를 하나로 모읍니다. <b>연도 구분이 없습니다</b> — 옛 표기가 몇 년 뒤 자료에 다시 나타나기 때문입니다. <b>기본</b> 표시가 붙은 항목은 프로그램에 내장된 값이라 수정·삭제할 수 없습니다.</p>
      <div class="mt-4 flex flex-wrap items-end gap-2">
        <label class="text-xs font-semibold text-sub">${esc(srcLabel)}<input id="ycAliasSrc" class="control mt-1 block" placeholder="예: 경남지사(양산RPS 태양광)"></label>
        <label class="text-xs font-semibold text-sub">${esc(dstLabel)}<input id="ycAliasDst" class="control mt-1 block" placeholder="예: 양산지사"></label>
        <button class="btn-secondary" data-action="add-alias">＋ 추가</button>
      </div>
      <div class="mt-4 max-h-96 overflow-auto"><table class="w-full"><thead class="table-head">
        <tr><th class="px-3 py-2">${esc(srcLabel)}</th><th class="px-3 py-2">${esc(dstLabel)}</th><th class="px-3 py-2 w-24"></th></tr></thead>
        <tbody class="divide-y divide-line-subtle">${keys.map(k => seeded.has(k) ? `
          <tr class="bg-subtle text-tri">
            <td class="table-cell">${esc(k)} <span class="badge bg-line text-sub">기본</span></td>
            <td class="table-cell">${esc(map[k])}</td>
            <td class="table-cell text-right text-xs">수정 불가</td></tr>` : `
          <tr><td class="table-cell font-semibold text-ink">${esc(k)}</td>
            <td class="table-cell"><input class="control" value="${esc(map[k])}" data-yc="alias" data-key="${esc(k)}"></td>
            <td class="table-cell text-right"><button class="btn-secondary" data-del-alias="${esc(k)}">삭제</button></td></tr>`).join("")}
        </tbody></table></div>
      ${keys.length ? "" : `<p class="mt-4 text-xs text-tri">등록된 별칭이 없습니다.</p>`}
    </div>`
}

// 마스터는 엑셀 업로드로 갱신한다 — 여기서는 «그 해에 무엇이 들어 있는지»만 보여준다.
function masterTables() {
  const m = state.yearConfig?.masters || {items: [], depts: []}
  const rows = (arr, cols) => arr.slice(0, 200).map(r =>
    `<tr>${cols.map(c => `<td class="table-cell">${esc(r[c] ?? "")}</td>`).join("")}</tr>`).join("")
  const more = arr => arr.length > 200
    ? `<p class="mt-2 text-xs text-tri">앞 200건만 표시합니다 (전체 ${arr.length.toLocaleString()}건).</p>` : ""
  return `
    <div class="grid gap-6 p-5 sm:p-6 xl:grid-cols-2">
      <div><h4 class="text-sm font-bold text-ink">예산과목 마스터 (${m.items.length.toLocaleString()}건)</h4>
        <div class="mt-3 max-h-96 overflow-auto"><table class="w-full"><thead class="table-head">
        <tr><th class="px-3 py-2">계정코드</th><th class="px-3 py-2">과목명</th><th class="px-3 py-2">속성</th></tr></thead>
        <tbody class="divide-y divide-line-subtle">${rows(m.items, ["계정코드", "과목명", "속성"])}</tbody></table></div>${more(m.items)}</div>
      <div><h4 class="text-sm font-bold text-ink">부서코드 마스터 (${m.depts.length.toLocaleString()}건)</h4>
        <div class="mt-3 max-h-96 overflow-auto"><table class="w-full"><thead class="table-head">
        <tr><th class="px-3 py-2">부서코드</th><th class="px-3 py-2">부서명</th><th class="px-3 py-2">처지사</th></tr></thead>
        <tbody class="divide-y divide-line-subtle">${rows(m.depts, ["부서코드", "부서명", "처지사"])}</tbody></table></div>${more(m.depts)}</div>
    </div>`
}

export function renderYearConfig() {
  const tab = state.ycTab || "depts"
  const locked = !!state.status?.locked
  const btn = (k, label) => `<button class="${tab === k ?"btn-primary" : "btn-secondary"}" data-yctab="${esc(k)}">${esc(label)}</button>`
  const body = tab === "depts" ? deptTable(locked)
    : tab === "master" ? masterTables()
    : tab === "alias" ? aliasTable()
    : itemTable(tab, locked)
  // 마스터·별칭은 여기서 저장하지 않는다 — 마스터는 엑셀 업로드, 별칭은 즉시 저장이다.
  const savable = tab === "depts" || tab === "손익" || tab === "자본"
  return `
  <section class="panel overflow-hidden">
    <div class="border-b border-line p-5 sm:p-6">
      <h3 class="section-title">📐 ${esc(state.year)}년 기준정보</h3>
      <p class="section-help">이 연도에만 적용됩니다. 지사는 준공·이관으로 성격이 바뀌므로(양산지사는 2023년 DH, 2025년 중대형CHP) 연도마다 따로 관리합니다. 저장하면 상단 <b>분석 반영</b>에 포함됩니다.</p>
      ${locked ? `<p class="mt-3 text-xs font-semibold text-warn">🔒 ${esc(state.year)}년은 마감 상태라 기준정보를 고칠 수 없습니다 — 위 '잠금 해제'를 먼저 누르세요.</p>` : ""}
      <div class="mt-4 flex flex-wrap gap-2">${TABS.map(([k, l]) => btn(k, l)).join("")}</div>
    </div>
    ${body}
    ${savable ? `<div class="border-t border-line p-5"><button class="btn-primary" data-action="save-yearconfig" ${locked ? "disabled" : ""}>저장</button></div>` : ""}
  </section>`
}
