import { yearPicker } from "../components/widgets.js"
import { state } from "../state.js"
import { esc, fmt } from "../util.js"

export function renderCollect() {
  const ds = (state.status?.datasets || []).filter(d => d.kind === "erp" && String(d.year) === String(state.year));
  const runs = state.status?.runs || {};
  const sums = ["손익", "자본"].map(b => {
    const s = runs[b]?.summary;
    if (!s) return `<article class="metric-card"><p class="text-sm font-semibold text-sub">${b} 매칭</p><p class="mt-3 text-sm text-sub">미실행</p></article>`;
    return `<article class="metric-card"><p class="text-sm font-semibold text-sub">${b} 매칭 결과</p>
      <p class="mt-3 text-3xl font-bold">${fmt(s["총 실적(천원)"])}<span class="ml-1 text-sm font-semibold text-tri">천원</span></p>
      <p class="mt-2 text-sm text-sub">계획집행 ${fmt(s["계획집행 행수"])}행 · 신규 ${fmt(s["신규 행수"])}행 · 학습확정 ${fmt(s["학습확정 전표수"] ?? 0)}건</p></article>`;
  }).join("");
  return `
    <div class="space-y-6">
      <section><p class="text-sm font-semibold text-ink">STAGE 2</p><h2 class="mt-1 font-hanan text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">실적 집계와 사업 매칭</h2>
      <p class="mt-2 text-sm text-sub">ERP(SAP) zrfm2 실적을 업로드하고 자동 매칭을 실행합니다. 저확신 항목은 실적분석(상세)에서 사람이 확인합니다.</p></section>
      ${state.status?.locked ? `<section class="rounded-card border border-warn bg-warn-bg p-4 text-sm font-semibold text-warn">🔒 ${esc(state.year)}년은 마감(잠금) 상태 — 업로드·분석이 차단됩니다.</section>` : ""}
      <section class="panel p-5">${yearPicker("cp")}</section>
      <section class="grid gap-6 xl:grid-cols-[1fr_.75fr]">
        <article class="panel p-6"><h3 class="section-title">ERP(zrfm2) 업로드 — <span class="text-ink">${esc(state.year)}년</span>으로 등록</h3>
          <p class="section-help">SAP에서 추출한 zrfm2 원본 그대로 — 합계행·타연도 전표는 자동으로 걸러집니다.</p>
          <button class="mt-6 grid w-full place-items-center rounded-card border-2 border-dashed border-line-strong bg-subtle px-6 py-12 text-center hover:border-ink" data-action="pick-erp">
            <span class="grid h-12 w-12 place-items-center rounded-card bg-white text-ink"><svg viewBox="0 0 24 24" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 16V4m0 0 4 4m-4-4L8 8M5 14v5h14v-5"/></svg></span>
            <span class="mt-4 font-bold text-ink">zrfm2 Excel(xlsx) 선택</span>
            <span class="mt-1 text-sm text-ink">업로드 즉시 DB로 흡수 · 원본 미보관</span></button>
          <input id="erpFile" class="hidden" type="file" accept=".xlsx">
          <div class="mt-6 flex items-center justify-between rounded-control bg-subtle p-4">
            <div><p class="font-semibold text-ink">자동 매칭 분석 (${esc(state.year)}년)</p><p class="text-xs text-sub">손익·자본을 한 번에 실행합니다 (약 1분) · 학습 DB 자동 적용</p></div>
            <button class="btn-primary" data-action="analyze">분석 실행</button>
          </div>
        </article>
        <article class="panel p-6"><h3 class="section-title">이 연도의 ERP 데이터셋</h3>
          ${ds.length ? `<ul class="mt-5 space-y-3 text-sm">${ds.map((d, i) => `<li class="flex items-center justify-between rounded-control ${i === 0 ?"border border-ok bg-ok-bg" : "bg-subtle"} p-3"><div><p class="font-semibold text-ink">${esc(d.label)}</p><p class="text-xs text-sub">${d.row_count.toLocaleString()}행 · ${esc(d.uploaded_at)}</p></div>${i === 0 ? '<span class="badge bg-ok-bg text-ok">사용중</span>' : '<span class="badge bg-subtle text-sub">이전본</span>'}</li>`).join("")}</ul>` : `<p class="mt-5 text-sm text-sub">${esc(state.year)}년 ERP 자료가 아직 없습니다.</p>`}
        </article>
      </section>
      <section class="grid gap-4 md:grid-cols-3">${sums}
        <article class="metric-card"><p class="text-sm font-semibold text-sub">다음 단계</p>
        <p class="mt-3 text-sm text-sub">매칭 결과를 지사별로 검토하고 잘못 붙은 전표를 재배정하세요.</p>
        <button class="btn-secondary mt-4" data-view="detail">실적분석(상세) →</button></article>
      </section>
    </div>`;
}

// ───────────────────────── 3 실적 분석 (전지사) ─────────────────────────
// 검색어 입력 시에는 결과 영역(#brResults)만 갱신 — 입력창을 다시 만들지
// 않아 한글 조합(IME)이 끊기지 않는다.
