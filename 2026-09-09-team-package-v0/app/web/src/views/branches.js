import { rateBadge } from "../components/badges.js"
import { amounts } from "../data.js"
import { emptyState } from "../components/widgets.js"
import { state } from "../state.js"
import { esc, fmt, fmtRate, rateVal } from "../util.js"

/** 차이 사유 입력 현황 — 남으면 노랑, 다 적었으면 초록. 권장 입력이라 빨강은 쓰지 않는다. */
function varianceBadge(r) {
  if (!r.variance) return '<span class="text-xs text-tri">-</span>';
  const done = r.varianceNoted || 0;
  const cls = done >= r.variance ? "bg-ok-bg text-ok" : "bg-warn-bg text-warn";
  return `<span class="badge ${cls}">${done}/${r.variance}</span>`;
}

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
      <section class="grid gap-4 sm:grid-cols-3"><article class="metric-card"><p class="text-sm font-semibold text-sub">조회 지사</p><p class="mt-3 text-2xl font-bold">${rows.length}개</p></article><article class="metric-card"><p class="text-sm font-semibold text-sub">조회 계획</p><p class="mt-3 text-2xl font-bold">${fmt(tot.plan)} <span class="text-xs font-semibold text-tri">천원</span></p></article><article class="metric-card"><p class="text-sm font-semibold text-sub">조회 집행률</p><p class="mt-3 text-2xl font-bold">${fmtRate(tot.plan, tot.actual)}</p></article></section>
      ${rows.length ? brScatterHtml(rows) : ""}
      <section class="panel mt-6 overflow-hidden">
        <div class="flex items-center justify-between gap-3 border-b border-line px-5 py-3"><div><h3 class="section-title">지사별 계획·실적</h3><p class="text-xs text-tri">${rows.length}곳 · 합계 집행률 ${fmtRate(tot.plan, tot.actual)}${state.brTableOpen ? "" : " · 표를 접었습니다"}</p></div><button class="btn-secondary min-h-[36px] px-4 text-xs" data-brtable aria-expanded="${state.brTableOpen}" aria-controls="brTable">${state.brTableOpen ? "표 접기 ▲" : "표 펼치기 ▼"}</button></div>
        ${!state.brTableOpen ? "" : rows.length ? `<div class="overflow-x-auto" id="brTable"><table class="w-full"><thead class="table-head"><tr><th class="px-4 py-3">지사명</th><th class="px-4 py-3 text-right">계획·천원</th><th class="px-4 py-3 text-right">실적·천원</th><th class="px-4 py-3 text-right">잔액·천원</th><th class="px-4 py-3 text-right">집행률</th><th class="px-4 py-3 text-right">검토대상</th><th class="px-4 py-3 text-right" title="집행률이 계획 대비 ±20%p 를 벗어난 사업 중 사유를 적은 수 / 전체">차이 사유</th></tr></thead>
        <tbody class="divide-y divide-line-subtle">${rows.map(r => `<tr class="clickable hover:bg-subtle" data-branch="${esc(r.branch)}"><td class="table-cell font-semibold text-ink">${esc(r.branch)}</td><td class="table-cell text-right">${fmt(r.plan)}</td><td class="table-cell text-right">${fmt(r.actual)}</td><td class="table-cell text-right ${r.plan - r.actual < 0 ?"text-err" : ""}">${fmt(r.plan - r.actual)}</td><td class="table-cell text-right">${rateBadge(r.plan, r.actual)}</td><td class="table-cell text-right">${r.lowConf ? `<span class="badge bg-warn-bg text-warn">${r.lowConf}건</span>` : '<span class="text-xs text-tri">-</span>'}</td><td class="table-cell text-right">${varianceBadge(r)}</td></tr>`).join("")}
        ${unmappedRows.map(r => `<tr class="clickable row-unmapped hover:bg-subtle" data-branch="${esc(r.branch)}"><td class="table-cell font-semibold text-err">${esc(r.branch)}</td><td class="table-cell text-right text-tri">-</td><td class="table-cell text-right text-tri">-</td><td class="table-cell text-right text-tri">-</td><td class="table-cell text-right"><span class="badge bg-subtle text-err">종합표 미포함</span></td><td class="table-cell text-right"><span class="badge bg-subtle text-err">미매핑 ${r.unmapped}건 · ${fmt(r.unmappedAmt)}천원</span></td><td></td></tr>`).join("")}</tbody>
        <tfoot class="border-t-2 border-line bg-subtle"><tr><td class="table-cell font-bold text-ink">합계</td><td class="table-cell text-right font-bold">${fmt(tot.plan)}</td><td class="table-cell text-right font-bold">${fmt(tot.actual)}</td><td class="table-cell text-right font-bold">${fmt(tot.plan - tot.actual)}</td><td class="table-cell text-right font-bold">${fmtRate(tot.plan, tot.actual)}</td><td></td><td></td></tr></tfoot></table></div>` : emptyState("분석 이력이 없거나 검색 결과가 없습니다.")}
      </section>`;
}

// 계획–실적 산점도 — 대각선(집행률 100%) 위는 계획보다 더 쓴 지사, 아래는 덜 쓴 지사.
// 지사 간 규모 차가 100배라 두 축 모두 로그 눈금(억원).
// 색은 집행률 배지(badges.js rateBadge)와 같은 세 단계 — 120% 초과 빨강 · 80~120% 초록 · 80% 미만 노랑(2026-10-26 사용자 결정).
// 적록 색약에서 빨강·초록이 헷갈리므로 모양도 나눈다: 초과 ▲ · 적정 ● · 미달 ▼.
// 노랑은 흰 바탕 대비가 낮아(#C98A00 2.87:1) 배지 글자색(warn #8F6000)으로 진하게 쓴다.
const SC_OVER = "#B42318", SC_OK = "#16794A", SC_UNDER = "#8F6000";
const scColor = rate => rate > 120 ? SC_OVER : rate >= 80 ? SC_OK : SC_UNDER;
/** 점 하나 — 집행률 단계에 따라 ▲(초과)·●(적정)·▼(미달). 흰 테두리로 겹친 점도 구분된다. */
function scMark(cx, cy, rate, size = 7) {
  const c = scColor(rate), st = `fill="${c}" stroke="#FFFFFF" stroke-width="2" stroke-linejoin="round"`;
  if (rate > 120) return `<polygon points="${cx},${cy - size * 1.25} ${cx + size * 1.15},${cy + size * .85} ${cx - size * 1.15},${cy + size * .85}" ${st}/>`;
  if (rate < 80) return `<polygon points="${cx},${cy + size * 1.25} ${cx + size * 1.15},${cy - size * .85} ${cx - size * 1.15},${cy - size * .85}" ${st}/>`;
  return `<circle cx="${cx}" cy="${cy}" r="${size}" ${st}/>`;
}
/** 범례 칸 — 점과 같은 모양을 작은 SVG 로. */
const scLegend = (rate, label) => `<span class="inline-flex items-center gap-1.5"><svg viewBox="0 0 20 20" class="h-3.5 w-3.5" aria-hidden="true">${scMark(10, 10, rate, 6)}</svg>${label}</span>`;
function brScatterHtml(rows) {
  const E = v => v / 1e5;   // 천원 → 억원
  const pts = rows.filter(r => r.plan > 0).map(r => ({name: r.branch, plan: E(r.plan), act: E(r.actual), rate: rateVal(r.plan, r.actual)}));
  if (!pts.length) return "";
  const W = 1040, H = 460, L = 64, R = 24, T = 20, B = 56;
  // 축 범위(2026-10-27 사용자 요청: 점이 가운데 몰리지 않게) — 10배 단위로 넓히지 않고 1·1.5·2·3·5·7 눈금 중
  //   데이터를 감싸는 가장 좁은 값으로. 아래 끝은 «계획» 최솟값 기준 — 실적 0·소액(안전처 0.45억 등)까지 넣으면
  //   범위가 10배씩 늘어 나머지가 뭉친다. 그보다 작은 실적은 바닥선에 붙여 그린다(범례에 표시).
  const NICE = [1, 1.5, 2, 3, 5, 7];
  const niceDown = v => { const e = 10 ** Math.floor(Math.log10(v)); return e * [...NICE].reverse().find(m => m * e <= v); };
  const niceUp = v => { const e = 10 ** Math.floor(Math.log10(v)); const m = NICE.find(m => m * e >= v); return m ? m * e : 10 * e; };
  const plans = pts.map(p => p.plan), acts = pts.map(p => p.act).filter(v => v > 0);
  const lo = niceDown(Math.min(...plans) * 0.8), hi = niceUp(Math.max(...plans, ...acts) * 1.12);
  const span = Math.log10(hi) - Math.log10(lo);
  const floored = pts.filter(p => p.act < lo).length;
  const sx = v => L + (Math.log10(Math.max(v, lo)) - Math.log10(lo)) / span * (W - L - R);
  const sy = v => H - B - (Math.log10(Math.max(v, lo)) - Math.log10(lo)) / span * (H - T - B);
  const num = v => v >= 10 ? fmt(v) : String(+v.toPrecision(2));
  let s = `<defs><clipPath id="scClip"><rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}"/></clipPath></defs>`;
  const ticks = [];
  for (let e = 10 ** Math.floor(Math.log10(lo)); e <= hi; e *= 10) for (const m of [1, 2, 5]) {
    const v = +(e * m).toPrecision(3); if (v >= lo * 0.999 && v <= hi * 1.001) ticks.push([v, m]);
  }
  for (const [v, m] of ticks) {
    s += `<line x1="${sx(v)}" x2="${sx(v)}" y1="${T}" y2="${H - B}" stroke="#E5E5E5" stroke-width="${m === 1 ? 1 : .5}"/><line x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}" stroke="#E5E5E5" stroke-width="${m === 1 ? 1 : .5}"/>`;
    s += `<text x="${sx(v)}" y="${H - B + 18}" text-anchor="middle" font-size="11" fill="#767676">${num(v)}</text><text x="${L - 8}" y="${sy(v) + 4}" text-anchor="end" font-size="11" fill="#767676">${num(v)}</text>`;
  }
  // ±20% 적정 범위 띠 — 격자 위에 연한 초록(80~120% 점 색과 같은 계열)으로 깔고 경계선·이름을 달아 눈에 띄게.
  const band = (k) => `${sx(lo)},${sy(lo * k)} ${sx(hi)},${sy(hi * k)}`;
  s += `<polygon points="${band(.8)} ${[sx(hi), sy(hi * 1.2)].join(",")} ${[sx(lo), sy(lo * 1.2)].join(",")}" fill="#16794A" fill-opacity=".16" clip-path="url(#scClip)"/>`;
  for (const k of [.8, 1.2]) s += `<polyline points="${band(k)}" fill="none" stroke="#16794A" stroke-opacity=".55" stroke-width="1" stroke-dasharray="3 3" clip-path="url(#scClip)"/>`;
  { const v0 = lo * 10 ** (span * .14), ang = -Math.atan2(sy(lo) - sy(hi), sx(hi) - sx(lo)) * 180 / Math.PI;
    s += `<text transform="translate(${sx(v0)} ${sy(v0 * 1.2) - 6}) rotate(${ang})" font-size="12" font-weight="700" fill="#16794A">적정 범위 ±20% (집행률 80~120%)</text>`; }
  s += `<line x1="${sx(lo)}" y1="${sy(lo)}" x2="${sx(hi)}" y2="${sy(hi)}" stroke="#0D0D0D" stroke-width="1.5" stroke-dasharray="6 4"/>`;
  // «집행률 100%»는 차트 안에 쓰면 오른쪽 위 지사 이름과 겹쳤다(2026-10-27) — 범례로 옮긴다.
  s += `<text x="${L + 12}" y="${T + 20}" font-size="13" font-weight="600" fill="${SC_OVER}">▲ 계획보다 더 씀</text>`;
  s += `<text x="${W - R - 12}" y="${H - B - 12}" text-anchor="end" font-size="13" font-weight="600" fill="${SC_UNDER}">▼ 계획보다 덜 씀</text>`;
  s += `<text x="${(L + W - R) / 2}" y="${H - 14}" text-anchor="middle" font-size="12" font-weight="600" fill="#5D5D5D">계획 (억원) →</text>`;
  s += `<text transform="translate(16 ${(T + H - B) / 2}) rotate(-90)" text-anchor="middle" font-size="12" font-weight="600" fill="#5D5D5D">실적 (억원) →</text>`;
  // 라벨: 대각선에서 먼 6곳 + 계획 큰 4곳만(전부 달면 겹친다). 나머지는 마우스를 올리면 보인다.
  const off = p => Math.abs(Math.log((p.act || lo) / p.plan));
  const labeled = new Set([...pts].sort((a, b) => off(b) - off(a)).slice(0, 6).concat([...pts].sort((a, b) => b.plan - a.plan).slice(0, 4)).map(p => p.name));
  // 이미 글자가 있는 자리(두 귀퉁이 안내)는 라벨이 피해 간다.
  const placed = [{x: L + 8, y: T + 6, w: 150, h: 18}, {x: W - R - 160, y: H - B - 28, w: 152, h: 18}];
  for (const p of [...pts].sort((a, b) => b.plan - a.plan)) {
    const cx = sx(p.plan), cy = sy(Math.max(p.act, lo));
    s += `<g class="clickable sc-pt" data-branch="${esc(p.name)}"><title>${esc(p.name)} — 계획 ${p.plan.toFixed(1)}억 · 실적 ${p.act.toFixed(1)}억 · 집행률 ${p.rate.toFixed(1)}% (클릭: 상세)</title><circle cx="${cx}" cy="${cy}" r="14" fill="transparent"/>${scMark(cx, cy, p.rate)}</g>`;
    if (!labeled.has(p.name)) continue;
    const txt = `${p.name} ${p.rate.toFixed(0)}%`, tw = txt.length * 10.5, th = 14;
    const cands = [[cx - tw / 2, cy - 12 - th], [cx + 11, cy - th / 2], [cx - 11 - tw, cy - th / 2], [cx - tw / 2, cy + 11],
                   [cx + 11, cy - th - 9], [cx - 11 - tw, cy - th - 9], [cx + 11, cy + 9], [cx - 11 - tw, cy + 9],
                   // 바닥선처럼 점이 몰린 곳 — 한 칸·두 칸 더 위로
                   [cx - tw / 2, cy - 30 - th], [cx + 11, cy - th - 27], [cx - 11 - tw, cy - th - 27], [cx - tw / 2, cy - 48 - th]];
    const hit = (bx, by) => bx < L + 2 || bx + tw > W - R - 2 || by < T + 2 || by + th > H - B - 2 || placed.some(q => bx < q.x + q.w && bx + tw > q.x && by < q.y + q.h && by + th > q.y)
      || pts.some(o => { const ox = sx(o.plan), oy = sy(Math.max(o.act, lo)); return ox > bx - 10 && ox < bx + tw + 10 && oy > by - 10 && oy < by + th + 10; });
    const spot = cands.find(([a, b]) => !hit(a, b));
    if (!spot) continue;                    // 빈 자리가 없으면 겹쳐 쓰지 않는다 — 이름은 마우스를 올리면 보인다
    const [bx, by] = spot;
    placed.push({x: bx, y: by, w: tw, h: th});
    s += `<text x="${bx}" y="${by + 11}" font-size="12" font-weight="600" fill="#0D0D0D" pointer-events="none">${esc(txt)}</text>`;
  }
  const over = pts.filter(p => p.rate > 120).length, under = pts.filter(p => p.rate < 80).length;
  return `
      <section class="panel mt-6 p-5 sm:p-6">
        <div class="flex flex-wrap items-start justify-between gap-3"><div><h3 class="section-title">계획 대비 실적 분포</h3><p class="section-help">점을 누르면 해당 지사의 상세 분석 화면으로 이동합니다.</p></div>
        <div class="flex gap-2"><span class="badge bg-err-bg text-err">▲ 120% 초과 ${over}곳</span><span class="badge bg-warn-bg text-warn">▼ 80% 미만 ${under}곳</span></div></div>
        <div class="mt-4 overflow-x-auto"><svg viewBox="0 0 ${W} ${H}" class="mx-auto block w-full min-w-[640px]" style="max-height:68vh" role="img" aria-label="지사별 계획 대비 실적 산점도">${s}</svg></div>
        <div class="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-sub">${scLegend(121, "120% 초과")}${scLegend(100, "80~120%")}${scLegend(79, "80% 미만")}<span><span class="mr-1.5 inline-block h-3 w-5 rounded-sm align-[-2px]" style="background:rgba(22,121,74,.16);outline:1px dashed rgba(22,121,74,.55)"></span>±20% 적정 범위</span><span class="inline-flex items-center gap-1.5"><svg viewBox="0 0 22 6" class="h-1.5 w-6" aria-hidden="true"><line x1="0" y1="3" x2="22" y2="3" stroke="#0D0D0D" stroke-width="2" stroke-dasharray="5 3"/></svg>집행률 100%</span>${floored ? `<span>바닥선 = 실적 ${num(lo)}억 미만(0원 포함) ${floored}곳</span>` : ""}</div>
      </section>`;
}

export function renderBranches() {
  return `
    <div class="space-y-6">
      <section class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between"><div><p class="text-sm font-semibold text-ink">실적 분석</p><h2 class="mt-1 font-hanan text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">전체 지사 현황 — ${esc(state.year)}년</h2></div></section>
      <section class="panel p-5"><div class="flex flex-wrap items-end gap-3">
        <label class="block min-w-48 flex-1"><span class="field-label">지사명 검색</span><input class="control w-full" data-filter="search" value="${esc(state.search)}" placeholder="지사명을 입력하세요"></label>
        <label class="block"><span class="field-label">예산 구분</span><select class="control" data-filter="type"><option value="all" ${state.type === "all" ? "selected" : ""}>전체</option><option value="profit" ${state.type === "profit" ? "selected" : ""}>손익</option><option value="capital" ${state.type === "capital" ? "selected" : ""}>자본</option></select></label>
        <label class="block"><span class="field-label">정렬</span><select class="control" data-filter="sort"><option value="rateDesc" ${state.sort === "rateDesc" ? "selected" : ""}>집행률 높은 순</option><option value="rateAsc" ${state.sort === "rateAsc" ? "selected" : ""}>집행률 낮은 순</option><option value="planDesc" ${state.sort === "planDesc" ? "selected" : ""}>예산 금액 큰 순</option><option value="branchAsc" ${state.sort === "branchAsc" ? "selected" : ""}>지사명 순</option></select></label>
      </div></section>
      <div id="brResults">${brResultsHtml()}</div>
    </div>`;
}

// ───────────────────────── 3+ 실적분석(상세) ─────────────────────────
