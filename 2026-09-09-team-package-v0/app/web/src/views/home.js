import { rateBadge } from "../components/badges.js"
import { emptyState } from "../components/widgets.js"
import { state } from "../state.js"
import { fmt, fmtRate } from "../util.js"

export function renderHome() {
  const ov = state.overview || [];
  const analyzed = ov.filter(r => r["손익"] || r["자본"]);
  const cur = ov.find(r => String(r.year) === String(state.year));
  const recent = analyzed.slice(-5);          // 최근 최대 5개년(오름차순)
  const maxV = Math.max(1, ...recent.flatMap(r => ["손익", "자본"].flatMap(b =>
    r[b] ? [r[b].계획, r[b].실적] : [])));
  const yearTotal = b => b ? (b.계획 || 0) : 0;

  const cards = ["손익", "자본"].map(b => {
    const s = cur?.[b];
    return `<article class="metric-card"><div class="flex items-center justify-between"><p class="text-sm font-semibold text-slate-500">${state.year}년 ${b}예산</p>${s ? `<span class="badge bg-emerald-50 text-emerald-700">분석 완료</span>` : `<span class="badge bg-slate-100 text-slate-500">미실행</span>`}</div>
      ${s ? `<p class="mt-4 text-2xl font-bold tracking-tight text-slate-950">${fmt(s.실적)} <span class="text-sm font-semibold text-slate-400">천원</span></p>
      <p class="mt-2 text-sm text-slate-500">계획 ${fmt(s.계획)} · 현재까지 집행률 <b>${s.집행률 ?? "-"}%</b></p>` :
      `<p class="mt-4 text-sm text-slate-500">'분석 실행'을 눌러 집계하세요.</p>`}</article>`;
  }).join("");
  const curAll = cur && (cur["손익"] || cur["자본"]) ? {
    p: (cur["손익"]?.계획 || 0) + (cur["자본"]?.계획 || 0),
    a: (cur["손익"]?.실적 || 0) + (cur["자본"]?.실적 || 0),
  } : null;

  return `
    <div class="space-y-6">
      <section class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div><p class="text-sm font-semibold text-blue-700">통합 현황</p>
        <h2 class="mt-1 text-2xl font-bold tracking-tight text-slate-950">다년도 예산·실적 현황</h2>
        <p class="mt-2 text-sm text-slate-500">분석 완료된 모든 연도를 집계합니다. (단위: 천원)</p></div>
      </section>
      ${!analyzed.length ? emptyState("아직 분석 이력이 없습니다. ① 계획 업로드 → ② zrfm2 업로드 → 상단 '분석 실행'을 눌러주세요.") : `
      <section class="grid gap-4 md:grid-cols-3">
        ${cards}
        <article class="metric-card"><div class="flex items-center justify-between"><p class="text-sm font-semibold text-slate-500">${state.year}년 전체(손익+자본)</p><span class="badge bg-blue-50 text-blue-700">현재까지</span></div>
        ${curAll ? `<p class="mt-4 text-2xl font-bold tracking-tight text-slate-950">${fmt(curAll.a)} <span class="text-sm font-semibold text-slate-400">천원</span></p>
        <p class="mt-2 text-sm text-slate-500">계획 ${fmt(curAll.p)} · 집행률 ${fmtRate(curAll.p, curAll.a)}</p>` : `<p class="mt-4 text-sm text-slate-500">해당 연도 분석 이력이 없습니다.</p>`}</article>
      </section>
      <section class="grid gap-6 xl:grid-cols-[1.05fr_.95fr]">
        <article class="panel p-5 sm:p-6">
          <div class="flex flex-wrap items-start justify-between gap-3"><div><h3 class="section-title">최근 ${recent.length}개년 실적 분석</h3><p class="section-help">파랑=계획 · 청록=실적 (손익+자본, 천원)</p></div><span class="badge bg-slate-100 text-slate-600">${recent.length}개 연도</span></div>
          <div class="mt-7 space-y-6">
            ${recent.map(r => {
              const p = (r["손익"]?.계획 || 0) + (r["자본"]?.계획 || 0);
              const a = (r["손익"]?.실적 || 0) + (r["자본"]?.실적 || 0);
              return `<div><div class="mb-2 flex items-end justify-between gap-3"><div><span class="font-bold text-slate-800 clickable" data-goyear="${r.year}">${r.year}</span><span class="ml-2 text-xs text-slate-500">집행률 ${fmtRate(p, a)}</span></div>
              <div class="text-right text-xs text-slate-500"><span class="font-semibold text-blue-700">${fmt(p)}</span><span class="mx-1">/</span><span class="font-semibold text-emerald-700">${fmt(a)}</span></div></div>
              <div class="space-y-1.5"><div class="h-3 overflow-hidden rounded-full bg-slate-100"><div class="h-full rounded-full bg-blue-500" style="width:${p / maxV * 100}%"></div></div>
              <div class="h-3 overflow-hidden rounded-full bg-slate-100"><div class="h-full rounded-full bg-emerald-500" style="width:${a / maxV * 100}%"></div></div></div></div>`;
            }).join("")}
          </div>
          <p class="mt-6 flex items-center gap-2 text-xs text-slate-500"><span class="h-2 w-2 rounded-full bg-slate-300"></span>연도를 클릭하면 해당 연도로 전환됩니다. 자료가 없는 연도는 계산하지 않습니다.</p>
        </article>
        <article class="panel overflow-hidden">
          <div class="flex items-start justify-between gap-3 border-b border-slate-200 p-5 sm:p-6"><div><h3 class="section-title">연도별 요약</h3><p class="section-help">각 연도의 최신 분석 기준</p></div><button class="text-sm font-semibold text-blue-700 hover:text-blue-900" data-view="branches">전체 지사 →</button></div>
          <div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-4 py-3">연도</th><th class="px-4 py-3">구분</th><th class="px-4 py-3 text-right">계획</th><th class="px-4 py-3 text-right">실적</th><th class="px-4 py-3 text-right">집행률</th></tr></thead>
          <tbody class="divide-y divide-slate-100">${analyzed.slice().reverse().flatMap(r => ["손익", "자본"].filter(b => r[b]).map(b => `<tr class="hover:bg-slate-50 clickable" data-goyear="${r.year}"><td class="table-cell font-semibold text-slate-900">${r.year}</td><td class="table-cell">${b}</td><td class="table-cell text-right">${fmt(r[b].계획)}</td><td class="table-cell text-right">${fmt(r[b].실적)}</td><td class="table-cell text-right">${rateBadge(r[b].계획, r[b].실적)}</td></tr>`)).join("")}</tbody></table></div>
        </article>
      </section>`}
    </div>`;
}
