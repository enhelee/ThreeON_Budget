import { rateBadge } from "../components/badges.js"
import { emptyState } from "../components/widgets.js"
import { state } from "../state.js"
import { esc, fmt, fmtRate } from "../util.js"

/** 증감률 — 부호 항상, 소수 한 자리, 천 단위 쉼표(+2,805.0% / -23.4%). */
const signPct = v => `${v >= 0 ? "+" : ""}${Number(v).toLocaleString("ko-KR", {minimumFractionDigits: 1, maximumFractionDigits: 1})}%`

/** 과목 행을 펼치면 지사별 계획·실적 — 지사를 누르면 3+ 상세(그 과목만)로 가서 사업 → 전표·매칭 근거까지 본다. */
function drillRows(budget, x) {
  if (state.statOpen !== `${budget}|${x.예산과목}`) return "";
  return (x.지사 || []).map(b => `
    <tr class="voucher-row">
      <td class="table-cell"></td>
      <td class="table-cell pl-8 text-sm text-ink">${esc(b.처지사)} <span class="text-xs text-tri">· 사업 ${b.사업수}</span></td>
      <td class="table-cell text-right text-sm">${fmt(b.계획)}</td>
      <td class="table-cell text-right text-sm font-semibold">${fmt(b.실적)}</td>
      <td class="table-cell" colspan="2"></td>
      <td class="table-cell text-right">${b.계획 > 0 ? rateBadge(b.계획, b.실적) : '<span class="text-xs text-tri">계획 없음</span>'}</td>
      <td class="table-cell text-right" colspan="2">${b.처지사 === "(미매핑)" ? "" : `<button class="text-xs font-semibold text-ink hover:text-mint-ink" data-drill="${esc(b.처지사)}" data-drill-item="${esc(x.예산과목)}" data-drill-budget="${esc(budget)}">전표 보기 →</button>`}</td>
    </tr>`).join("");
}

// 탭(2026-10-27 사용자 요청: 5번·설정처럼 한 묶음씩) — 손익 / 자본 / 전년 대비. 자료는 연 탭 것만 받는다(router).
export const STATS_TABS = [["손익", "손익예산"], ["자본", "자본예산"], ["compare", "전년 대비 증감"]]
const UNIT = '<span class="text-xs font-semibold text-tri">단위: 천원</span>'

export function renderStats() {
  const tab = state.statsTab || "손익";
  const title = `<section><p class="text-sm font-semibold text-ink">STAGE 4</p><h2 class="mt-1 font-hanan text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">통계 · 내보내기 — ${esc(state.year)}년</h2></section>
    <div class="flex flex-wrap gap-2" role="tablist">${STATS_TABS.map(([k, l]) => `<button class="${tab === k ? "btn-primary" : "btn-secondary"}" role="tab" aria-selected="${tab === k}" data-stattab="${k}">${esc(l)}</button>`).join("")}</div>`;
  if (tab === "compare") return `<div class="space-y-6">${title}${compareHtml()}</div>`;
  const st = state.stats;
  if (!st || !Object.keys(st.budgets || {}).length) {
    return `<div class="space-y-6">${title}${emptyState("분석 이력이 없습니다. 먼저 분석을 실행하세요.")}</div>`;
  }
  const sections = Object.entries(st.budgets).filter(([budget]) => budget === tab).map(([budget, data]) => {
    const items = data.items;
    const tot = items.reduce((a, x) => { a.p += x.계획; a.a += x.실적; a.e += x.집행 || 0; a.n += x.신규 || 0; a.c += x.사업수 || 0; a.m += x.미시행 || 0; return a; }, {p: 0, a: 0, e: 0, n: 0, c: 0, m: 0});
    const maxA = Math.max(1, ...data.groups.map(g => Math.max(g.계획, g.실적)));
    return `
      <section class="panel overflow-hidden">
        <div class="flex flex-wrap items-start justify-between gap-3 border-b border-line p-5 sm:p-6">
          <h3 class="section-title">${budget}예산 — 과목별 계획 대비 실적</h3>
          <div class="flex flex-wrap gap-2">
            <button class="btn-primary" data-export="actual" data-budget="${budget}" title="양식2·3 실적 집계표(xlsx) — 분석 후 첫 다운로드는 파일 생성으로 시간이 걸립니다">실적 집계표</button>
            <button class="btn-secondary" data-export="v1" data-budget="${budget}" title="zrfm2 원본에 매칭 결과 열을 붙인 전표 원장(xlsx) — 분석 후 첫 다운로드는 파일 생성으로 시간이 걸립니다">전표+매칭 원장</button>
            <button class="btn-secondary" data-export="matched" data-budget="${budget}" title="전표 한 줄마다 붙은 사업·확신도(CSV, 다른 프로그램 연계용)">전표별 매칭 CSV</button>
          </div>
        </div>
        <div class="flex justify-end px-5 pt-3 sm:px-6">${UNIT}</div>
        <div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-4 py-3">대분류</th><th class="px-4 py-3">예산과목</th><th class="px-4 py-3 text-right">계획(A)</th><th class="px-4 py-3 text-right">실적(B)</th><th class="px-4 py-3 text-right">└ 계획집행</th><th class="px-4 py-3 text-right">└ 신규</th><th class="px-4 py-3 text-right">집행률</th><th class="px-4 py-3 text-right">사업수</th><th class="px-4 py-3 text-right">미시행</th></tr></thead>
        <tbody class="divide-y divide-line-subtle">${items.map(x => `<tr class="clickable hover:bg-subtle" data-stat-item="${esc(budget)}|${esc(x.예산과목)}" title="눌러서 지사별 실적 → 전표까지 내려가 보기"><td class="table-cell text-sub">${esc(x.대분류)}</td><td class="table-cell font-semibold text-ink"><span class="mr-1 inline-block w-3 text-tri">${state.statOpen === `${budget}|${x.예산과목}` ? "▾" : "▸"}</span>${esc(x.예산과목)}</td><td class="table-cell text-right">${fmt(x.계획)}</td><td class="table-cell text-right font-semibold">${fmt(x.실적)}</td><td class="table-cell text-right text-sub">${fmt(x.집행)}</td><td class="table-cell text-right text-sub">${fmt(x.신규)}</td><td class="table-cell text-right">${rateBadge(x.계획, x.실적)}</td><td class="table-cell text-right">${x.사업수}</td><td class="table-cell text-right ${x.미시행 ?"text-warn" : "text-tri"}">${x.미시행}</td></tr>${drillRows(budget, x)}`).join("")}</tbody>
        <tfoot class="border-t-2 border-line bg-subtle"><tr><td class="table-cell font-bold" colspan="2">합계</td><td class="table-cell text-right font-bold">${fmt(tot.p)}</td><td class="table-cell text-right font-bold">${fmt(tot.a)}</td><td class="table-cell text-right text-sub">${fmt(tot.e)}</td><td class="table-cell text-right text-sub">${fmt(tot.n)}</td><td class="table-cell text-right font-bold">${fmtRate(tot.p, tot.a)}</td><td class="table-cell text-right">${fmt(tot.c)}</td><td class="table-cell text-right">${fmt(tot.m)}</td></tr></tfoot></table></div>
        <div class="border-t border-line p-5 sm:p-6"><div class="flex flex-wrap items-center justify-between gap-3"><h4 class="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm font-bold text-ink">지사그룹별
            <span class="inline-flex items-center gap-1.5 text-xs font-semibold text-sub"><span class="yr-dot yr-dot--plan"></span>계획</span><span class="inline-flex items-center gap-1.5 text-xs font-semibold text-sub"><span class="yr-dot yr-dot--act"></span>실적</span></h4>${UNIT}</div>
          <div class="mt-4 space-y-4">${data.groups.map(g => `<div><div class="mb-2 flex items-end justify-between"><span class="font-semibold text-ink">${esc(g.그룹)}</span><span class="flex items-center gap-2 text-xs text-sub"><span class="inline-flex items-center gap-1"><span class="yr-dot yr-dot--plan"></span><span class="font-semibold text-ink">${fmt(g.계획)}</span></span>/<span class="inline-flex items-center gap-1"><span class="yr-dot yr-dot--act"></span><span class="font-semibold text-ink">${fmt(g.실적)}</span></span> · ${fmtRate(g.계획, g.실적)}</span></div>
          <div class="space-y-1.5"><div class="h-3 overflow-hidden rounded-full bg-subtle" title="계획 ${fmt(g.계획)} 천원"><div class="yr-bar yr-bar--plan h-full rounded-full" style="width:${g.계획 / maxA * 100}%"></div></div>
          <div class="h-3 overflow-hidden rounded-full bg-subtle" title="실적 ${fmt(g.실적)} 천원"><div class="yr-bar yr-bar--act h-full rounded-full" style="width:${g.실적 / maxA * 100}%"></div></div></div></div>`).join("")}</div></div>
      </section>`;
  }).join("");
  return `<div class="space-y-6">${title}${sections || emptyState(`${esc(tab)}예산 분석 결과가 없습니다.`)}</div>`;
}

function compareHtml() {
  const cmp = state.statsCompare;
  if (!cmp) return `<section class="panel p-6 text-sm text-tri">불러오는 중…</section>`;
  if (!cmp.prev) return emptyState("비교할 전년 분석 결과가 없습니다.");
  return Object.entries(cmp.budgets).map(([budget, items]) => {
    const t = items.reduce((a, x) => { a.o += x.전년실적; a.c += x.당년실적; return a; }, {o: 0, c: 0});
    return `
    <section class="panel overflow-hidden">
      <div class="flex flex-wrap items-center justify-between gap-3 border-b border-line p-5 sm:p-6"><h3 class="section-title">${budget}예산 — 전년 대비 증감 (${cmp.prev}년 → ${esc(state.year)}년)</h3>${UNIT}</div>
      <div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-4 py-3">예산과목</th><th class="px-4 py-3 text-right">${cmp.prev}년 실적</th><th class="px-4 py-3 text-right">${esc(state.year)}년 실적</th><th class="px-4 py-3 text-right">증감</th><th class="px-4 py-3 text-right">증감률</th></tr></thead>
      <tbody class="divide-y divide-line-subtle">${items.map(x => `<tr class="hover:bg-subtle"><td class="table-cell font-semibold text-ink">${esc(x.예산과목)}</td><td class="table-cell text-right">${fmt(x.전년실적)}</td><td class="table-cell text-right font-semibold">${fmt(x.당년실적)}</td><td class="table-cell text-right ${x.증감 < 0 ?"text-err" : "text-ok"}">${x.증감 >= 0 ? "+" : ""}${fmt(x.증감)}</td><td class="table-cell text-right">${x.증감률 === null ? '<span class="badge bg-warn-bg text-warn">신규</span>' : `<span class="badge ${x.증감률 >= 0 ?"bg-ok-bg text-ok" : "bg-warn-bg text-warn"}">${signPct(x.증감률)}</span>`}</td></tr>`).join("")}</tbody>
      <tfoot class="border-t-2 border-line bg-subtle"><tr><td class="table-cell font-bold">합계</td><td class="table-cell text-right font-bold">${fmt(t.o)}</td><td class="table-cell text-right font-bold">${fmt(t.c)}</td><td class="table-cell text-right font-bold ${t.c - t.o < 0 ?"text-err" : ""}">${t.c - t.o >= 0 ? "+" : ""}${fmt(t.c - t.o)}</td><td class="table-cell text-right font-bold">${t.o ? signPct((t.c - t.o) / t.o * 100) : "-"}</td></tr></tfoot></table></div>
    </section>`;
  }).join("");
}

// ───────────────────────── 5 중장기 예측 / 설정 ─────────────────────────
