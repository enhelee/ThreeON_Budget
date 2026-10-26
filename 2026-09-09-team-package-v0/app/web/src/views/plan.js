import { lockedSay } from "../components/characters.js"
import { yearPicker } from "../components/widgets.js"
import { state } from "../state.js"
import { esc, fmt } from "../util.js"

/** 올린 계획 합계 = 분석 대상 + 분석 제외 과목. 제외가 없으면 아무것도 그리지 않는다. */
function planScopeHtml() {
  const sc = state.status?.plan_scope
  const ex = Object.entries(sc?.excluded || {})
  if (!ex.length) return ""
  const exSum = ex.reduce((a, [, v]) => a + v, 0)
  return `<p class="mt-3 text-xs text-sub">분석 대상 <b class="text-ink">${fmt(sc.total - exSum)}</b>천원 · 분석 제외 ${fmt(exSum)}천원
    (${ex.map(([k, v]) => `${esc(k)} ${fmt(v)}`).join(" · ")}) — 제외 과목은 설정 › 기준정보에서 고릅니다.</p>`
}

export function renderBudget() {
  const ds = (state.status?.datasets || []).filter(d => d.kind === "plan" && String(d.year) === String(state.year));
  const locked = !!state.status?.locked;
  return `
    <div class="space-y-6">
      <section><p class="text-sm font-semibold text-ink">STAGE 1</p><h2 class="mt-1 font-hanan text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">예산 계획 등록</h2></section>
      ${locked ? lockedSay("업로드가 차단됩니다.") : ""}
      <section class="panel p-5">${yearPicker("bp")}</section>
      <section class="grid gap-6 xl:grid-cols-[1fr_.75fr]">
        <article class="panel p-6"><h3 class="section-title">계획본 업로드 — <span class="text-ink">${esc(state.year)}년</span>으로 등록</h3>
          <button class="drop-zone flex w-full flex-col items-center justify-center px-6 text-center ${locked ? "cursor-not-allowed opacity-50" : "hover:border-ink"}" data-action="pick-plan" ${locked ? 'disabled aria-disabled="true" title="마감된 연도 — 설정 탭에서 해제 후 업로드"' : ""}>
            <span class="grid h-12 w-12 place-items-center rounded-card bg-white text-ink"><svg viewBox="0 0 24 24" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 16V4m0 0 4 4m-4-4L8 8M5 14v5h14v-5"/></svg></span>
            <span class="mt-4 font-bold text-ink">계획 Excel(xlsx) 선택 — 여러 개 가능</span>
            <span class="mt-1 text-sm text-ink">손익·자본·건설공사를 함께 고르면 한 계획으로 합쳐 흡수됩니다</span></button>
          <input id="planFile" class="hidden" type="file" accept=".xlsx" multiple>
        </article>
        <article class="panel p-6"><h3 class="section-title">이 연도의 계획 데이터셋</h3>
          <div class="dataset-box">${ds.length ? `<ul class="space-y-2 text-sm">${ds.map((d, i) => `<li class="flex items-center justify-between gap-3 rounded-control ${i === 0 ?"border border-line-strong bg-base" : "bg-base"} p-3"><div><p class="font-semibold text-ink">${esc(d.label)}</p><p class="text-xs text-sub">${d.row_count.toLocaleString()}행 · ${fmt(d.total_amount)}천원 · ${esc(d.uploaded_at)}</p></div>${i === 0 ? '<span class="badge bg-subtle text-ink">사용중</span>' : '<span class="badge bg-subtle text-sub">이전본</span>'}</li>`).join("")}</ul>` : `<p class="grid h-full place-items-center text-sm text-sub">${esc(state.year)}년 계획이 아직 없습니다.</p>`}</div>
          ${planScopeHtml()}
          <p class="mt-3 text-xs text-tri">가장 최근 업로드가 사용됩니다 — 나눠진 파일은 한 번에 고르세요.</p>
        </article>
      </section>
    </div>`;
}

// ───────────────────────── 2 실적 집계 ─────────────────────────
