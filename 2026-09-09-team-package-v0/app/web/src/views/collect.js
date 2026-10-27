import { charSay, lockedSay } from "../components/characters.js"
import { yearPicker } from "../components/widgets.js"
import { state } from "../state.js"
import { esc, fmt } from "../util.js"

const ALERT_KINDS = ["급증", "예산 초과", "과다 귀속", "음수 실적", "미매칭 비중"];

/** 이상 알림 — 목록은 검토 큐로 모았다(2026-10-27 사용자 결정: 같은 내용이 두 곳에 있었다).
 *  여기는 종류별 건수만 두고, 누르면 그 이유로 거른 검토 큐로 간다. 검토 큐에 없는 «미매칭 비중»(예산·지사 단위)만
 *  이 자리에 그대로 적는다. */
const ALERT_TO_REASON = {"과다 귀속": "overload", "음수 실적": "negative"};

export function alertsPanelHtml() {
  const data = state.alerts;
  if (!data) return "";
  const sm = data.summary || {total: 0, high: 0, counts: {}};
  const unmatched = (data.alerts || []).filter(a => a.kind === "미매칭 비중");
  const where = a => [a.budget, a.branch].filter(Boolean).map(esc).join(" · ");
  const chip = k => `<button class="badge bg-subtle text-ink hover:bg-ink hover:text-white" data-goto-review data-reason="${ALERT_TO_REASON[k] || ""}" title="검토 큐에서 보기">${esc(k)} ${sm.counts?.[k] || 0}</button>`;
  return `
      <section class="panel p-6" aria-labelledby="alertsTitle">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h3 id="alertsTitle" class="section-title">이상 알림 — ${esc(state.year)}년</h3>
          <div class="flex flex-wrap items-center gap-3">
            <p class="text-sm text-sub">전체 <b class="text-ink">${sm.total}</b>건 · 높음 <b class="text-err">${sm.high}</b>건</p>
            ${sm.total ? '<button class="btn-primary" data-goto-review data-reason="">검토 큐에서 처리 →</button>' : ""}
          </div>
        </div>
        ${sm.total ? `<div class="mt-4 flex flex-wrap gap-2">${ALERT_KINDS.map(chip).join("")}</div>
        ${unmatched.length ? `<ul class="mt-4 divide-y divide-line-subtle border-t border-line">${unmatched.map(a => `
          <li class="flex flex-wrap items-start gap-x-3 gap-y-1 py-3 text-sm">
            <span class="badge ${a.severity === "높음" ? "bg-err-bg text-err" : "bg-warn-bg text-warn"}">${esc(a.severity)}</span>
            <span class="badge bg-subtle text-ink">미매칭 비중</span>
            <span class="min-w-0 flex-1"><span class="font-semibold text-ink">${where(a)}</span><span class="block text-xs text-sub">${esc(a.text)}</span></span>
            ${a.branch && a.branch !== "(미매핑)" ? `<button class="text-xs font-semibold text-ink hover:text-brand" data-branch="${esc(a.branch)}">상세 →</button>` : ""}
          </li>`).join("")}</ul>` : ""}`
        : `<p class="mt-4 text-sm text-sub">${!Object.keys(state.status?.runs || {}).length ? "분석 결과가 생기면 여기에 알림이 나옵니다." : "규칙에 걸린 항목이 없어요."}</p>`}
      </section>`;
}

/** 매칭이 한마디 — 업로드 전 / 분석 전 / 분석 끝 세 단계. 숫자는 runs 요약(손익+자본) 그대로. */
function matchingSay(ds, runs) {
  const done = ["손익", "자본"].map(b => runs[b]?.summary).filter(Boolean);
  if (done.length) {
    const sum = k => done.reduce((a, s) => a + (Number(s[k]) || 0), 0);
    return charSay({who: "mt", title: "분석 끝! 전표마다 맞는 사업을 찾아 붙였어요.",
      body: `계획집행 ${fmt(sum("계획집행 행수"))}행 · 신규 ${fmt(sum("신규 행수"))}행 · 학습확정 ${fmt(sum("학습확정 전표수"))}건. 확신도가 낮은 건 실적분석(상세)에서 검토미와 같이 봐요.`,
      action: `<button class="btn-secondary" data-view="detail">확인하러 가기 →</button>`});
  }
  if (ds.length) {
    return charSay({who: "mt", title: "zrfm2가 올라왔어요.",
      body: "«분석 실행»을 누르면 전표 글자·금액·지사·과목을 보고 맞는 사업을 찾아요."});
  }
  return charSay({who: "mt", title: "전표를 기다리고 있어요.",
    body: `${esc(state.year)}년 zrfm2 를 올리고 «분석 실행»을 누르면 제가 전표마다 맞는 사업을 찾아요.`});
}

export function renderCollect() {
  const ds = (state.status?.datasets || []).filter(d => d.kind === "erp" && String(d.year) === String(state.year));
  const runs = state.status?.runs || {};
  const locked = !!state.status?.locked;
  const lockAttr = locked ? 'disabled aria-disabled="true" title="마감된 연도 — 설정 탭에서 해제 후 사용"' : "";
  const sums = ["손익", "자본"].map(b => {
    const s = runs[b]?.summary;
    if (!s) return `<article class="metric-card"><p class="text-sm font-semibold text-sub">${b} 매칭</p><p class="mt-3 text-sm text-sub">미실행</p></article>`;
    return `<article class="metric-card"><p class="text-sm font-semibold text-sub">${b} 매칭 결과</p>
      <p class="mt-3 text-3xl font-bold">${fmt(s["총 실적(천원)"])}<span class="ml-1 text-sm font-semibold text-tri">천원</span></p>
      <p class="mt-2 text-sm text-sub">계획집행 ${fmt(s["계획집행 행수"])}행 · 신규 ${fmt(s["신규 행수"])}행 · 학습확정 ${fmt(s["학습확정 전표수"] ?? 0)}건</p></article>`;
  }).join("");
  return `
    <div class="space-y-6">
      <section><p class="text-sm font-semibold text-ink">STAGE 2</p><h2 class="mt-1 font-hanan text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">실적 집계와 사업 매칭</h2></section>
      ${locked ? lockedSay("업로드·분석이 차단됩니다.") : matchingSay(ds, runs)}
      <section class="panel p-5">${yearPicker("cp")}</section>
      <section class="grid gap-6 xl:grid-cols-[1fr_.75fr]">
        <article class="panel p-6"><h3 class="section-title">ERP(zrfm2) 업로드 — <span class="text-ink">${esc(state.year)}년</span>으로 등록</h3>
          <button class="drop-zone flex w-full flex-col items-center justify-center px-6 text-center ${locked ? "cursor-not-allowed opacity-50" : "hover:border-ink"}" data-action="pick-erp" ${lockAttr}>
            <span class="grid h-12 w-12 place-items-center rounded-card bg-white text-ink"><svg viewBox="0 0 24 24" class="h-6 w-6" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 16V4m0 0 4 4m-4-4L8 8M5 14v5h14v-5"/></svg></span>
            <span class="mt-4 font-bold text-ink">zrfm2 Excel(xlsx) 선택</span>
            <span class="mt-1 text-sm text-ink">업로드 즉시 DB로 흡수 · 원본 미보관</span></button>
          <input id="erpFile" class="hidden" type="file" accept=".xlsx">
          <div class="mt-6 flex items-center justify-between rounded-control bg-subtle p-4">
            <div><p class="font-semibold text-ink">자동 매칭 분석 (${esc(state.year)}년)</p><p class="text-xs text-sub">손익·자본을 한 번에 실행합니다 (약 1분) · 학습 DB 자동 적용</p></div>
            <button class="btn-primary disabled:cursor-not-allowed disabled:opacity-40" data-action="analyze" ${lockAttr}>분석 실행</button>
          </div>
        </article>
        <article class="panel p-6"><h3 class="section-title">이 연도의 ERP 데이터셋</h3>
          <div class="dataset-box">${ds.length ? `<ul class="space-y-2 text-sm">${ds.map((d, i) => `<li class="flex items-center justify-between gap-3 rounded-control ${i === 0 ?"border border-ok bg-ok-bg" : "bg-base"} p-3"><div><p class="font-semibold text-ink">${esc(d.label)}</p><p class="text-xs text-sub">${d.row_count.toLocaleString()}행 · ${esc(d.uploaded_at)}</p></div>${i === 0 ? '<span class="badge bg-ok-bg text-ok">사용중</span>' : '<span class="badge bg-subtle text-sub">이전본</span>'}</li>`).join("")}</ul>` : `<p class="grid h-full place-items-center text-sm text-sub">${esc(state.year)}년 ERP 자료가 아직 없습니다.</p>`}</div>
        </article>
      </section>
      ${alertsPanelHtml()}
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
