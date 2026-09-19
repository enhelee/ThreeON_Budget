import { api } from "./api.js"
import { toast } from "./components/feedback.js"
import { renderPage } from "./router.js"
import { state } from "./state.js"

export function realBranches() {
  return (state.branches || []).map(r => r.branch).filter(b => !b.endsWith(" (미매핑)"));
}

export async function loadOverview() {
  state.overview = (await api("/api/overview")).years;   // 오름차순 [{year, 손익:{}, 자본:{}}]
  const ys = state.overview.map(r => r.year);
  for (const y of ys) if (!state.years.includes(y)) state.years.push(y);
  state.years.sort((a, b) => String(b).localeCompare(String(a)));
  if (!state.year) state.year = state.years[0] || String(new Date().getFullYear());
}

// 메인 대시보드 전용 — 실패해도 화면 전체를 막지 않는다(해당 카드만 '-' 로 뜬다).

export async function loadHealth() {
  try { state.health = await api("/healthz"); }
  catch { state.health = null; }
}

export async function loadExportStatus() {
  try { state.exportStatus = await api(`/api/export-status?year=${state.year}`); }
  catch { state.exportStatus = null; }
}

export async function loadStatus() {
  state.status = await api(`/api/status?year=${state.year}`);
}
// 분석에 아직 반영되지 않은 변경 건수 — 저장은 즉시, 분석은 모아서 한 번.

export async function loadPending() {
  try { state.pending = await api(`/api/pending?year=${state.year}`); }
  catch { state.pending = null; }
}
// 저장 후 공통 처리: 미반영 배지 갱신 + 화면 부분 갱신(분석은 하지 않는다)

export async function afterSave(msg) {
  await loadPending();
  if (state.view === "detail" && state.det.branch) await loadDetail(state.det.branch);
  renderPage();
  const n = state.pending?.total || 0;
  toast(msg + (n ? ` · 미반영 ${n}건 — 상단 '분석 반영'을 누르면 결과에 적용됩니다.` : ""));
}

// 마감을 풀어 놓은 연도 — 어느 화면에 있든 배너로 알려야 한다.
// 실패해도 화면을 막지 않는다(배너만 안 뜬다).

export async function loadLockStates() {
  try { state.lockStates = (await api("/api/lock-state")).open; }
  catch { state.lockStates = null; }
}

// 설정 화면 「연도 기준정보」 — 그 해 한 벌을 한 번에 끌어온다.
// 별칭만 연도가 없다(표기 흔들림 보정은 연도가 바뀌어도 유효하다).

export async function loadYearConfig() {
  const year = state.year;
  const q = b => `/api/config/items?year=${year}&budget=${encodeURIComponent(b)}`;
  const [depts, pl, cap, alias, mi, md] = await Promise.all([
    api(`/api/config/depts?year=${year}`),
    api(q("손익")), api(q("자본")),
    api("/api/config/alias"),
    api(`/api/master/items?year=${year}`),
    api(`/api/master/depts?year=${year}`),
  ]);
  state.yearConfig = {
    depts: depts.rows,
    items: {"손익": pl.rows, "자본": cap.rows},
    alias: {item: alias.item, dept: alias.dept},
    aliasSeeded: alias.seeded,
    masters: {items: mi.rows, depts: md.rows},
  };
}

export async function loadBranches() {
  state.branches = (await api(`/api/branches?year=${state.year}`)).rows;
}

export async function loadDetail(branch) {
  state.det.data = await api(`/api/branch-detail?year=${state.year}&branch=${encodeURIComponent(branch)}`);
  state.det.branch = branch;
  state.det.open = new Set(); state.det.sel = new Set();
  state.det.selBudget = null; state.det.editKey = null; state.det.delKey = null;
  state.det.ovDept = ""; state.det.ovTarget = ""; state.det.ovManual = "";
}

// 재배정에서 '이동할 지사'를 고르면 그 지사의 기존 사업명을 목록에 채운다(연도·지사별 캐시).

export async function loadOvBiz(branch) {
  const k = `${state.year}|${branch}`;
  if (state.ovBiz[k]) return state.ovBiz[k];
  const d = await api(`/api/branch-detail?year=${state.year}&branch=${encodeURIComponent(branch)}`);
  state.ovBiz[k] = (d.biz || []).map(b => ({budget: b.budget, 사업명: b.사업명}));
  return state.ovBiz[k];
}

export function amounts(row) {
  if (state.type === "profit") return { plan: row.profitPlan, actual: row.profitActual };
  if (state.type === "capital") return { plan: row.capitalPlan, actual: row.capitalActual };
  return { plan: row.profitPlan + row.capitalPlan, actual: row.profitActual + row.capitalActual };
}

// ───────────────────────── 홈 (다년도) ─────────────────────────
