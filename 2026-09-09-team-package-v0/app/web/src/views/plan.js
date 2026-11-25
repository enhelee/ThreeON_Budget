import { tourButton } from "../components/tour.js"
import { lockedSay } from "../components/characters.js"
import { fileList, nextStep, slimDrop, stepGuide } from "../components/stage.js"
import { state } from "../state.js"
import { esc, fmt } from "../util.js"

// 1단계 화면(2026-11-03 grace «처음 보면 뭘 하라는지 모르겠다»): 위에 세 단계 안내(지금 할 단계가 반짝),
// 파일이 없으면 캐릭터가 업로드 칸을 가리키고, 처음 온 사람에게는 사용법 둘러보기(components/tour.js).
// 화면 안 연도 고르기 칸은 맨 위 줄과 같은 기능이라 뺐다. 조각은 components/stage.js(2단계와 같이 쓴다).
// 두 칸 grid 는 minmax(0,…): 그냥 1fr 이면 오른쪽 긴 파일 이름(여러 파일 합친 2023년 등)이 칸 최소 폭을 밀어
// 왼쪽 업로드 칸이 좁아지고 글자가 한 글자씩 세로로 쪼개졌다(2026-11-04 grace 캡처).
// 계획 올리기는 두 갈래(2026-11-25 팀장): 주관부서가 합친 «취합 계획»을 그대로 올리거나,
// 처·지사가 낸 파일을 «부서별 계획»으로 올려 앱이 합친다(budget/dept_plan.py). 부서별 탭은 안 낸 부서를 보여 준다.
export function renderBudget() {
  const ds = (state.status?.datasets || []).filter(d => d.kind === "plan" && String(d.year) === String(state.year));
  const locked = !!state.status?.locked;
  const tab = state.planTab === "dept" ? "dept" : "merged";
  const pd = state.planDepts && String(state.planDepts.year) === String(state.year) ? state.planDepts : null;
  const guide = tab === "dept"
    ? stepGuide(["부서별 계획 올리기", "미제출 부서 확인", "다음 단계로"], !pd?.files ? 1 : pd.missing.length ? 2 : 3, "부서별 계획 단계")
    : stepGuide(["취합 계획 올리기", "올라간 파일 확인", "다음 단계로"], ds.length ? 3 : 1, "예산 계획 단계");
  return `
    <div class="space-y-5">
      <section class="flex flex-wrap items-end justify-between gap-3"><div><p class="text-sm font-semibold text-ink">STAGE 1</p><h2 class="mt-1 font-hanan text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">예산 계획 등록</h2></div>
        ${tourButton("budget")}</section>
      ${locked ? lockedSay("업로드가 차단됩니다.") : ""}
      <div class="flex flex-wrap gap-2" role="tablist" aria-label="계획 올리는 방법">
        ${[["merged", "취합 계획 올리기"], ["dept", "부서별 계획 올리기"]].map(([k, l]) =>
          `<button class="${tab === k ? "btn-primary" : "btn-secondary"}" role="tab" aria-selected="${tab === k}" data-plantab="${k}">${l}</button>`).join("")}
      </div>
      ${guide}
      ${tab === "dept" ? deptPanels(pd, locked) : `
      <section class="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,.85fr)]">
        <article class="panel p-5"><h3 class="section-title">① 취합 계획 올리기 <span class="text-base font-semibold text-sub">· ${esc(state.year)}년</span></h3>
          ${slimDrop({action: "pick-plan", drop: "plan", title: "취합 계획 엑셀 선택 또는 끌어다 놓기",
                      sub: "손익·자본·건설공사 파일을 함께 고르면 한 계획으로 합쳐져요 (.xlsx)", locked, empty: !ds.length, hint: "여기를 눌러 취합 계획 엑셀을 올려요"})}
          <input id="planFile" class="hidden" type="file" accept=".xlsx" multiple>
          <p class="mt-3 text-xs text-sub">지사별로 따로 받은 파일이면 위 <b>부서별 계획 올리기</b>에서 올리세요 — 앱이 합쳐 줘요.</p>
        </article>
        <article class="panel p-5 plan-files"><h3 class="section-title">② 올라간 계획 파일</h3>
          <div class="mt-4">${fileList(ds, {emptyText: `${esc(state.year)}년 계획 파일이 아직 없어요. 왼쪽에서 올리면 여기에 보여요.`, showAmount: true})}</div>
        </article>
      </section>`}
      ${nextStep({view: "collect", label: "실적 집계로", ready: ds.length > 0,
                  desc: ds.length ? "계획이 올라갔어요. 이제 ERP 전표(zrfm2)를 올려 실적을 모아요." : "계획 엑셀을 먼저 올린 뒤 넘어가요."})}
    </div>`;
}

function deptPanels(pd, locked) {
  const drop = `${slimDrop({action: "pick-plan-dept", drop: "plan-dept", title: "부서 계획 엑셀 선택 또는 끌어다 놓기",
                  sub: "여러 부서 파일을 한 번에 골라도 돼요. 파일 안 처·지사 이름으로 부서를 알아내 자동으로 합쳐요 (.xlsx)",
                  locked, empty: !pd?.files, hint: "지사에서 받은 계획 엑셀을 여기에 올려요"})}
          <input id="planDeptFile" class="hidden" type="file" accept=".xlsx" multiple>`;
  if (!pd) return `<section class="panel p-5"><h3 class="section-title">① 부서별 계획 올리기</h3>${drop}
      <p class="mt-4 rounded-control bg-subtle p-4 text-sm text-sub">부서별 제출 현황을 불러오는 중이에요…</p></section>`;
  const pct = pd.expected ? Math.round(pd.submitted / pd.expected * 100) : 0;
  const groups = [...new Set(pd.depts.map(d => d.그룹))];
  const fileRow = (d, f) => `<li class="flex items-center justify-between gap-2 text-xs">
      <span class="min-w-0 truncate text-ink" title="${esc(f.filename)}">${esc(f.filename)}</span>
      <span class="flex shrink-0 items-center gap-2 text-sub">${f.row_count.toLocaleString()}행 · ${fmt(f.total_amount)} 천원 · ${esc(String(f.uploaded_at).slice(5, 16))}
        ${locked ? "" : `<button type="button" class="rounded-control border border-line px-2 py-0.5 font-semibold text-sub hover:bg-warn-bg hover:text-warn" data-action="del-plan-dept" data-id="${f.id}" data-dept="${esc(d.부서)}" data-name="${esc(f.filename)}" title="이 파일 빼기">빼기</button>`}</span></li>`;
  const row = d => `<tr class="${d.제출 ? "" : "bg-warn-bg/40"}">
      <td class="table-cell whitespace-nowrap font-semibold text-ink">${esc(d.부서)}</td>
      <td class="table-cell whitespace-nowrap">${d.제출 ? '<span class="badge bg-ok-bg text-ok">✓ 제출</span>' : '<span class="badge bg-warn-bg text-warn">미제출</span>'}</td>
      <td class="table-cell">${d.files.length ? `<ul class="space-y-1">${d.files.map(f => fileRow(d, f)).join("")}</ul>`
        : d.다른파일 ? '<span class="text-xs text-sub">다른 부서 파일 안에 함께 들어 있어요</span>' : '<span class="text-xs text-tri">—</span>'}</td></tr>`;
  return `
      <section class="grid gap-5 xl:grid-cols-[minmax(0,.8fr)_minmax(0,1.2fr)]">
        <article class="panel p-5"><h3 class="section-title">① 부서별 계획 올리기 <span class="text-base font-semibold text-sub">· ${esc(state.year)}년</span></h3>
          ${drop}
          <div class="mt-5 rounded-control border border-line-subtle p-4">
            <div class="flex items-baseline justify-between"><p class="text-sm font-semibold text-ink">제출 현황</p>
              <p class="text-sm"><b class="text-lg text-ink">${pd.submitted}</b><span class="text-sub"> / ${pd.expected}개 부서</span></p></div>
            <div class="mt-2 h-2 overflow-hidden rounded-full bg-subtle"><div class="h-full rounded-full bg-ok" style="width:${pct}%"></div></div>
            ${pd.missing.length ? `<p class="mt-4 text-sm font-semibold text-warn">아직 안 낸 부서 ${pd.missing.length}곳</p>
              <div class="mt-2 flex flex-wrap gap-1.5">${pd.missing.map(n => `<span class="badge bg-warn-bg text-warn">${esc(n)}</span>`).join("")}</div>`
              : `<p class="mt-4 text-sm font-semibold text-ok">모든 부서가 냈어요 — 취합이 끝났어요.</p>`}
          </div>
          <ul class="mt-3 space-y-0.5 text-xs text-sub">
            <li>* 올릴 때마다 그 해 부서 파일 전부를 한 계획으로 다시 합쳐 분석에 써요.</li>
            <li>* 같은 부서가 같은 이름의 파일을 다시 올리면 새 파일로 바꿔요.</li>
            <li>* 부서 목록은 설정의 지사 구성(포함)을 따라요.</li>
          </ul>
          ${pd.files && !pd.current_is_merged ? `<p class="mt-3 rounded-control bg-warn-bg p-3 text-xs text-warn">지금 분석에 쓰는 계획은 따로 올린 취합 계획이에요. 부서 파일을 하나 더 올리면 부서별 취합본으로 바뀌어요.</p>` : ""}
        </article>
        <article class="panel p-5"><h3 class="section-title">② 부서별 제출 현황</h3>
          <div class="mt-4 overflow-x-auto"><table class="w-full text-sm">
            <thead><tr class="text-left text-xs text-sub"><th class="table-cell">부서</th><th class="table-cell">상태</th><th class="table-cell">올린 파일</th></tr></thead>
            ${groups.map(g => `<tbody class="divide-y divide-line-subtle"><tr><td colspan="3" class="bg-subtle px-3 py-1.5 text-xs font-semibold text-sub">${esc(g)}</td></tr>
              ${pd.depts.filter(d => d.그룹 === g).map(row).join("")}</tbody>`).join("")}
          </table></div>
        </article>
      </section>`;
}

// ───────────────────────── 2 실적 집계 ─────────────────────────
