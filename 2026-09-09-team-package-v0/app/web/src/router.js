import { api } from "./api.js"
import { busy, toast } from "./components/feedback.js"
import { loadBranches, loadDetail, loadExportStatus, loadHealth, loadLockStates, loadOverview, loadPending, loadStatus, loadYearConfig } from "./data.js"
import { closeMenu } from "./main.js"
import { state, viewMeta } from "./state.js"
import { $, fmt } from "./util.js"
import { loadErrorBannerHtml } from "./components/loaderror.js"
import { lockBannerHtml } from "./components/lockbanner.js"
import { renderBranches } from "./views/branches.js"
import { renderCollect } from "./views/collect.js"
import { renderDetail } from "./views/detail.js"
import { mountForecast, renderForecast } from "./views/forecast.js"
import { renderHome } from "./views/home.js"
import { renderBudget } from "./views/plan.js"
import { renderSettings } from "./views/settings.js"
import { renderStats } from "./views/stats.js"

// ───────────────────────── 해시 라우팅 ─────────────────────────
// 주소의 «#/...» 조각이 "지금 어느 화면인가"의 단일 근거다.
//
//   화면을 바꾸는 길 → navigate() 하나뿐. navigate() 가 주소를 맞춘다.
//   반대 방향(뒤로가기·새로고침·링크로 들어옴) → hashchange 가 navigate() 를 부른다.
//
// 양방향이 같은 함수로 모이므로 순환이 생길 수 있는데, navigate() 가 state 를
// 먼저 바꾸고 주소를 나중에 맞추기 때문에 hashchange 쪽 비교가 곧바로 no-op 이 된다.
// 플래그를 두지 않는 이유가 이것이다.

const VIEW_HASH = {home: "home", budget: "plan", collect: "collect", branches: "branches",
                   detail: "detail", stats: "stats", forecast: "forecast", settings: "settings"};
const HASH_VIEW = Object.fromEntries(Object.entries(VIEW_HASH).map(([v, h]) => [h, v]));

/** 화면(+지사) → 주소 조각. 3+ 상세는 지사가 곧 화면의 내용이라 주소에 같이 담는다. */
export function viewHash(view, branch) {
  const h = VIEW_HASH[view] || "home";
  return h === "detail" && branch ? `#/detail/${encodeURIComponent(branch)}` : `#/${h}`;
}

/** 주소 조각 → {view, branch}. 모르는 주소면 null. */
export function parseHash(hash = location.hash) {
  const m = /^#\/([^/]+)\/?(.*)$/.exec(hash);
  if (!m) return null;
  const view = HASH_VIEW[m[1]];
  if (!view) return null;
  let branch = "";
  if (view === "detail" && m[2]) {
    try { branch = decodeURIComponent(m[2]); } catch { branch = m[2]; }
  }
  return {view, branch};
}

/** 현재 state 에 맞춰 주소를 갱신한다(화면 전환을 navigate 밖에서 한 경우용). */
export function syncHash(opts = {}) {
  const h = viewHash(state.view, state.det.branch);
  if (location.hash === h) return;
  if (opts.replace) location.replace(location.pathname + location.search + h);
  else location.hash = h;
}

/** 뒤로가기·새로고침·직접 입력으로 주소가 바뀌었을 때. */
export function onHashChange() {
  const t = parseHash();
  if (!t) { syncHash({replace: true}); return; }   // 모르는 주소는 지금 화면으로 되돌린다
  const same = t.view === state.view &&
               (t.view !== "detail" || t.branch === state.det.branch);
  if (same) return;                               // navigate() 가 방금 맞춘 주소 — 할 일 없음
  navigate(t.view, {branch: t.branch});
}

/** 첫 진입: 주소에 화면이 적혀 있으면 그 화면으로, 없으면 홈으로. */
export function bootRoute() {
  const t = parseHash();
  return t ? navigate(t.view, {branch: t.branch}) : navigate("home");
}

export function renderPage() {
  const renderers = {home: renderHome, budget: renderBudget, collect: renderCollect,
                     branches: renderBranches, detail: renderDetail, stats: renderStats,
                     forecast: renderForecast, settings: renderSettings};
  $("#page").innerHTML = renderers[state.view]();
  const lb = $("#lockBanner");
  if (lb) lb.innerHTML = loadErrorBannerHtml() + lockBannerHtml();
  if (state.view === "forecast") mountForecast();   // iframe 성패를 지켜본다
  const [title, subtitle] = viewMeta[state.view];
  $("#pageTitle").textContent = title;
  $("#pageSubtitle").textContent = subtitle;
  document.querySelectorAll("nav [data-view]").forEach(b =>
    b.classList.toggle("nav-button-active", b.dataset.view === state.view));
  const ys = $("#yearSelect");
  const years = state.years.length ? state.years : [state.year];
  ys.innerHTML = years.map(y => `<option value="${y}" ${String(y) === String(state.year) ? "selected" : ""}>${y}년</option>`).join("");
  syncAnalyzeButton();
}

// 화면 하나를 그리려고 API 를 예닐곱 개 부른다. 이것들을 한 try 로 묶으면
// 앞의 하나가 죽는 순간 뒤가 통째로 건너뛰어지고, 화면은 «데이터가 없다»처럼 보인다.
// 실제로 배포 직후 502 한 번에 설정 화면 전체가 빈 것처럼 보여 데이터 소실로 오인됐다
// (2026-09-19). 그래서 구역마다 따로 실패시키고, 실패한 구역을 배너로 밝힌다.
async function settle(jobs) {
  const errs = [];
  for (const [label, fn] of jobs) {
    try { await fn(); } catch (e) { errs.push(`${label}: ${e.message}`); }
  }
  return errs;
}

export async function navigate(view, opts = {}) {
  // 3+ 상세는 주소가 지사까지 담는다. 주소에서 온 호출("branch" 키가 있는 경우)은
  // 그 값이 곧 진실이다 - 지사가 적혀 있으면 불러오고, 비어 있으면 선택을 푼다.
  // 키가 없는 내부 호출(changeYear 등)은 보던 지사를 그대로 둔다.
  if (view === "detail" && "branch" in opts && opts.branch !== state.det.branch) {
    if (opts.branch) {
      try { await loadDetail(opts.branch); }
      catch (e) { toast(e.message); }             // 없어진 지사면 지사 선택 화면이 뜬다
    } else {
      state.det = {...state.det, branch: "", data: null, open: new Set(), sel: new Set(),
                   selBudget: null, editKey: null, delKey: null};
    }
  }
  state.view = view;
  syncHash();
  const jobs = [["연도 목록", loadOverview], ["미반영 건수", loadPending],
                ["마감 상태", loadLockStates]];
  if (view === "home" || view === "branches" || view === "detail") {
    jobs.push(["현황", loadStatus], ["지사 목록", loadBranches]);
  }
  if (view === "home") jobs.push(["서버 정보", loadHealth], ["내보내기 이력", loadExportStatus]);
  if (view === "forecast") jobs.push(["서버 정보", loadHealth]);   // iframe 주소가 여기서 온다
  if (view === "budget" || view === "collect") jobs.push(["현황", loadStatus]);
  if (view === "stats") {
    jobs.push(["통계", async () => { state.stats = await api(`/api/stats?year=${state.year}`); }],
              ["연도 비교", async () => { state.statsCompare = await api(`/api/stats-compare?year=${state.year}`); }]);
  }
  if (view === "settings") {
    jobs.push(
      ["현황", loadStatus],
      ["재배정 이력", async () => { state.overrides = await api(`/api/overrides?year=${state.year}`); }],
      ["학습 현황", async () => { state.learned = await api("/api/learned"); }],
      ["감사 로그", async () => { state.audit = (await api("/api/audit?limit=50")).rows; }],
      ["모델 목록", async () => { state.models = await api("/api/models"); }],
      ["사업 수정 이력", async () => { state.bizEdits = await api(`/api/biz-edits?year=${state.year}`); }],
      ["수동 추가 사업", async () => { state.manualBiz = await api(`/api/manual-biz?year=${state.year}`); }],
      ["사업 삭제 이력", async () => { state.bizDeletes = await api(`/api/biz-deletes?year=${state.year}`); }],
      ["연도 기준정보", loadYearConfig]);
  }
  state.loadErrors = await settle(jobs);
  if (state.loadErrors.length) {
    toast(`${state.loadErrors.length}개 구역을 불러오지 못했습니다 — 화면 위 안내를 보세요.`);
  }
  renderPage();
  closeMenu();
  window.scrollTo({top: 0, behavior: "smooth"});
}

export async function changeYear(y) {
  state.year = String(y);
  state.det = {...state.det, branch: "", data: null, open: new Set(), sel: new Set(), selBudget: null, editKey: null};
  await navigate(state.view);
}

export async function addYearFromInput(inputId) {
  const el = inputId ? document.getElementById(inputId) : null;
  const v = el ? el.value.trim() : (prompt("추가할 연도를 입력하세요 (예: 2021)") || "").trim();
  if (!/^\d{4}$/.test(v)) { toast("연도는 4자리 숫자로 입력하세요."); return; }
  const isNew = !state.years.includes(v);
  if (isNew) {
    state.years.push(v);
    state.years.sort((a, b) => String(b).localeCompare(String(a)));
  }
  const copied = isNew ? await copyPrevYearConfig(v) : null;
  await changeYear(v);
  toast(copied
    ? `${v}년으로 전환했습니다 — 기준정보는 ${copied}년 사본입니다. 계획·zrfm2를 업로드하세요.`
    : `${v}년으로 전환했습니다. 계획·zrfm2를 업로드하세요.`);
}

// 새 연도는 빈 상태가 아니라 «직전 연도의 사본»으로 시작한다. 기준은 매년
// 조금씩만 바뀌므로 24개 지사와 19개 과목을 다시 입력하게 둘 이유가 없다.
// 이미 기준이 선 연도면 서버가 409 로 막는다 — 그때는 조용히 지나간다.
async function copyPrevYearConfig(to) {
  const prev = state.years.filter(y => String(y) < to).sort().slice(-1)[0];
  if (!prev) return null;
  const ok = confirm(`${to}년 기준정보를 ${prev}년에서 복사해 올까요?\n\n`
    + "지사 구성·예산과목 구성·기준정보 마스터를 그대로 가져옵니다.\n"
    + "가져온 뒤 설정 화면에서 고칠 수 있습니다.");
  if (!ok) return null;
  try {
    await api("/api/config/copy-year", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({from_year: prev, to_year: to})});
    return prev;
  } catch (e) {
    if (e.status === 409) toast(`${to}년 기준정보가 이미 있어 복사하지 않았습니다.`);
    else toast(`기준정보 복사 실패: ${e.message}`);
    return null;
  }
}

export async function runAnalyze(silent) {
  const n = state.pending?.total || 0;
  const t0 = Date.now();
  busy(true, `손익·자본 매칭 분석 중... (${state.year}년${n ? `, 미반영 ${n}건 반영` : ""})`);
  try {
    const res = await api("/api/analyze", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({year: state.year})});
    const p = res["손익"]["요약"], c = res["자본"]["요약"];
    const sec = ((Date.now() - t0) / 1000).toFixed(1);
    if (!silent) {
      toast(`분석 완료 (${sec}초) — 손익 ${fmt(p["총 실적(천원)"])}천원 / 자본 ${fmt(c["총 실적(천원)"])}천원`);
    }
    if (state.det.branch) await loadDetail(state.det.branch);
    await navigate(state.view);
    return true;
  } catch (e) { toast("분석 실패: " + e.message); return false; }
  finally { busy(false); }
}

// 헤더 분석 버튼 — 미반영 변경이 있으면 '분석 반영 (N)'으로 바뀌고 강조된다.

export function syncAnalyzeButton() {
  const btn = $("#analyzeBtn"), label = $("#analyzeLabel"), cnt = $("#pendingCount");
  if (!btn || !label || !cnt) return;
  const n = state.pending?.total || 0;
  label.textContent = n ? "분석 반영" : "분석 실행";
  btn.classList.toggle("btn-pending", n > 0);
  btn.title = n ? `저장된 변경 ${n}건을 분석에 반영합니다` : "손익·자본 매칭 분석 실행";
  cnt.textContent = n ? String(n) : "";
  cnt.classList.toggle("hidden", !n);
}

export async function uploadFile(kind, file) {
  busy(true, `${kind === "plan" ? "계획" : "zrfm2"} 자료를 ${state.year}년으로 DB에 흡수 중...`);
  try {
    const fd = new FormData();
    fd.append("file", file);
    const info = await api(`/api/upload/${kind}?year=${state.year}`, {method: "POST", body: fd});
    toast(`흡수 완료 — ${info.rows.toLocaleString()}행 (dataset #${info.dataset_id})`);
    await navigate(state.view);
  } catch (e) { toast(e.message); }
  finally { busy(false); }
}

// ───────────────────────── 이벤트 ─────────────────────────
