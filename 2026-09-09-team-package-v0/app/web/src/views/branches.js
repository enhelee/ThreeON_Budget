import { rateBadge } from "../components/badges.js"
import { amounts } from "../data.js"
import { emptyState } from "../components/widgets.js"
import { state } from "../state.js"
import { esc, fmt, fmtRate, rateVal } from "../util.js"

export function brResultsHtml() {
  const all = (state.branches || []).map(r => ({...r, ...amounts(r)}))
    .filter(r => r.branch.toLocaleLowerCase("ko").includes(state.search.trim().toLocaleLowerCase("ko")));
  const rows = all.filter(r => !r.unmapped);
  const unmappedRows = all.filter(r => r.unmapped);   // 미매핑 가상 지사 → 맨 아래
  if (state.sort === "rateAsc") rows.sort((a, b) => (rateVal(a.plan, a.actual) ?? Infinity) - (rateVal(b.plan, b.actual) ?? Infinity));
  else if (state.sort === "planDesc") rows.sort((a, b) => b.plan - a.plan);
  else if (state.sort === "branchAsc") rows.sort((a, b) => a.branch.localeCompare(b.branch, "ko"));
  else rows.sort((a, b) => (rateVal(b.plan, b.actual) ?? -Infinity) - (rateVal(a.plan, a.actual) ?? -Infinity));
  const tot = rows.reduce((a, r) => { a.plan += r.plan; a.actual += r.actual; return a; }, {plan: 0, actual: 0});
  return `
      <section class="grid gap-4 sm:grid-cols-3"><article class="metric-card"><p class="text-sm font-semibold text-slate-500">조회 지사</p><p class="mt-3 text-2xl font-bold">${rows.length}개</p></article><article class="metric-card"><p class="text-sm font-semibold text-slate-500">조회 계획</p><p class="mt-3 text-2xl font-bold">${fmt(tot.plan)} <span class="text-xs font-semibold text-slate-400">천원</span></p></article><article class="metric-card"><p class="text-sm font-semibold text-slate-500">조회 집행률</p><p class="mt-3 text-2xl font-bold">${fmtRate(tot.plan, tot.actual)}</p></article></section>
      <section class="panel mt-6 overflow-hidden">
        ${rows.length ? `<div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-4 py-3">지사명</th><th class="px-4 py-3 text-right">계획</th><th class="px-4 py-3 text-right">실적</th><th class="px-4 py-3 text-right">잔액</th><th class="px-4 py-3 text-right">집행률</th><th class="px-4 py-3 text-right">검토대상</th></tr></thead>
        <tbody class="divide-y divide-slate-100">${rows.map(r => `<tr class="clickable hover:bg-blue-50/40" data-branch="${esc(r.branch)}"><td class="table-cell font-semibold text-slate-900">${esc(r.branch)}</td><td class="table-cell text-right">${fmt(r.plan)}</td><td class="table-cell text-right">${fmt(r.actual)}</td><td class="table-cell text-right ${r.plan - r.actual < 0 ? "text-red-600" : ""}">${fmt(r.plan - r.actual)}</td><td class="table-cell text-right">${rateBadge(r.plan, r.actual)}</td><td class="table-cell text-right">${r.lowConf ? `<span class="badge bg-amber-50 text-amber-700">${r.lowConf}건</span>` : '<span class="text-xs text-slate-400">-</span>'}</td></tr>`).join("")}
        ${unmappedRows.map(r => `<tr class="clickable row-unmapped hover:bg-blue-50/40" data-branch="${esc(r.branch)}"><td class="table-cell font-semibold text-red-600">${esc(r.branch)}</td><td class="table-cell text-right text-slate-400">-</td><td class="table-cell text-right text-slate-400">-</td><td class="table-cell text-right text-slate-400">-</td><td class="table-cell text-right"><span class="badge bg-slate-100 text-red-600">종합표 미포함</span></td><td class="table-cell text-right"><span class="badge bg-slate-100 text-red-600">미매핑 ${r.unmapped}건 · ${fmt(r.unmappedAmt)}천원</span></td></tr>`).join("")}</tbody>
        <tfoot class="border-t-2 border-slate-200 bg-slate-50"><tr><td class="table-cell font-bold text-slate-950">합계</td><td class="table-cell text-right font-bold">${fmt(tot.plan)}</td><td class="table-cell text-right font-bold">${fmt(tot.actual)}</td><td class="table-cell text-right font-bold">${fmt(tot.plan - tot.actual)}</td><td class="table-cell text-right font-bold">${fmtRate(tot.plan, tot.actual)}</td><td></td></tr></tfoot></table></div>` : emptyState("분석 이력이 없거나 검색 결과가 없습니다.")}
      </section>`;
}

export function renderBranches() {
  return `
    <div class="space-y-6">
      <section class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between"><div><p class="text-sm font-semibold text-blue-700">실적 분석</p><h2 class="mt-1 text-2xl font-bold tracking-tight text-slate-950">전체 지사 현황 — ${esc(state.year)}년</h2><p class="mt-2 text-sm text-slate-500">지사를 클릭하면 상세 검토 화면으로 이동합니다. (단위: 천원)</p></div></section>
      <section class="panel p-5"><div class="flex flex-wrap items-end gap-3">
        <label class="block min-w-48 flex-1"><span class="mb-1.5 block text-xs font-semibold text-slate-500">지사명 검색</span><input class="control w-full" data-filter="search" value="${esc(state.search)}" placeholder="지사명을 입력하세요"></label>
        <label class="block"><span class="mb-1.5 block text-xs font-semibold text-slate-500">예산 구분</span><select class="control" data-filter="type"><option value="all" ${state.type === "all" ? "selected" : ""}>전체</option><option value="profit" ${state.type === "profit" ? "selected" : ""}>손익</option><option value="capital" ${state.type === "capital" ? "selected" : ""}>자본</option></select></label>
        <label class="block"><span class="mb-1.5 block text-xs font-semibold text-slate-500">정렬</span><select class="control" data-filter="sort"><option value="rateDesc" ${state.sort === "rateDesc" ? "selected" : ""}>집행률 높은 순</option><option value="rateAsc" ${state.sort === "rateAsc" ? "selected" : ""}>집행률 낮은 순</option><option value="planDesc" ${state.sort === "planDesc" ? "selected" : ""}>예산 금액 큰 순</option><option value="branchAsc" ${state.sort === "branchAsc" ? "selected" : ""}>지사명 순</option></select></label>
      </div></section>
      <div id="brResults">${brResultsHtml()}</div>
    </div>`;
}

// ───────────────────────── 3+ 실적분석(상세) ─────────────────────────
