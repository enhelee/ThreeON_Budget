import { api } from "../api.js"
import { state } from "../state.js"
import { esc, fmt } from "../util.js"

export function renderSettingsExtra() {
  const audit = state.audit || [];
  const reg = state.models || {models: [], names: [], stats: {}};
  const modelsByName = {};
  for (const m of reg.models) (modelsByName[m.name] ||= []).push(m);
  const auditRows = audit.length ? audit.map(a => `<tr class="hover:bg-slate-50"><td class="table-cell mono">${esc(a.at)}</td><td class="table-cell font-semibold text-slate-800">${esc(a.operator || "-")}</td><td class="table-cell mono">${esc(a.method)} ${esc(a.path)}</td><td class="table-cell text-right">${a.status}</td><td class="table-cell audit-detail">${esc(a.detail || "")}</td></tr>`).join("")
    : `<tr><td class="table-cell text-slate-400" colspan="5">기록이 없습니다.</td></tr>`;
  const modelPanels = reg.names.map(name => {
    const st = reg.stats[name] || {total: 0, confirmed: 0, unconfirmed: 0, per_class: {}, trainable: false};
    const vers = modelsByName[name] || [];
    const verRows = vers.length ? vers.map(m => `<tr class="hover:bg-slate-50"><td class="table-cell font-semibold">v${m.version}${m.active ? ' <span class="badge bg-emerald-50 text-emerald-700">활성</span>' : ""}</td><td class="table-cell mono">${esc(m.trained_at)}</td><td class="table-cell text-right">${m.n_samples ?? "-"}</td><td class="table-cell text-right">${m.n_classes ?? "-"}</td><td class="table-cell text-right">${m.metrics?.cv_accuracy ?? "-"}</td><td class="table-cell">${esc(m.created_by || "-")}</td><td class="table-cell text-slate-500">${esc(m.note || "")}</td><td class="table-cell text-right"><div class="flex flex-wrap justify-end gap-1">${m.active ? "" : `<button class="btn-secondary" data-action="activate-model" data-id="${m.id}">활성화</button>`}<a class="btn-secondary" href="/api/models/${m.id}/download">다운로드</a></div></td></tr>`).join("")
      : `<tr><td class="table-cell text-slate-400" colspan="8">등록된 모델 버전이 없습니다 — 학습데이터를 채운 뒤 [재학습]을 누르거나 <span class="mono">scripts/v2_model_sync.py --push</span>로 팀 v2 파일을 반입하세요.</td></tr>`;
    const perClass = Object.entries(st.per_class || {}).map(([k, v]) => `<span class="badge bg-slate-100 text-slate-700">${esc(k)} ${v}</span>`).join(" ");
    return `<div class="border-t border-slate-200 p-5 sm:p-6">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div><h4 class="text-sm font-bold text-slate-800">${esc(name)}</h4>
        <p class="section-help">학습데이터 <b>${st.total}</b>건 (사람확정 ${st.confirmed} · 미확정 ${st.unconfirmed}) ${st.trainable ? '<span class="badge bg-emerald-50 text-emerald-700">재학습 가능</span>' : '<span class="badge bg-amber-50 text-amber-700">데이터 부족(20건·2유형 이상)</span>'}</p>
        <div class="mt-2 flex flex-wrap gap-1">${perClass || '<span class="text-xs text-slate-400">라벨 없음</span>'}</div></div>
        <div class="flex flex-wrap gap-2">
          <button class="btn-primary" data-action="train" data-name="${esc(name)}" ${st.trainable ? "" : "disabled"}>재학습 → 새 버전</button>
          <button class="btn-secondary" data-action="pick-training" data-name="${esc(name)}">학습 CSV 가져오기</button>
          <a class="btn-secondary" href="/api/training/export.csv?name=${encodeURIComponent(name)}">학습 CSV 내보내기</a>
        </div>
      </div>
      <div class="mt-4 overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-4 py-3">버전</th><th class="px-4 py-3">학습시각</th><th class="px-4 py-3 text-right">표본</th><th class="px-4 py-3 text-right">유형</th><th class="px-4 py-3 text-right">CV정확도</th><th class="px-4 py-3">학습자</th><th class="px-4 py-3">비고</th><th class="px-4 py-3"></th></tr></thead><tbody class="divide-y divide-slate-100">${verRows}</tbody></table></div>
    </div>`;
  }).join("");
  return `
    <section class="panel overflow-hidden">
      <div class="flex flex-wrap items-start justify-between gap-3 p-5 sm:p-6">
        <div><h3 class="section-title">🧾 변경 이력 (감사 로그)</h3>
        <p class="section-help">공용 비밀번호 체계에서 <b>누가·언제·무엇을</b> 바꿨는지의 근거입니다. 로그인 때 입력한 작업자 이름으로 모든 변경 요청(재배정·수정·삭제·추가·분석·학습·마감)이 기록됩니다. 최근 ${audit.length}건.</p></div>
        <button class="btn-secondary" data-action="reload-audit">새로고침</button>
      </div>
      <div class="overflow-x-auto"><table class="w-full audit-table"><thead class="table-head"><tr><th class="px-4 py-3">시각</th><th class="px-4 py-3">작업자</th><th class="px-4 py-3">요청</th><th class="px-4 py-3 text-right">상태</th><th class="px-4 py-3">요약</th></tr></thead><tbody class="divide-y divide-slate-100">${auditRows}</tbody></table></div>
    </section>

    <section class="panel overflow-hidden">
      <div class="p-5 sm:p-6"><h3 class="section-title">🧪 분류 모델 레지스트리 · 학습데이터</h3>
        <p class="section-help">팀 v2 앱의 투자유형 분류기(scikit-learn)를 <b>DB에 버전으로 보관</b>합니다 — 모델 파일(joblib)·학습시각·표본수·CV정확도·SHA256·학습데이터 스냅샷이 함께 남고, <b>활성</b> 버전 하나만 서비스에 쓰입니다(잘못 학습되면 이전 버전 활성화로 즉시 롤백). 학습데이터는 <b>사람이 확정한 라벨이 자동 예측값보다 우선</b>하며, 재학습은 이 화면의 버튼으로만 실행됩니다(자동 재학습 없음). 팀 v2 앱은 파일에서 모델을 읽으므로 <span class="mono">py scripts/v2_model_sync.py --pull</span>로 활성 버전을 내려받아 씁니다.</p></div>
      ${modelPanels}
    </section>`;
}

export function renderSettings() {
  const ds = state.status?.datasets || [];
  const ovs = state.overrides || {};
  const ovRows = ["손익", "자본"].flatMap(b => (ovs[b] || []).map(o => ({...o, budget: b})));
  const learned = state.learned || {};
  const edits = state.bizEdits || [];
  return `<div class="space-y-6">
    <section><p class="text-sm font-semibold text-blue-700">운영 관리</p><h2 class="mt-1 text-2xl font-bold tracking-tight text-slate-950">데이터 관리</h2>
    <p class="mt-2 text-sm text-slate-500">모든 원자료는 백엔드 DB(data/budget.db)에만 저장됩니다.</p></section>
    ${renderSettingsExtra()}

    <section class="panel p-6">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div><h3 class="section-title">🔒 연도 마감 (잠금)</h3>
        <p class="section-help">검토·학습까지 끝난 연도를 마감하면 <b>업로드·분석·재배정·수정이 전부 차단</b>되어, 이후 학습이 업그레이드되어도 완료된 연도의 숫자가 절대 바뀌지 않습니다. 조회·통계·Excel 내보내기는 계속 가능합니다.</p></div>
        <div class="flex flex-wrap gap-2">
          ${state.status?.locked
            ? `<button class="btn-secondary" data-action="unlock-year">🔓 ${esc(state.year)}년 잠금 해제</button>`
            : `<button class="btn-primary" data-action="lock-year">🔒 ${esc(state.year)}년 마감(잠금)</button>`}
        </div>
      </div>
      ${Object.keys(state.status?.locks || {}).length ? `<div class="mt-4 flex flex-wrap gap-2">${Object.entries(state.status.locks).map(([y, at]) => `<span class="badge bg-amber-50 text-amber-800">🔒 ${y}년 (${esc(at)})</span>`).join("")}</div>` : `<p class="mt-4 text-xs text-slate-400">마감된 연도가 없습니다.</p>`}
    </section>

    <section class="panel p-6">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div><h3 class="section-title">🧠 AI 학습 (수동 실행)</h3>
        <p class="section-help">학습 DB는 <b>연도 구분 없이 하나</b>입니다 — 어느 연도에서 학습했든 <b>모든 연도 분석에 공통 적용</b>됩니다. 재배정은 <b>저장 시 학습하지 않습니다</b>(rev13에서 분리) — 검토가 끝난 뒤 아래 버튼으로 한 번에 학습하세요. 같은 텍스트의 전표는 유사도 계산보다 학습 결과를 우선 적용(확신도 0.99, 사람 확정 &gt; 자동 확정)하며, <b>사람이 직접 재배정한 전표는 학습이 덮지 못합니다</b>(확신도 1.0).</p>
        <p class="mt-2 text-xs font-semibold text-amber-700">순서: ① 상세에서 수정·저장 → ② 상단 <b>분석 반영</b> → ③ 여기서 <b>AI 학습</b> → ④ 연도 마감. 분석 반영 전에 학습하면 방금 한 수정이 학습에 안 들어갑니다.</p></div>
        <div class="flex flex-wrap gap-2">
          <button class="btn-primary" data-action="learn">${esc(state.year)}년 확정 결과 AI 학습${(state.pending?.learn_pending || 0) ? ` (대기 ${state.pending.learn_pending}건)` : ""}</button>
          <button class="btn-secondary" data-action="clear-learned">학습 초기화</button>
        </div>
      </div>
      ${(state.pending?.total || 0) ? `<p class="mt-4 text-xs font-semibold text-amber-700">⚠ 분석 미반영 변경 ${state.pending.total}건이 있습니다 — 먼저 상단 '분석 반영'을 누르세요.</p>` : ""}
      <div class="mt-5 grid gap-3 sm:grid-cols-3">
        <div class="rounded-xl bg-slate-50 p-4"><p class="text-xs font-semibold text-slate-500">학습된 매핑 총계 (전체 연도 공용)</p><p class="mt-1 text-2xl font-bold">${(learned["총계"] || 0).toLocaleString()}건</p></div>
        <div class="rounded-xl bg-blue-50 p-4"><p class="text-xs font-semibold text-blue-700">사람 확정(재배정)</p><p class="mt-1 text-2xl font-bold text-blue-950">${(learned["수동확정"] || 0).toLocaleString()}건</p></div>
        <div class="rounded-xl bg-slate-50 p-4"><p class="text-xs font-semibold text-slate-500">자동 확정</p><p class="mt-1 text-2xl font-bold">${(learned["자동확정"] || 0).toLocaleString()}건</p></div>
      </div>
      <p class="mt-4 text-xs text-slate-400">'학습 대기'는 재배정한 전표 중 아직 학습표에 없는 건수입니다(텍스트 없는 전표는 학습 대상이 아닙니다).</p>
    </section>

    <section class="panel p-6">
      <h3 class="section-title">📚 기준정보 마스터</h3>
      <p class="section-help">예산과목(계정코드·속성)·부서코드(처지사) 마스터 — 속성(일반/제조/건가/자산) 교정, ERP 과목 정규화, 계획행 처지사 보정에 사용됩니다. 조직개편·계정 신설 시 새 파일을 올려 갱신하세요(같은 코드는 덮어씀).</p>
      <div class="mt-4 grid gap-3 sm:grid-cols-2">
        <div class="rounded-xl bg-slate-50 p-4"><div class="flex items-center justify-between"><p class="text-xs font-semibold text-slate-500">예산과목 마스터</p><button class="btn-secondary" data-action="pick-master-item">파일 갱신</button></div><p class="mt-2 text-2xl font-bold">${(state.status?.master?.예산과목 || 0).toLocaleString()}건</p><p class="mt-1 text-xs text-slate-400">양식: 계정코드·이름·주관부서코드·주관부서명·속성·비고</p></div>
        <div class="rounded-xl bg-slate-50 p-4"><div class="flex items-center justify-between"><p class="text-xs font-semibold text-slate-500">부서코드 마스터</p><button class="btn-secondary" data-action="pick-master-dept">파일 갱신</button></div><p class="mt-2 text-2xl font-bold">${(state.status?.master?.부서코드 || 0).toLocaleString()}건</p><p class="mt-1 text-xs text-slate-400">양식: 부서코드·부서명·처지사·비고</p></div>
      </div>
      <input id="masterItemFile" class="hidden" type="file" accept=".xlsx">
      <input id="masterDeptFile" class="hidden" type="file" accept=".xlsx">
    </section>

    <section class="panel overflow-hidden"><div class="border-b border-slate-200 p-5"><h3 class="section-title">등록 데이터셋</h3></div>
    <div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-4 py-3">ID</th><th class="px-4 py-3">종류</th><th class="px-4 py-3">연도</th><th class="px-4 py-3">파일</th><th class="px-4 py-3 text-right">행수</th><th class="px-4 py-3">업로드</th></tr></thead>
    <tbody class="divide-y divide-slate-100">${ds.map(d => `<tr><td class="table-cell">${d.id}</td><td class="table-cell"><span class="badge ${d.kind === "plan" ? "bg-blue-50 text-blue-700" : "bg-emerald-50 text-emerald-700"}">${d.kind}</span></td><td class="table-cell">${d.year}</td><td class="table-cell">${esc(d.label)}</td><td class="table-cell text-right">${d.row_count.toLocaleString()}</td><td class="table-cell text-xs text-slate-500">${esc(d.uploaded_at)}</td></tr>`).join("")}</tbody></table></div></section>

    <section class="panel overflow-hidden"><div class="border-b border-slate-200 p-5"><h3 class="section-title">수동 재배정 이력 (${esc(state.year)}년)</h3><p class="section-help">삭제하면 다음 분석 실행부터 자동 매칭으로 돌아갑니다.</p></div>
    ${ovRows.length ? `<div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-4 py-3">ID</th><th class="px-4 py-3">구분</th><th class="px-4 py-3">전표행</th><th class="px-4 py-3">배정 사업명</th><th class="px-4 py-3">일시</th><th class="px-4 py-3 text-right">삭제</th></tr></thead>
    <tbody class="divide-y divide-slate-100">${ovRows.map(o => `<tr><td class="table-cell">${o.id}</td><td class="table-cell">${o.budget}</td><td class="table-cell">${o.erp_row_id}</td><td class="table-cell font-semibold">${esc(o.target_name)}</td><td class="table-cell text-xs text-slate-500">${esc(o.created_at)}</td><td class="table-cell text-right"><button class="btn-secondary" data-del-override="${o.id}">삭제</button></td></tr>`).join("")}</tbody></table></div>` : `<p class="p-5 text-sm text-slate-500">재배정 이력이 없습니다.</p>`}</section>

    <section class="panel overflow-hidden"><div class="border-b border-slate-200 p-5"><h3 class="section-title">수동 추가 사업 (${esc(state.year)}년)</h3><p class="section-help">상세 화면 '＋ 사업 추가'로 등록한 사업입니다. 삭제하면 다음 분석부터 제외됩니다.</p></div>
    ${(state.manualBiz || []).length ? `<div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-4 py-3">ID</th><th class="px-4 py-3">구분</th><th class="px-4 py-3">지사</th><th class="px-4 py-3">예산과목</th><th class="px-4 py-3">사업명</th><th class="px-4 py-3 text-right">연예산(천원)</th><th class="px-4 py-3">일시</th><th class="px-4 py-3 text-right">삭제</th></tr></thead>
    <tbody class="divide-y divide-slate-100">${state.manualBiz.map(m => `<tr><td class="table-cell">${m.id}</td><td class="table-cell">${m.budget}</td><td class="table-cell">${esc(m.처지사)}</td><td class="table-cell">${esc(m.예산과목)}</td><td class="table-cell font-semibold">${esc(m.사업명)}</td><td class="table-cell text-right">${fmt(m.연예산)}</td><td class="table-cell text-xs text-slate-500">${esc(m.created_at)}</td><td class="table-cell text-right"><button class="btn-secondary" data-del-manual="${m.id}">삭제</button></td></tr>`).join("")}</tbody></table></div>` : `<p class="p-5 text-sm text-slate-500">수동 추가 사업이 없습니다.</p>`}</section>

    <section class="panel overflow-hidden"><div class="border-b border-slate-200 p-5"><h3 class="section-title">사업 내용 수정 이력 (${esc(state.year)}년)</h3><p class="section-help">상세 화면 ✎로 저장한 수정입니다. 삭제하면 다음 분석부터 원본으로 돌아갑니다.</p></div>
    ${edits.length ? `<div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-4 py-3">ID</th><th class="px-4 py-3">구분</th><th class="px-4 py-3">대상 사업</th><th class="px-4 py-3">수정 내용</th><th class="px-4 py-3">일시</th><th class="px-4 py-3 text-right">삭제</th></tr></thead>
    <tbody class="divide-y divide-slate-100">${edits.map(e => `<tr><td class="table-cell">${e.id}</td><td class="table-cell">${e.budget}</td><td class="table-cell">${esc(e.처지사)} · ${esc(e.예산과목)} · ${esc(e.사업명)}</td><td class="table-cell text-xs">${esc(Object.entries(e.fields).map(([k, v]) => `${k}→${v === "" ? "(빈칸)" : v}`).join(", "))}</td><td class="table-cell text-xs text-slate-500">${esc(e.created_at)}</td><td class="table-cell text-right"><button class="btn-secondary" data-del-edit="${e.id}">삭제</button></td></tr>`).join("")}</tbody></table></div>` : `<p class="p-5 text-sm text-slate-500">수정 이력이 없습니다.</p>`}</section>

    <section class="panel overflow-hidden"><div class="border-b border-slate-200 p-5"><h3 class="section-title">사업 삭제 이력 (${esc(state.year)}년)</h3><p class="section-help">상세 화면에서 삭제한 사업입니다. 원본 계획 자료는 지워지지 않았으므로, 여기서 <b>되돌리기</b>를 누르면 다음 분석부터 다시 살아납니다.</p></div>
    ${(state.bizDeletes || []).length ? `<div class="overflow-x-auto"><table class="w-full"><thead class="table-head"><tr><th class="px-4 py-3">ID</th><th class="px-4 py-3">구분</th><th class="px-4 py-3">삭제한 사업</th><th class="px-4 py-3">전표 처리</th><th class="px-4 py-3">일시</th><th class="px-4 py-3 text-right">되돌리기</th></tr></thead>
    <tbody class="divide-y divide-slate-100">${state.bizDeletes.map(x => `<tr><td class="table-cell">${x.id}</td><td class="table-cell">${x.budget}</td><td class="table-cell">${esc(x.처지사)} · ${esc(x.예산과목)} · <b>${esc(x.사업명)}</b></td><td class="table-cell text-xs text-slate-500">${esc(x.memo || "귀속 전표 없음")}</td><td class="table-cell text-xs text-slate-500">${esc(x.created_at)}</td><td class="table-cell text-right"><button class="btn-secondary" data-restore-del="${x.id}">되돌리기</button></td></tr>`).join("")}</tbody></table></div>` : `<p class="p-5 text-sm text-slate-500">삭제한 사업이 없습니다.</p>`}</section>
  </div>`;
}

// ───────────────────────── 렌더 & 라우팅 ─────────────────────────
