import { tourButton } from "../components/tour.js"
import { lockedSay } from "../components/characters.js"
import { fileList, nextStep, slimDrop, stepGuide } from "../components/stage.js"
import { state } from "../state.js"
import { esc } from "../util.js"

// 1단계 화면(2026-11-03 grace «처음 보면 뭘 하라는지 모르겠다»): 위에 세 단계 안내(지금 할 단계가 반짝),
// 파일이 없으면 캐릭터가 업로드 칸을 가리키고, 처음 온 사람에게는 사용법 둘러보기(components/tour.js).
// 화면 안 연도 고르기 칸은 맨 위 줄과 같은 기능이라 뺐다. 조각은 components/stage.js(2단계와 같이 쓴다).
// 두 칸 grid 는 minmax(0,…): 그냥 1fr 이면 오른쪽 긴 파일 이름(여러 파일 합친 2023년 등)이 칸 최소 폭을 밀어
// 왼쪽 업로드 칸이 좁아지고 글자가 한 글자씩 세로로 쪼개졌다(2026-11-04 grace 캡처).
export function renderBudget() {
  const ds = (state.status?.datasets || []).filter(d => d.kind === "plan" && String(d.year) === String(state.year));
  const locked = !!state.status?.locked;
  return `
    <div class="space-y-5">
      <section class="flex flex-wrap items-end justify-between gap-3"><div><p class="text-sm font-semibold text-ink">STAGE 1</p><h2 class="mt-1 font-hanan text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">예산 계획 등록</h2></div>
        ${tourButton("budget")}</section>
      ${locked ? lockedSay("업로드가 차단됩니다.") : ""}
      ${stepGuide(["계획 엑셀 올리기", "올라간 파일 확인", "다음 단계로"], ds.length ? 3 : 1, "예산 계획 단계")}
      <section class="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,.85fr)]">
        <article class="panel p-5"><h3 class="section-title">① 계획 엑셀 올리기 <span class="text-base font-semibold text-sub">· ${esc(state.year)}년</span></h3>
          ${slimDrop({action: "pick-plan", drop: "plan", title: "계획 엑셀 선택 또는 끌어다 놓기",
                      sub: "손익·자본·건설공사 파일을 함께 고르면 한 계획으로 합쳐져요 (.xlsx)", locked, empty: !ds.length, hint: "여기를 눌러 계획 엑셀을 올려요"})}
          <input id="planFile" class="hidden" type="file" accept=".xlsx" multiple>
        </article>
        <article class="panel p-5 plan-files"><h3 class="section-title">② 올라간 계획 파일</h3>
          <div class="mt-4">${fileList(ds, {emptyText: `${esc(state.year)}년 계획 파일이 아직 없어요. 왼쪽에서 올리면 여기에 보여요.`, showAmount: true})}</div>
        </article>
      </section>
      ${nextStep({view: "collect", label: "실적 집계로", ready: ds.length > 0,
                  desc: ds.length ? "계획이 올라갔어요. 이제 ERP 전표(zrfm2)를 올려 실적을 모아요." : "계획 엑셀을 먼저 올린 뒤 넘어가요."})}
    </div>`;
}

// ───────────────────────── 2 실적 집계 ─────────────────────────
