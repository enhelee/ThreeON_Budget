import { tourButton } from "../components/tour.js"
import { charSay, lockedSay } from "../components/characters.js"
import { fileList, nextStep, slimDrop, stepGuide } from "../components/stage.js"
import { state } from "../state.js"
import { esc, fmt } from "../util.js"

const ALERT_KINDS = ["급증", "예산 초과", "과다 귀속", "음수 실적", "미매칭 비중"];

/** 이상 알림 — 목록은 검토 대기로 모았다(2026-10-27 사용자 결정: 같은 내용이 두 곳에 있었다).
 *  여기는 종류별 건수만 두고, 누르면 그 이유로 거른 검토 대기로 간다. 검토 대기에 없는 «미매칭 비중»(예산·지사 단위)만
 *  이 자리에 그대로 적는다. */
const ALERT_TO_REASON = {"과다 귀속": "overload", "음수 실적": "negative"};

export function alertsPanelHtml() {
  const data = state.alerts;
  if (!data) return "";
  const sm = data.summary || {total: 0, high: 0, counts: {}};
  const unmatched = (data.alerts || []).filter(a => a.kind === "미매칭 비중");
  const where = a => [a.budget, a.branch].filter(Boolean).map(esc).join(" · ");
  const chip = k => `<button class="badge bg-subtle text-ink hover:bg-ink hover:text-white" data-goto-review data-reason="${ALERT_TO_REASON[k] || ""}" title="검토 대기에서 보기">${esc(k)} ${sm.counts?.[k] || 0}</button>`;
  return `
      <section class="panel p-6" aria-labelledby="alertsTitle">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h3 id="alertsTitle" class="section-title">이상 알림 — ${esc(state.year)}년</h3>
          <div class="flex flex-wrap items-center gap-3">
            <p class="text-sm text-sub">전체 <b class="text-ink">${sm.total}</b>건 · 높음 <b class="text-err">${sm.high}</b>건</p>
            ${sm.total ? '<button class="btn-primary" data-goto-review data-reason="">검토 대기에서 처리 →</button>' : ""}
          </div>
        </div>
        ${sm.total ? `<div class="mt-4 flex flex-wrap gap-2">${ALERT_KINDS.map(chip).join("")}</div>
        ${unmatched.length ? `<ul class="mt-4 divide-y divide-line-subtle border-t border-line">${unmatched.map(a => `
          <li class="flex flex-wrap items-start gap-x-3 gap-y-1 py-3 text-sm">
            <span class="badge ${a.severity === "높음" ? "bg-err-bg text-err" : "bg-warn-bg text-warn"}">${esc(a.severity)}</span>
            <span class="badge bg-subtle text-ink">미매칭 비중</span>
            <span class="min-w-0 flex-1"><span class="font-semibold text-ink">${where(a)}</span><span class="block text-xs text-sub">${esc(a.text)}</span></span>
            ${a.branch && a.branch !== "(미매핑)" ? `<button class="text-xs font-semibold text-ink hover:text-mint-ink" data-branch="${esc(a.branch)}">상세 →</button>` : ""}
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
      body: `계획집행 ${fmt(sum("계획집행 행수"))}행 · 신규 ${fmt(sum("신규 행수"))}행 · 학습확정 ${fmt(sum("학습확정 전표수"))}건. 확신도가 낮은 건 지사 상세에서 검토미와 같이 봐요.`,
      action: `<button class="btn-secondary" data-view="detail">확인하러 가기 →</button>`});
  }
  if (ds.length) {
    return charSay({who: "mt", title: "zrfm2가 올라왔어요.",
      body: "«분석 실행»을 누르면 전표 글자·금액·지사·과목을 보고 맞는 사업을 찾아요."});
  }
  return charSay({who: "mt", title: "전표를 기다리고 있어요.",
    body: `${esc(state.year)}년 zrfm2 를 올리고 «분석 실행»을 누르면 제가 전표마다 맞는 사업을 찾아요.`});
}

// 2단계 화면(2026-11-03 grace): 1단계와 같은 모양 — 세 단계 안내 · 얇은 업로드 칸 · 올라간 파일(원본 내려받기) ·
// 눈에 띄는 매칭 결과(억원) · 따로 떨어진 큰 «다음 단계» 버튼 · 길어지는 이상 알림은 맨 아래. 화면 안 연도 칸은 뺐다.
const eok = v => { const x = (Number(v) || 0) / 1e5; return Math.abs(x) >= 100 ? fmt(Math.round(x)) : x.toFixed(1) }

export function renderCollect() {
  const ds = (state.status?.datasets || []).filter(d => d.kind === "erp" && String(d.year) === String(state.year));
  const runs = state.status?.runs || {};
  const locked = !!state.status?.locked;
  const lockAttr = locked ? 'disabled aria-disabled="true" title="마감된 연도 — 설정에서 해제 후 사용"' : "";
  const analyzed = ["손익", "자본"].some(b => runs[b]?.summary);
  const now = analyzed ? 3 : ds.length ? 2 : 1;
  const sums = ["손익", "자본"].map(b => {
    const s = runs[b]?.summary, key = b === "손익" ? "pl" : "cap";
    if (!s) return `<article class="match-card match-card--${key}"><p class="match-card__k">${b} 매칭 결과</p><p class="match-card__v text-tri">아직 분석 전</p></article>`;
    return `<article class="match-card match-card--${key}"><p class="match-card__k">${b} 매칭 결과</p>
      <p class="match-card__v">${eok(s["총 실적(천원)"])}<span class="match-card__u">억원</span></p>
      <p class="match-card__sub" title="${fmt(s["총 실적(천원)"])} 천원">계획집행 ${fmt(s["계획집행 행수"])}행 · 신규 ${fmt(s["신규 행수"])}행 · 학습확정 ${fmt(s["학습확정 전표수"] ?? 0)}건</p></article>`;
  }).join("");
  return `
    <div class="space-y-5">
      <section class="flex flex-wrap items-end justify-between gap-3"><div><p class="text-sm font-semibold text-ink">STAGE 2</p><h2 class="mt-1 font-hanan text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">실적 집계와 사업 매칭</h2></div>
        ${tourButton("collect")}</section>
      ${locked ? lockedSay("업로드·분석이 차단됩니다.") : matchingSay(ds, runs)}
      ${stepGuide(["ERP 전표(zrfm2) 올리기", "자동 매칭 분석 실행", "매칭 결과 확인"], now, "실적 집계 단계")}
      <section class="grid gap-5 xl:grid-cols-[1fr_.85fr]">
        <article class="panel p-5"><h3 class="section-title">① ERP 전표 올리기 <span class="text-base font-semibold text-sub">· ${esc(state.year)}년</span></h3>
          ${slimDrop({action: "pick-erp", drop: "erp", title: "zrfm2 엑셀 선택 또는 끌어다 놓기",
                      sub: "SAP 에서 내려받은 zrfm2 파일 하나 (.xlsx)", locked, empty: !ds.length, hint: "여기를 눌러 zrfm2 엑셀을 올려요"})}
          <input id="erpFile" class="hidden" type="file" accept=".xlsx">
          <div class="analyze-box ${now === 2 ? "is-now" : ""}">
            <div><p class="font-semibold text-ink">② 자동 매칭 분석 (${esc(state.year)}년)</p><p class="text-xs text-sub">손익·자본을 한 번에 실행해요 (약 1분) · 학습 DB 자동 적용</p></div>
            <button class="btn-primary disabled:cursor-not-allowed disabled:opacity-40" data-action="analyze" ${lockAttr}>분석 실행</button>
          </div>
        </article>
        <article class="panel p-5 plan-files"><h3 class="section-title">올라간 전표 파일</h3>
          <div class="mt-4">${fileList(ds, {emptyText: `${esc(state.year)}년 전표 파일이 아직 없어요. 왼쪽에서 올리면 여기에 보여요.`, showAmount: false})}</div>
        </article>
      </section>
      <section class="match-results"><h3 class="section-title">③ 매칭 결과</h3><div class="mt-4 grid gap-4 md:grid-cols-2">${sums}</div></section>
      ${nextStep({view: "detail", label: "지사 상세로", ready: analyzed,
                  desc: analyzed ? "매칭 결과를 지사별로 검토하고 잘못 붙은 전표를 재배정해요." : "분석을 실행하면 결과를 확인하러 넘어갈 수 있어요."})}
      ${alertsPanelHtml()}
    </div>`;
}

// ───────────────────────── 3 실적 분석 (전지사) ─────────────────────────
// 검색어 입력 시에는 결과 영역(#brResults)만 갱신 — 입력창을 다시 만들지
// 않아 한글 조합(IME)이 끊기지 않는다.
