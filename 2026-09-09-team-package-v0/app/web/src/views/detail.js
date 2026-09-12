import { confBadge, gubunBadge } from "../components/badges.js"
import { emptyState, pendingBarHtml } from "../components/widgets.js"
import { realBranches } from "../data.js"
import { state } from "../state.js"
import { esc, fmt, fmtRate } from "../util.js"

export const DET_COLS = [
  ["budget", "구분"], ["예산과목", "예산과목"], ["속성", "속성"], ["사업명", "사업명"],
  ["연예산원", "연예산(A)"], ["실적원", "실적금액(B)"], ["구분", "상태"], ["확신도", "확신도"],
];

export function detSortArrow(key) {
  if (state.det.sortKey !== key) return '<span class="text-slate-300">↕</span>';
  return state.det.sortDir > 0 ? "▲" : "▼";
}

export function legend() {
  return `<div class="flex flex-wrap items-center gap-4 text-xs text-slate-600">
    <span class="flex items-center gap-1.5"><span class="swatch" style="background:#fff;border:1px solid #cbd5e1"></span>계획집행 — 계획 사업에 실적이 붙음</span>
    <span class="flex items-center gap-1.5"><span class="swatch" style="background:#fef2f2"></span><b>분홍</b> = 미시행 (계획은 있으나 실적 0)</span>
    <span class="flex items-center gap-1.5"><span class="swatch" style="background:#fffbeb"></span><b>노랑</b> = 신규 (계획에 없던 집행)</span>
    <span class="flex items-center gap-1.5"><span class="swatch" style="background:#f1f5f9"></span><b>회색</b> = 미매핑 (지사 미확정 — 재배정으로 지사 지정, 종합표 미포함)</span>
    <span class="flex items-center gap-1.5">확신도: <span class="badge bg-emerald-50 text-emerald-700">0.80↑ 자동확정</span><span class="badge bg-amber-50 text-amber-700">0.80미만 검토 필요</span></span>
  </div>`;
}

export function renderDetail() {
  const d = state.det;
  const branchOpts = (state.branches || []).map(r => `<option value="${esc(r.branch)}" ${r.branch === d.branch ? "selected" : ""}>${esc(r.branch)}</option>`).join("");
  if (!d.data) {
    return `<div class="space-y-6">
      <section><p class="text-sm font-semibold text-blue-700">STAGE 3+</p><h2 class="mt-1 text-2xl font-bold tracking-tight text-slate-950">실적분석 (상세) — ${esc(state.year)}년</h2>
      <p class="mt-2 text-sm text-slate-500">지사를 선택하면 손익·자본 구분 없이 전체 사업 목록이 표시됩니다.</p></section>
      <section class="panel p-5"><label class="block max-w-sm"><span class="mb-1.5 block text-xs font-semibold text-slate-500">지사 선택</span>
      <select class="control w-full" data-det="branch"><option value="">지사를 선택하세요</option>${branchOpts}</select></label>
      ${!(state.branches || []).length ? `<p class="mt-4 text-sm text-amber-700">분석 이력이 없습니다. 먼저 '실적 집계'에서 분석을 실행하세요.</p>` : ""}</section>
    </div>`;
  }
  const locked = !!state.status?.locked;
  return `
    <div class="space-y-6">
      <section class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div><p class="text-sm font-semibold text-blue-700">STAGE 3+ · ${esc(state.year)}년</p>
        <h2 class="mt-1 text-2xl font-bold tracking-tight text-slate-950">${esc(d.branch)} — 사업별 실적 검토</h2>
        <p class="mt-2 text-sm text-slate-500">사업 클릭=전표 트리 · 컬럼 제목 클릭=정렬 · ✎=내용 수정 · 전표 체크=재배정. <b>수정은 즉시 저장되고, 분석 반영은 모아서 한 번</b> 하면 됩니다.</p></div>
        <button class="btn-secondary" data-view="branches">← 전체 지사</button>
      </section>
      ${pendingBarHtml()}
      <section class="panel p-5"><div class="flex flex-wrap items-end gap-3">
        <label class="block"><span class="mb-1.5 block text-xs font-semibold text-slate-500">지사</span><select class="control" data-det="branch">${branchOpts}</select></label>
        <label class="block"><span class="mb-1.5 block text-xs font-semibold text-slate-500">예산구분</span><select class="control" data-det="budget"><option value="all" ${d.budget === "all" ? "selected" : ""}>전체</option><option value="손익" ${d.budget === "손익" ? "selected" : ""}>손익</option><option value="자본" ${d.budget === "자본" ? "selected" : ""}>자본</option></select></label>
        <label class="block"><span class="mb-1.5 block text-xs font-semibold text-slate-500">예산과목</span><select class="control" data-det="item"><option value="">전체</option>${d.data.items.map(it => `<option value="${esc(it)}" ${d.item === it ? "selected" : ""}>${esc(it)}</option>`).join("")}</select></label>
        <label class="block"><span class="mb-1.5 block text-xs font-semibold text-slate-500">속성</span><select class="control" data-det="attr"><option value="">전체</option>${d.data.attrs.map(a => `<option value="${esc(a)}" ${d.attr === a ? "selected" : ""}>${esc(a)}</option>`).join("")}</select></label>
        <label class="block min-w-48 flex-1"><span class="mb-1.5 block text-xs font-semibold text-slate-500">사업명 검색</span><input class="control w-full" data-det="q" value="${esc(d.q)}" placeholder="사업명 일부를 입력"></label>
        <label class="flex items-center gap-2 pb-2 text-sm font-semibold text-slate-600"><input type="checkbox" class="accent-blue-600" data-det-check="hideMissing" ${d.hideMissing ? "checked" : ""}>미시행 숨기기</label>
        ${locked ? "" : `<button class="btn-secondary" data-action="toggle-add">＋ 사업 추가</button>`}
      </div></section>
      ${!locked && d.addOpen ? addBizFormHtml() : ""}
      ${locked ? `<section class="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-semibold text-amber-900">🔒 ${esc(state.year)}년은 마감(잠금) 상태입니다 — 조회만 가능하며 재배정·수정이 차단됩니다. (설정 탭에서 해제 가능)</section>` : ""}
      <div id="detResults">${detResultsHtml()}</div>
    </div>`;
}

// 수동 사업 추가 폼 — 계획본에 없는 사업을 이 지사에 직접 등록

export function addBizFormHtml() {
  const d = state.det;
  const add = d.add || (d.add = {budget: "손익"});
  const items = state.status?.items?.[add.budget] || [];
  return `
    <section class="panel border-blue-300 bg-blue-50 p-5">
      <p class="mb-3 text-sm font-bold text-blue-950">＋ 사업 추가 — <b>${esc(d.branch)}</b>에 계획본에 없는 사업을 등록합니다
        <span class="ml-2 text-xs font-medium text-blue-700">저장 후 자동 재분석되어 목록에 나타나고(실적 없으면 '미시행'), 전표 재배정 대상 사업으로 쓸 수 있습니다.</span></p>
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label class="block"><span class="mb-1.5 block text-xs font-semibold text-blue-700">예산구분</span>
          <select id="abBudget" class="control w-full" data-add-budget="1">
            <option value="손익" ${add.budget === "손익" ? "selected" : ""}>손익</option>
            <option value="자본" ${add.budget === "자본" ? "selected" : ""}>자본</option></select></label>
        <label class="block"><span class="mb-1.5 block text-xs font-semibold text-blue-700">예산과목 *</span>
          <select id="abItem" class="control w-full">${items.map(it => `<option value="${esc(it)}">${esc(it)}</option>`).join("")}</select></label>
        <label class="block"><span class="mb-1.5 block text-xs font-semibold text-blue-700">속성 (비우면 마스터 자동)</span>
          <select id="abAttr" class="control w-full"><option value="">(자동)</option>${["일반", "제조", "건가", "자산"].map(a => `<option value="${a}">${a}</option>`).join("")}</select></label>
        <label class="block"><span class="mb-1.5 block text-xs font-semibold text-blue-700">연예산 (천원)</span><input id="abPlan" class="control w-full" type="number" min="0" placeholder="0"></label>
        <label class="block sm:col-span-2"><span class="mb-1.5 block text-xs font-semibold text-blue-700">사업명 *</span><input id="abName" class="control w-full" placeholder="사업명을 입력하세요"></label>
        <label class="block"><span class="mb-1.5 block text-xs font-semibold text-blue-700">주관부서명</span><input id="abOwner" class="control w-full"></label>
        <label class="block"><span class="mb-1.5 block text-xs font-semibold text-blue-700">예산귀속 부서명(부)</span><input id="abPart" class="control w-full"></label>
      </div>
      <div class="mt-4 flex gap-2">
        <button class="btn-primary" data-action="save-add">사업 추가 (자동 재분석)</button>
        <button class="btn-secondary" data-action="toggle-add">닫기</button>
      </div>
    </section>`;
}

// 사업 삭제 확인 상자 — 귀속 전표가 있으면 '어디로 옮길지'를 반드시 고르게 한다.
//   전표를 그냥 지우면 ERP 총액과 어긋나므로, 삭제는 언제나 (전표 이동 + 계획행 제외)다.

export function unassignedName(b) {
  return `${state.det.branch} ${b.예산과목} 미지정`;
}

export function deleteBoxHtml(b, key) {
  if (state.det.delKey !== key) return "";
  const n = (b.전표 || []).length;
  const hasPlan = !String(b.구분 ?? "").startsWith("신규") && b.구분 !== "미매핑";
  // 자기 자신만 제외(이름이 아니라 행 단위) — 동명 사업이 둘일 때 쌍둥이를 대상으로
  //   고를 수 있어야 중복을 하나로 합칠 수 있다.
  const others = [...new Set((state.det.data.biz || [])
    .map((x, idx) => ({...x, _k: `${x.budget}|${x.예산과목}|${x.사업명}|${idx}`}))
    .filter(x => x.budget === b.budget && x.예산과목 === b.예산과목 && x._k !== key
                 && !(hasPlan && x.사업명 === b.사업명))
    .map(x => x.사업명))].sort((x, y) => String(x).localeCompare(String(y), "ko"));
  return `
    <div class="danger-box">
      <p class="danger-title">사업 삭제 — "${esc(b.사업명)}"</p>
      ${!hasPlan ? `<p class="danger-text">이 사업은 계획에 없는 <b>${esc(b.구분)}</b> 행입니다 — 귀속 전표를 옮기면 그대로 사라집니다(삭제 기록을 남기지 않습니다).</p>` : ""}
      ${n ? `
      <p class="danger-text">귀속 전표 <b>${n}건 · ${fmt(b.실적원)}원</b>이 있습니다. 총액이 어긋나지 않게 <b>먼저 옮길 곳을 고르세요.</b>${hasPlan ? " 옮긴 뒤 이 사업을 삭제합니다." : ""}</p>
      <label class="mt-3 block max-w-30"><span class="danger-label">전표를 옮길 사업 (같은 지사 · 같은 예산과목)</span>
        <select id="delTarget" class="control w-full">
          ${others.map(o => `<option value="${esc(o)}">${esc(o)}</option>`).join("")}
          <option value="__unassigned__" ${others.length ? "" : "selected"}>— 미지정 항목으로 이동 (${esc(unassignedName(b))}) —</option>
        </select></label>` : `
      <p class="danger-text">귀속 전표가 없습니다. 계획행(연예산 <b>${fmt(b.연예산)}천원</b>)이 이후 분석에서 제외됩니다.</p>`}
      ${hasPlan ? `<p class="danger-text">원본 계획 자료는 지우지 않습니다 — 설정 탭 <b>'사업 삭제 이력'</b>에서 되돌릴 수 있습니다.</p>` : `<p class="danger-text">되돌리려면 설정 탭 <b>'수동 재배정 이력'</b>에서 해당 이동 기록을 지우면 됩니다.</p>`}
      <div class="mt-3 flex gap-2">
        <button class="btn-danger" data-action="confirm-delete" data-ekey="${esc(key)}">${!hasPlan ? "전표 옮기고 정리" : (n ? "옮기고 삭제" : "삭제")}</button>
        <button class="btn-secondary" data-action="cancel-delete">취소</button>
      </div>
    </div>`;
}

// 검색어 입력 시 결과 영역만 갱신(#detResults) — 입력창을 다시 만들지 않아
// 한글 조합(IME)이 끊기지 않는다.

export function detResultsHtml() {
  const d = state.det;
  const data = d.data;
  let biz = data.biz.map((b, idx) => ({...b, _key: `${b.budget}|${b.예산과목}|${b.사업명}|${idx}`}));
  if (d.budget !== "all") biz = biz.filter(b => b.budget === d.budget);
  if (d.item) biz = biz.filter(b => b.예산과목 === d.item);
  if (d.attr) biz = biz.filter(b => String(b.속성 ?? "") === d.attr);
  if (d.hideMissing) biz = biz.filter(b => b.구분 !== "미시행");
  if (d.q.trim()) { const q = d.q.trim().toLocaleLowerCase("ko"); biz = biz.filter(b => String(b.사업명 ?? "").toLocaleLowerCase("ko").includes(q)); }
  if (d.sortKey) {
    const k = d.sortKey, dir = d.sortDir;
    biz.sort((a, b) => {
      const va = a[k], vb = b[k];
      if (typeof va === "number" || typeof vb === "number")
        return ((va ?? -Infinity) - (vb ?? -Infinity)) * dir;
      return String(va ?? "").localeCompare(String(vb ?? ""), "ko") * dir;
    });
  }
  const tot = biz.reduce((a, b) => { a.plan += b.연예산; a.actual += b.실적;
    a.planWon += b.연예산원; a.actualWon += b.실적원; return a; },
    {plan: 0, actual: 0, planWon: 0, actualWon: 0});
  const selCount = d.sel.size;
  const locked = !!state.status?.locked;

  const rows = biz.map(b => {
    const key = b._key;
    const open = d.open.has(key);
    const editing = d.editKey === key;
    const allSel = b.전표.length > 0 && b.전표.every(v => d.sel.has(v.erp_row_id));
    const vhead = !open || !b.전표.length ? "" : `
      <tr class="voucher-head">
        <td class="table-cell pl-6 text-xs font-bold text-slate-500" colspan="2">
        ${locked ? "예산과목" : `<label class="flex items-center gap-2" title="이 사업의 전표 전체 선택/해제"><input type="checkbox" class="accent-blue-600" data-vall="${esc(key)}" data-vbudget="${esc(b.budget)}" ${allSel ? "checked" : ""}><span>예산과목</span></label>`}</td>
        <td class="table-cell text-xs font-bold text-slate-500">전표번호</td>
        <td class="table-cell text-xs font-bold text-slate-500">전표 텍스트(ERP)</td>
        <td class="table-cell text-right text-xs font-bold text-slate-500">전기일</td>
        <td class="table-cell text-right text-xs font-bold text-slate-500">전표금액(원)</td>
        <td class="table-cell text-right text-xs font-bold text-slate-500" colspan="2">확신도</td>
        <td></td></tr>`;
    const vrows = !open ? "" : vhead + b.전표.map(v => `
      <tr class="voucher-row">
        <td class="table-cell pl-6" colspan="2">
        <label class="flex items-center gap-2">${locked ? "" : `<input type="checkbox" class="accent-blue-600" data-voucher="${v.erp_row_id}" data-vbudget="${esc(b.budget)}" ${d.sel.has(v.erp_row_id) ? "checked" : ""}>`}
        <span class="cell-item text-xs text-slate-600" title="${esc(v.과목 ?? b.예산과목)}">${esc(v.과목 ?? b.예산과목)}</span></label></td>
        <td class="table-cell cell-doc text-xs text-slate-500">${esc(v.전표번호 ?? "-")}</td>
        <td class="table-cell cell-name" title="${esc(v.텍스트 ?? "")}">${esc(v.텍스트 ?? "(텍스트 없음)")}</td>
        <td class="table-cell text-right text-xs text-slate-400">${esc(v.전기일 ?? "")}</td>
        <td class="table-cell text-right font-medium">${fmt(v.금액원)}</td>
        <td class="table-cell text-right" colspan="2">${v.확신도 !== null && v.확신도 !== undefined ? confBadge(v.확신도) : ""}</td>
        <td></td></tr>`).join("")
      + (open && b.전표.length === 0 ? `<tr class="voucher-row"><td class="table-cell pl-10 text-xs text-slate-400" colspan="9">귀속 전표 없음 (미시행)</td></tr>` : "");
    const editRow = !editing ? "" : `
      <tr class="edit-row"><td colspan="9" class="p-4">
        <div class="rounded-xl border border-blue-200 bg-blue-50 p-4">
          <p class="mb-3 text-sm font-bold text-blue-950">사업 내용 수정 <span class="ml-2 text-xs font-medium text-blue-700">빈칸으로 저장하면 해당 값이 지워집니다. 저장 즉시 반영 + 이후 분석에도 유지.</span></p>
          <div class="edit-grid">
            <label class="block"><span class="mb-1.5 block text-xs font-semibold text-blue-700">예산귀속 지사(처.지사)</span>
              <select id="edBranch" class="control w-full">${realBranches().map(x => `<option value="${esc(x)}" ${x === state.det.branch ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></label>
            <label class="block"><span class="mb-1.5 block text-xs font-semibold text-blue-700">예산과목</span>
              <select id="edItem" class="control w-full">${(((state.status || {}).items || {})[b.budget] || [b.예산과목]).map(x => `<option value="${esc(x)}" ${x === b.예산과목 ? "selected" : ""}>${esc(x)}</option>`).join("")}${(((state.status || {}).items || {})[b.budget] || []).includes(b.예산과목) ? "" : `<option value="${esc(b.예산과목)}" selected>${esc(b.예산과목)} (구성에 없음)</option>`}</select></label>
            <label class="block"><span class="mb-1.5 block text-xs font-semibold text-blue-700">사업명</span><input id="edName" class="control w-full" value="${esc(b.사업명)}"></label>
            <label class="block"><span class="mb-1.5 block text-xs font-semibold text-blue-700">속성</span><input id="edAttr" class="control w-full" value="${esc(b.속성 ?? "")}" placeholder="예: 제조/자산/건가"></label>
            <label class="block"><span class="mb-1.5 block text-xs font-semibold text-blue-700">주관부서명</span><input id="edDept" class="control w-full" value="${esc(b.주관부서명 ?? "")}"></label>
            <label class="block"><span class="mb-1.5 block text-xs font-semibold text-blue-700">예산귀속 부서명(부)</span><input id="edPart" class="control w-full" value="${esc(b.부서부 ?? "")}"></label>
            <label class="block"><span class="mb-1.5 block text-xs font-semibold text-blue-700">연예산(A) · 천원</span><input id="edPlan" class="control w-full text-right" value="${b.연예산 ?? ""}" placeholder="천원 단위"></label>
          </div>
          <p class="mt-2 text-xs text-blue-700"><b>예산귀속 지사</b>를 바꾸면 이 사업이 연예산(A)·귀속 전표까지 <b>통째로</b> 그 지사로 이동합니다(삭제·재생성 아님). <b>예산과목</b>은 같은 예산(${esc(b.budget)}) 안에서만 바꿀 수 있고, 전표의 과목은 ERP 계정코드가 정하므로 <b>귀속 전표는 옛 과목에 신규로 남습니다</b>. <b>주관부서명</b>은 표기용 텍스트라 종합표·지사별 집계는 바뀌지 않습니다. <b>연예산</b>을 고치면 원본 계획본은 그대로 두고 이후 모든 분석·종합표·집행률에 그 값이 쓰입니다.</p>
          ${deleteBoxHtml(b, key)}
          <div class="mt-4 flex flex-wrap gap-2">
            <button class="btn-primary" data-action="save-edit" data-ekey="${esc(key)}">저장</button>
            <button class="btn-secondary" data-action="cancel-edit">취소</button>
            <button class="btn-danger-outline push-right" data-action="ask-delete" data-ekey="${esc(key)}">이 사업 삭제</button>
          </div>
        </div>
      </td></tr>`;
    return `
      <tr class="clickable ${b.구분 === "미시행" ? "row-missing" : ""} ${String(b.구분).startsWith("신규") ? "row-new" : ""} ${b.구분 === "미매핑" ? "row-unmapped" : ""} hover:bg-blue-50/40" data-biz="${esc(key)}">
        <td class="table-cell"><span class="badge ${b.budget === "손익" ? "bg-blue-50 text-blue-700" : "bg-emerald-50 text-emerald-700"}">${b.budget}</span></td>
        <td class="table-cell text-slate-700 cell-item" title="${esc(b.예산과목)}">${esc(b.예산과목)}</td>
        <td class="table-cell text-slate-500">${esc(b.속성 ?? "-")}</td>
        <td class="table-cell font-semibold text-slate-900 cell-name" title="${esc(b.사업명)}"><span class="mr-1 inline-block w-3 text-slate-400">${b.전표.length ? (open ? "▾" : "▸") : ""}</span>${esc(b.사업명)}</td>
        <td class="table-cell text-right">${fmt(b.연예산원)}</td>
        <td class="table-cell text-right font-semibold">${fmt(b.실적원)}</td>
        <td class="table-cell text-right">${gubunBadge(b.구분)}</td>
        <td class="table-cell text-right">${b.구분 === "계획집행" ? confBadge(b.확신도) : ""}</td>
        <td class="table-cell text-right">${locked ? "" : `<button class="grid h-6 w-6 place-items-center rounded-lg bg-slate-100 text-slate-600 hover:bg-blue-100 hover:text-blue-700" title="사업 내용 수정" data-edit="${esc(key)}">✎</button>`}</td>
      </tr>${editRow}${vrows}`;
  }).join("");

  // 이동 대상 지사 — 현재 지사가 실제 지사면 그것이 기본값, 미매핑 가상지사면 미선택
  const ovDeptSel = d.ovDept || (realBranches().includes(d.branch) ? d.branch : "");
  // 이동할 사업 목록은 '이동 대상 지사' 기준 — 현재 지사는 화면 데이터, 다른 지사는
  //   ovBiz 캐시(지사 변경 시 불러옴)에서 가져온다. 그래야 타 지사·처의 기존 사업에
  //   바로 붙일 수 있다.
  const ovNames = (() => {
    if (!selCount || !ovDeptSel) return [];
    const src = ovDeptSel === d.branch ? data.biz : state.ovBiz[`${state.year}|${ovDeptSel}`];
    if (!src) return null;                       // null = 아직 안 불러옴
    return [...new Set(src.filter(b => b.budget === d.selBudget).map(b => b.사업명))].sort(
      (a, b) => String(a).localeCompare(String(b), "ko"));
  })();
  const targetOpts = (() => {
    if (!selCount) return "";
    // 첫 항목은 항상 '선택 없음' — 실수로 목록 맨 위 사업에 붙는 것을 막고,
    //   새 사업명을 직접 입력하는 흐름을 기본값으로 둔다.
    return `<option value="" ${d.ovTarget ? "" : "selected"}>— 선택 없음 (직접 입력) —</option>`
      + (ovNames || []).map(n => `<option value="${esc(n)}" ${n === d.ovTarget ? "selected" : ""}>${esc(n)}</option>`).join("");
  })();

  return `
      <section class="grid gap-4 sm:grid-cols-3">
        <article class="metric-card"><p class="text-sm font-semibold text-slate-500">조회 사업</p><p class="mt-3 text-2xl font-bold">${biz.length}건</p></article>
        <article class="metric-card"><p class="text-sm font-semibold text-slate-500">연예산(A)</p><p class="mt-3 text-2xl font-bold">${fmt(tot.plan)} <span class="text-xs font-semibold text-slate-400">천원</span></p></article>
        <article class="metric-card"><p class="text-sm font-semibold text-slate-500">최종 실적금액(B)</p><p class="mt-3 text-2xl font-bold">${fmt(tot.actual)} <span class="text-xs font-semibold text-slate-400">천원</span></p><p class="mt-1 text-xs text-slate-500">집행률 ${fmtRate(tot.plan, tot.actual)}</p></article>
      </section>
      ${selCount && !locked ? `<section class="panel sticky top-16 z-10 mt-6 border-blue-300 bg-blue-50 p-4">
        <div class="flex flex-wrap items-end gap-3">
          <p class="font-bold text-blue-950">${selCount}건 전표 선택 (${esc(d.selBudget)})</p>
          <label class="block"><span class="mb-1.5 block text-xs font-semibold text-blue-700">이동할 지사</span>
            <select id="ovDept" class="control">${ovDeptSel ? "" : '<option value="">— 지사 선택 —</option>'}${realBranches().map(b => `<option value="${esc(b)}" ${b === ovDeptSel ? "selected" : ""}>${esc(b)}</option>`).join("")}</select></label>
          <label class="block min-w-48 flex-1"><span class="mb-1.5 block text-xs font-semibold text-blue-700">이동할 사업 선택 <span class="font-bold">(${esc(ovDeptSel || "지사 미선택")} 기준${ovNames ? ` · ${ovNames.length}건` : ""})</span></span><select id="ovTarget" class="control w-full">${targetOpts}</select></label>
          <label class="block min-w-48 flex-1"><span class="mb-1.5 block text-xs font-semibold text-blue-700">또는 사업명 직접 입력</span><input id="ovManual" class="control w-full" placeholder="입력 시 이 이름이 우선 적용" value="${esc(d.ovManual || "")}"></label>
          <button class="btn-primary" data-action="save-override">재배정 저장 (자동 재분석)</button>
          <button class="btn-secondary" data-action="clear-sel">선택 해제</button>
        </div>
        <p class="mt-2 text-xs text-blue-700">사업 목록은 <b>이동할 지사</b>의 기존 사업입니다 — 그 지사·처에 이미 있는 사업에 붙이려면 목록에서 고르세요. <b>새 사업</b>으로 옮기려면 <b>'— 선택 없음 —'</b> 그대로 두고 사업명을 직접 입력하면 그 지사의 신규 사업으로 귀속됩니다.</p>
        </section>` : ""}
      <section class="panel mt-6 overflow-hidden">
        <div class="border-b border-slate-200 px-4 py-3">${legend()}</div>
        ${biz.length ? `<div class="overflow-x-auto"><table class="det-table w-full"><thead class="table-head"><tr>
          ${DET_COLS.map(([k, label], i) => `<th class="clickable ${i >= 4 && i <= 7 ? "text-right" : ""}" data-detsort="${k}"><span class="th-line">${label} <span>${detSortArrow(k)}</span></span></th>`).join("")}
          <th class="text-right">수정</th></tr></thead>
        <tbody class="divide-y divide-slate-100">${rows}</tbody>
        <tfoot class="border-t-2 border-slate-200 bg-slate-50"><tr><td class="table-cell font-bold" colspan="4">합계 (${biz.length}개 사업, 단위: 원)</td><td class="table-cell text-right font-bold">${fmt(tot.planWon)}</td><td class="table-cell text-right font-bold">${fmt(tot.actualWon)}</td><td colspan="3"></td></tr></tfoot></table></div>` : emptyState("조건에 맞는 사업이 없습니다.")}
      </section>
      <p class="mt-4 text-xs text-slate-400">표의 연예산(A)·실적금액(B)·전표금액은 <b>원 단위</b>, 상단 요약 카드는 <b>천원 단위</b>입니다. 재배정은 저장 즉시 자동 재분석되어 반영되고, 그 확정 내용은 자동으로 학습됩니다.</p>`;
}

// ───────────────────────── 4 통계·내보내기 ─────────────────────────
