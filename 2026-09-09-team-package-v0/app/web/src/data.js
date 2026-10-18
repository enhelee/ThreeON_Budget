import { api } from "./api.js"
import { toast } from "./components/feedback.js"
import { renderPage } from "./router.js"
import { state } from "./state.js"

export function realBranches() {
  return (state.branches || []).map(r => r.branch).filter(b => !b.endsWith(" (미매핑)"));
}

export async function loadOverview() {
  applyOverview((await api("/api/overview")).years);
}

function applyOverview(rows) {
  state.overview = rows;   // 오름차순 [{year, 손익:{}, 자본:{}}]
  const ys = state.overview.map(r => r.year);
  for (const y of ys) if (!state.years.includes(y)) state.years.push(y);
  state.years.sort((a, b) => String(b).localeCompare(String(a)));
  if (!state.year) state.year = state.years[0] || String(new Date().getFullYear());
}

// 화면 전환 공통 3종(연도 목록·미반영 건수·열린 연도)을 요청 하나로 — DB 연결 3번 → 1번.
// 연도가 아직 없으면(첫 진입) 서버가 «자료가 있는 최신 연도»로 미반영을 센다. 화면이 고른
// 연도가 그와 다르면(자료 없는 해) 미반영만 따로 다시 받는다.
// 미반영·열린 연도는 예전처럼 실패해도 화면을 막지 않는다(null → 배지·배너만 안 뜬다).
export async function loadNavState() {
  const q = state.year ? `?year=${encodeURIComponent(state.year)}` : "";
  const d = await api(`/api/nav-state${q}`);
  applyOverview(d.years);
  state.lockStates = d.open;
  // 보고 있는 연도가 마감됐는지 — 마감 연도에는 «분석 반영»을 권하지 않는다(눌러도 423).
  state.yearLocked = d.year === state.year ? !!d.locked : null;
  if (d.year === state.year) state.pending = d.pending;
  else await loadPending();
}

// 메인 대시보드 전용 — 실패해도 화면 전체를 막지 않는다(해당 카드만 '-' 로 뜬다).

export async function loadHealth() {
  try { state.health = await api("/healthz"); }
  catch { state.health = null; }
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

// 마감을 풀어 놓은 연도(state.lockStates) — 어느 화면에 있든 배너로 알려야 한다.
// loadNavState 가 함께 받는다(실패하면 null → 배너만 안 뜬다).

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
  state.ycDirty = new Set();
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

// ───────────────────────── 5 중장기 예측 (3·4단계) ─────────────────────────
// 기준연도(base_year)는 헤더 대상연도와 다른 축이다 — 서버가 기본값을 정한다
// (상태가 있는 최신 기준연도, 없으면 마감 최신연도+1). 사용자가 고른 값은 유지한다.

// 기준연도를 아직 모르면(첫 진입) base_year 를 비워 보낸다 — 서버가 /base-years 의 default 와
// 같은 함수로 정하고 응답에 base_year 를 싣는다. 그래서 메타·가정·표를 동시에 부를 수 있다
// (순차로 기다리면 운영에서 탭 하나가 10초였다 — 2026-10-15 실측).
const fcQuery = () => state.fc.baseYear ? `?base_year=${encodeURIComponent(state.fc.baseYear)}` : "";
const adoptBase = d => { if (!state.fc.baseYear && d?.base_year) state.fc.baseYear = String(d.base_year); };

export async function loadForecastMeta() {
  const m = await api("/api/forecast/base-years");
  state.fc.baseYears = m.base_years;
  state.fc.lockedYears = m.locked_years;
  if (!state.fc.baseYear) state.fc.baseYear = m.default;
}

export async function loadForecastState() {
  state.fc.data = await api(`/api/forecast/state${fcQuery()}`);
  adoptBase(state.fc.data);
  state.fc.dirty = new Set();
}

export async function loadForecastBench() {
  state.fc.bench = await api(`/api/forecast/benchmark${fcQuery()}`);
  adoptBase(state.fc.bench);
  state.fc.benchEdits = {methods: {}, overrides: {}};
}

export async function loadForecastTable() {
  state.fc.table = await api(`/api/forecast/table${fcQuery()}`);
  adoptBase(state.fc.table);
}
