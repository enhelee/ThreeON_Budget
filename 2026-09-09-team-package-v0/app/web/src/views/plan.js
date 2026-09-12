import { yearPicker } from "../components/widgets.js"
import { state } from "../state.js"
import { esc, fmt } from "../util.js"

export function renderBudget() {
  const ds = (state.status?.datasets || []).filter(d => d.kind === "plan" && String(d.year) === String(state.year));
  return `
    <div class="space-y-6">
      <section><p class="text-sm font-semibold text-blue-700">STAGE 1</p><h2 class="mt-1 text-2xl font-bold tracking-tight text-slate-950">예산 계획 등록</h2>
      <p class="mt-2 text-sm text-slate-500">사업별 예산(양식1(월별)) 파일을 업로드하면 행 단위로 백엔드 DB에 흡수됩니다. 원본 파일은 서버에 남지 않습니다.</p></section>
      ${state.status?.locked ? `<section class="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-semibold text-amber-900">🔒 ${esc(state.year)}년은 마감(잠금) 상태 — 업로드가 차단됩니다.</section>` : ""}
      <section class="panel p-5">${yearPicker("bp")}</section>
      <section class="grid gap-6 xl:grid-cols-[1fr_.75fr]">
        <article class="panel p-6"><h3 class="section-title">계획본 업로드 — <span class="text-blue-700">${esc(state.year)}년</span>으로 등록</h3>
          <p class="section-help">헤더 3행 · 데이터 4행부터 — 주관부서명, 부서코드, 처지사, 부서(부), 속성, 예산코드, 예산과목, 사업명, 산출내역, 연예산</p>
          <button class="mt-6 grid w-full place-items-center rounded-2xl border-2 border-dashed border-blue-200 bg-blue-50 px-6 py-12 text-center hover:border-blue-400" data-action="pick-plan">
            <span class="grid h-12 w-12 place-items-center rounded-2xl bg-white text-blue-700 shadow-sm"><svg viewBox="0 0 24 24" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 16V4m0 0 4 4m-4-4L8 8M5 14v5h14v-5"/></svg></span>
            <span class="mt-4 font-bold text-blue-950">계획 Excel(xlsx) 선택</span>
            <span class="mt-1 text-sm text-blue-700">업로드 즉시 DB로 흡수됩니다</span></button>
          <input id="planFile" class="hidden" type="file" accept=".xlsx">
        </article>
        <article class="panel p-6"><h3 class="section-title">이 연도의 계획 데이터셋</h3>
          ${ds.length ? `<ul class="mt-5 space-y-3 text-sm">${ds.map((d, i) => `<li class="flex items-center justify-between rounded-xl ${i === 0 ? "border border-blue-200 bg-blue-50" : "bg-slate-50"} p-3"><div><p class="font-semibold text-slate-800">${esc(d.label)}</p><p class="text-xs text-slate-500">${d.row_count.toLocaleString()}행 · ${fmt(d.total_amount)}천원 · ${esc(d.uploaded_at)}</p></div>${i === 0 ? '<span class="badge bg-blue-100 text-blue-700">사용중</span>' : '<span class="badge bg-slate-100 text-slate-500">이전본</span>'}</li>`).join("")}</ul>` : `<p class="mt-5 text-sm text-slate-500">${esc(state.year)}년 계획이 아직 없습니다.</p>`}
          <p class="mt-4 text-xs text-slate-400">같은 연도에 여러 번 올리면 <b>가장 최근 업로드</b>가 사용됩니다.</p>
        </article>
      </section>
    </div>`;
}

// ───────────────────────── 2 실적 집계 ─────────────────────────
