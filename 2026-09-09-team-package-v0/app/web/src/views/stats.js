import { rateBadge } from "../components/badges.js"
import { emptyState } from "../components/widgets.js"
import { state } from "../state.js"
import { esc, fmt, fmtRate } from "../util.js"

export function renderStats() {
  const st = state.stats;
  if (!st || !Object.keys(st.budgets || {}).length) {
    return `<div class="space-y-6"><section><p class="text-sm font-semibold text-blue-700">STAGE 4</p><h2 class="mt-1 text-2xl font-bold tracking-tight text-slate-950">통계 · 내보내기 — ${esc(state.year)}년</h2></section>${emptyState("분석 이력이 없습니다. 먼저 분석을 실행하세요.")}</div>`;
  }
  const sections = Object.entries(st.budgets).map(([budget, data]) => {
    const items = data.items;
    const tot = items.reduce((a, x) => { a.p += x.계획; a.a += x.실적; return a; }, {p: 0, a: 0});
    const maxA = Math.max(1, ...data.groups.map(g => Math.max(g.계획, g.실적)));
    return `
      <section class="panel overflow-hidden">
        <div class="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 p-5 sm:p-6">
          <div><h3 class="section-title">${budget}예산 — 과목별 계획 대비 실적</h3><p class="section-help">${esc(state.year)}년 · 25년 확정 분류체계 · 단위: 천원</p></div>
          <div class="flex flex-wrap gap-2">
            <button class="btn-primary" data-export="actual" data-budget="${budget}" title="분석 후 첫 다운로드는 파일 생성으로 30초쯤 걸립니다">실적 Excel</button>
            <button class="btn-secondary" data-export="v1" data-budget="${budget}" title="분석 후 첫 다운로드는 파일 생성으로 30초쯤 걸립니다">zrfm2_V1</button>
            <button class="btn-secondary" data-export="matched" data-budget="${budget}" title="분석 후 첫 다운로드는 파일 생성으로 30초쯤 걸립니다">matched CSV</button>
          </div>
        </div>
        <div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-4 py-3">대분류</th><th class="px-4 py-3">예산과목</th><th class="px-4 py-3 text-right">계획(A)</th><th class="px-4 py-3 text-right">실적(B)</th><th class="px-4 py-3 text-right">└ 계획집행</th><th class="px-4 py-3 text-right">└ 신규</th><th class="px-4 py-3 text-right">집행률</th><th class="px-4 py-3 text-right">사업수</th><th class="px-4 py-3 text-right">미시행</th></tr></thead>
        <tbody class="divide-y divide-slate-100">${items.map(x => `<tr class="hover:bg-slate-50"><td class="table-cell text-slate-500">${esc(x.대분류)}</td><td class="table-cell font-semibold text-slate-900">${esc(x.예산과목)}</td><td class="table-cell text-right">${fmt(x.계획)}</td><td class="table-cell text-right font-semibold">${fmt(x.실적)}</td><td class="table-cell text-right text-slate-500">${fmt(x.집행)}</td><td class="table-cell text-right text-slate-500">${fmt(x.신규)}</td><td class="table-cell text-right">${rateBadge(x.계획, x.실적)}</td><td class="table-cell text-right">${x.사업수}</td><td class="table-cell text-right ${x.미시행 ? "text-amber-700" : "text-slate-400"}">${x.미시행}</td></tr>`).join("")}</tbody>
        <tfoot class="border-t-2 border-slate-200 bg-slate-50"><tr><td class="table-cell font-bold" colspan="2">합계</td><td class="table-cell text-right font-bold">${fmt(tot.p)}</td><td class="table-cell text-right font-bold">${fmt(tot.a)}</td><td colspan="2"></td><td class="table-cell text-right font-bold">${fmtRate(tot.p, tot.a)}</td><td colspan="2"></td></tr></tfoot></table></div>
        <div class="border-t border-slate-200 p-5 sm:p-6"><h4 class="text-sm font-bold text-slate-700">지사그룹별 (계획 파랑 · 실적 청록)</h4>
          <div class="mt-4 space-y-4">${data.groups.map(g => `<div><div class="mb-2 flex items-end justify-between"><span class="font-semibold text-slate-800">${esc(g.그룹)}</span><span class="text-xs text-slate-500"><span class="font-semibold text-blue-700">${fmt(g.계획)}</span> / <span class="font-semibold text-emerald-700">${fmt(g.실적)}</span> · ${fmtRate(g.계획, g.실적)}</span></div>
          <div class="space-y-1.5"><div class="h-3 overflow-hidden rounded-full bg-slate-100"><div class="h-full rounded-full bg-blue-500" style="width:${g.계획 / maxA * 100}%"></div></div>
          <div class="h-3 overflow-hidden rounded-full bg-slate-100"><div class="h-full rounded-full bg-emerald-500" style="width:${g.실적 / maxA * 100}%"></div></div></div></div>`).join("")}</div></div>
      </section>`;
  }).join("");
  const cmp = state.statsCompare;
  const cmpSection = !cmp || !cmp.prev ? "" : Object.entries(cmp.budgets).map(([budget, items]) => {
    const t = items.reduce((a, x) => { a.o += x.전년실적; a.c += x.당년실적; return a; }, {o: 0, c: 0});
    return `
    <section class="panel overflow-hidden">
      <div class="border-b border-slate-200 p-5 sm:p-6"><h3 class="section-title">${budget}예산 — 전년 대비 증감 (${cmp.prev}년 → ${esc(state.year)}년)</h3><p class="section-help">각 연도의 최신 분석 실적 기준 · 단위: 천원</p></div>
      <div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-4 py-3">예산과목</th><th class="px-4 py-3 text-right">${cmp.prev}년 실적</th><th class="px-4 py-3 text-right">${esc(state.year)}년 실적</th><th class="px-4 py-3 text-right">증감</th><th class="px-4 py-3 text-right">증감률</th></tr></thead>
      <tbody class="divide-y divide-slate-100">${items.map(x => `<tr class="hover:bg-slate-50"><td class="table-cell font-semibold text-slate-900">${esc(x.예산과목)}</td><td class="table-cell text-right">${fmt(x.전년실적)}</td><td class="table-cell text-right font-semibold">${fmt(x.당년실적)}</td><td class="table-cell text-right ${x.증감 < 0 ? "text-red-600" : "text-emerald-700"}">${x.증감 >= 0 ? "+" : ""}${fmt(x.증감)}</td><td class="table-cell text-right">${x.증감률 === null ? '<span class="badge bg-amber-50 text-amber-700">신규</span>' : `<span class="badge ${x.증감률 >= 0 ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}">${x.증감률 >= 0 ? "+" : ""}${x.증감률}%</span>`}</td></tr>`).join("")}</tbody>
      <tfoot class="border-t-2 border-slate-200 bg-slate-50"><tr><td class="table-cell font-bold">합계</td><td class="table-cell text-right font-bold">${fmt(t.o)}</td><td class="table-cell text-right font-bold">${fmt(t.c)}</td><td class="table-cell text-right font-bold ${t.c - t.o < 0 ? "text-red-600" : ""}">${t.c - t.o >= 0 ? "+" : ""}${fmt(t.c - t.o)}</td><td class="table-cell text-right font-bold">${t.o ? ((t.c - t.o) / t.o * 100).toFixed(1) + "%" : "-"}</td></tr></tfoot></table></div>
    </section>`;
  }).join("");
  const teamSection = `
    <section class="panel p-5 sm:p-6">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div><h3 class="section-title">팀 연계 — 예산예측프로그램(팀공유 v2)으로 넘기기</h3>
        <p class="section-help">손익·자본 최신 분석을 한 파일에 담습니다. <b>결과 JSON</b>은 v2 앱의 「예산 실적 집계 → 사업 실적 연결」에 올려 표준화·중장기 예산(3·4단계) 입력으로 쓰고, CSV 3종은 연동규격(연도 단일 파일, 원 단위)입니다. 첫 다운로드는 파일 생성으로 30초쯤 걸립니다.</p></div>
        <div class="flex flex-wrap gap-2">
          <button class="btn-primary" data-team-export="json" title="팀연계_${esc(state.year)}_사업실적연결.json">결과 JSON (사업 실적 연결)</button>
          <button class="btn-secondary" data-team-export="matched" title="matched_${esc(state.year)}.csv">matched 통합 CSV</button>
          <button class="btn-secondary" data-team-export="budget" title="budget_${esc(state.year)}.csv">budget CSV</button>
          <button class="btn-secondary" data-team-export="data" title="data_${esc(state.year)}.csv">data CSV</button>
        </div>
      </div>
    </section>`;
  return `<div class="space-y-6">
    <section><p class="text-sm font-semibold text-blue-700">STAGE 4</p><h2 class="mt-1 text-2xl font-bold tracking-tight text-slate-950">통계 · 내보내기 — ${esc(state.year)}년</h2>
    <p class="mt-2 text-sm text-slate-500">검토(재배정·수정)가 반영된 최신 분석 기준입니다.</p></section>
    ${teamSection}${sections}${cmpSection}</div>`;
}

// ───────────────────────── 5 중장기 예측 / 설정 ─────────────────────────
