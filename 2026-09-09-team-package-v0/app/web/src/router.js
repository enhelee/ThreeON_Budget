import { api } from "./api.js"
import { busy, toast } from "./components/feedback.js"
import { loadBranches, loadDetail, loadOverview, loadPending, loadStatus } from "./data.js"
import { closeMenu } from "./main.js"
import { state, viewMeta } from "./state.js"
import { $, fmt } from "./util.js"
import { renderBranches } from "./views/branches.js"
import { renderCollect } from "./views/collect.js"
import { renderDetail } from "./views/detail.js"
import { renderForecast } from "./views/forecast.js"
import { renderHome } from "./views/home.js"
import { renderBudget } from "./views/plan.js"
import { renderSettings } from "./views/settings.js"
import { renderStats } from "./views/stats.js"

export function renderPage() {
  const renderers = {home: renderHome, budget: renderBudget, collect: renderCollect,
                     branches: renderBranches, detail: renderDetail, stats: renderStats,
                     forecast: renderForecast, settings: renderSettings};
  $("#page").innerHTML = renderers[state.view]();
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

export async function navigate(view) {
  state.view = view;
  try {
    await loadOverview();
    await loadPending();
    if (view === "home" || view === "branches" || view === "detail") { await loadStatus(); await loadBranches(); }
    if (view === "budget" || view === "collect") await loadStatus();
    if (view === "stats") {
      state.stats = await api(`/api/stats?year=${state.year}`);
      state.statsCompare = await api(`/api/stats-compare?year=${state.year}`);
    }
    if (view === "settings") {
      await loadStatus();
      state.overrides = await api(`/api/overrides?year=${state.year}`);
      state.learned = await api("/api/learned");
      state.audit = (await api("/api/audit?limit=50")).rows;
      state.models = await api("/api/models");
      state.bizEdits = await api(`/api/biz-edits?year=${state.year}`);
      state.manualBiz = await api(`/api/manual-biz?year=${state.year}`);
      state.bizDeletes = await api(`/api/biz-deletes?year=${state.year}`);
    }
  } catch (e) { toast(e.message); }
  renderPage();
  closeMenu();
  window.scrollTo({top: 0, behavior: "smooth"});
}

export async function changeYear(y) {
  state.year = String(y);
  state.det = {...state.det, branch: "", data: null, open: new Set(), sel: new Set(), selBudget: null, editKey: null};
  await navigate(state.view);
}

export function addYearFromInput(inputId) {
  const el = inputId ? document.getElementById(inputId) : null;
  const v = el ? el.value.trim() : (prompt("추가할 연도를 입력하세요 (예: 2021)") || "").trim();
  if (!/^\d{4}$/.test(v)) { toast("연도는 4자리 숫자로 입력하세요."); return; }
  if (!state.years.includes(v)) {
    state.years.push(v);
    state.years.sort((a, b) => String(b).localeCompare(String(a)));
  }
  changeYear(v);
  toast(`${v}년으로 전환했습니다. 계획·zrfm2를 업로드하세요.`);
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
