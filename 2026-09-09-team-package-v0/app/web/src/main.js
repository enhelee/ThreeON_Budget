import "./styles/app.css"
// 손으로 쓴 스타일 — 원본과 동일하게 Tailwind 유틸리티 뒤에 와야 한다
import "./styles/custom.css"
import { api, checkAuth, doLogin } from "./api.js"
import { busy, toast } from "./components/feedback.js"
import { afterSave, loadDetail, loadOvBiz } from "./data.js"
import { addYearFromInput, changeYear, navigate, renderPage, runAnalyze, uploadFile } from "./router.js"
import { state } from "./state.js"
import { $, fmt } from "./util.js"
import { brResultsHtml } from "./views/branches.js"
import { detResultsHtml, unassignedName } from "./views/detail.js"

// ───────────────────────── 상태 ─────────────────────────

document.addEventListener("click", async e => {
  const nav = e.target.closest("nav [data-view], [data-view].btn-secondary, button[data-view]");
  if (nav && nav.dataset.view) { navigate(nav.dataset.view); return; }
  const gy = e.target.closest("[data-goyear]");
  if (gy) { changeYear(gy.dataset.goyear); return; }
  const br = e.target.closest("[data-branch]");
  if (br) {
    busy(true, "지사 상세 로딩...");
    try { await loadDetail(br.dataset.branch); state.view = "detail"; renderPage(); }
    catch (err) { toast(err.message); }
    finally { busy(false); }
    return;
  }
  const th = e.target.closest("[data-detsort]");
  if (th) {
    const k = th.dataset.detsort;
    if (state.det.sortKey === k) {
      if (state.det.sortDir === 1) state.det.sortDir = -1;
      else { state.det.sortKey = ""; state.det.sortDir = 1; }   // 3번째 클릭=기본 정렬
    } else { state.det.sortKey = k; state.det.sortDir = 1; }
    renderPage();
    return;
  }
  const ed = e.target.closest("[data-edit]");
  if (ed) {
    state.det.editKey = state.det.editKey === ed.dataset.edit ? null : ed.dataset.edit;
    renderPage();
    return;
  }
  const biz = e.target.closest("[data-biz]");
  if (biz && !e.target.closest("input") && !e.target.closest("button")) {
    const k = biz.dataset.biz;
    state.det.open.has(k) ? state.det.open.delete(k) : state.det.open.add(k);
    renderPage();
    return;
  }
  const act = e.target.closest("[data-action]")?.dataset.action;
  if (act === "analyze") runAnalyze();
  if (act === "logout") { await fetch("/api/logout", {method: "POST"}); location.reload(); return; }
  if (act === "reload-audit") { await navigate("settings"); return; }
  if (act === "train") {
    const name = e.target.closest("[data-action]").dataset.name;
    if (!confirm(`${name} 모델을 지금 재학습할까요?\n활성 학습데이터로 새 버전을 만들고 그 버전을 활성화합니다(이전 버전은 보관·롤백 가능).`)) return;
    try {
      toast("재학습 중… 표본 수에 따라 수 초~수십 초 걸립니다.");
      const r = await api("/api/train", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name})});
      toast(`재학습 완료 — v${r.version} · 표본 ${r.n_samples}건 · CV정확도 ${r.metrics?.cv_accuracy ?? "-"}`);
      await navigate("settings");
    } catch (err) { toast(err.message); }
    return;
  }
  if (act === "activate-model") {
    const id = e.target.closest("[data-action]").dataset.id;
    try { await api(`/api/models/${id}/activate`, {method: "POST"}); toast("활성 버전을 바꿨습니다."); await navigate("settings"); }
    catch (err) { toast(err.message); }
    return;
  }
  if (act === "pick-training") { state.trainingName = e.target.closest("[data-action]").dataset.name; $("#trainingFile").click(); return; }
  if (act === "add-year") addYearFromInput(e.target.closest("[data-action]").dataset.input);
  if (act === "pick-plan") $("#planFile").click();
  if (act === "pick-erp") $("#erpFile").click();
  if (act === "pick-master-item") $("#masterItemFile").click();
  if (act === "pick-master-dept") $("#masterDeptFile").click();
  if (act === "clear-sel") {
    state.det.sel.clear(); state.det.selBudget = null;
    state.det.ovDept = ""; state.det.ovTarget = ""; state.det.ovManual = "";
    renderPage();
  }
  if (act === "cancel-edit") { state.det.editKey = null; state.det.delKey = null; renderPage(); }
  if (act === "toggle-add") { state.det.addOpen = !state.det.addOpen; renderPage(); }
  if (act === "save-add") {
    const name = $("#abName").value.trim();
    if (!name) { toast("사업명을 입력하세요."); return; }
    const body = {
      year: state.year, budget: $("#abBudget").value,
      예산과목: $("#abItem").value, 처지사: state.det.branch, 사업명: name,
      속성: $("#abAttr").value || null,
      주관부서명: $("#abOwner").value.trim() || null,
      부서부: $("#abPart").value.trim() || null,
      연예산: Number($("#abPlan").value) || 0,
    };
    busy(true, "사업 추가 저장 중...");
    try {
      await api("/api/manual-biz", {method: "POST",
        headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
      state.det.addOpen = false;
    } catch (err) { toast(err.message); busy(false); return; }
    finally { busy(false); }
    await afterSave(`사업 추가 저장 — "${name}"`);
  }
  if (act === "save-edit") {
    const key = e.target.closest("[data-action]").dataset.ekey;
    const b = state.det.data.biz.map((x, idx) => ({...x, _key: `${x.budget}|${x.예산과목}|${x.사업명}|${idx}`}))
      .find(x => x._key === key);
    if (!b) return;
    const planIn = $("#edPlan") ? $("#edPlan").value.replace(/,/g, "").trim() : "";
    if (planIn !== "" && isNaN(Number(planIn))) { toast("연예산은 숫자(천원)로 입력하세요."); return; }
    const fields = {
      "사업명": $("#edName").value.trim(),
      "속성": $("#edAttr").value.trim(),
      "주관부서명": $("#edDept").value.trim(),
      "부서부": $("#edPart").value.trim(),
    };
    if (!fields["사업명"]) { toast("사업명은 비울 수 없습니다."); return; }
    const planChanged = planIn !== String(b.연예산 ?? "");
    if (planChanged) fields["연예산"] = planIn;      // 안 바꿨으면 보내지 않는다
    // 예산과목 변경 — 전표 과목은 ERP 계정코드가 정하므로 귀속 전표는 옛 과목에 남는다.
    const newItem = $("#edItem") ? $("#edItem").value : b.예산과목;
    const itemChanged = !!newItem && newItem !== b.예산과목;
    if (itemChanged) {
      const n = (b.전표 || []).length;
      const warn = n ? `\n\n귀속 전표 ${n}건(${fmt(b.실적원)}원)은 ERP 계정코드가 "${b.예산과목}"이라 그 과목에 신규 사업으로 남습니다. 총액은 보존됩니다.` : "";
      if (!confirm(`예산과목을 바꿉니다.\n${b.예산과목} → ${newItem}${warn}\n\n계속할까요?`)) return;
      fields["예산과목"] = newItem;
    }
    // 예산귀속 지사 변경 = 사업 통째 이동(계획행=biz_edit.처지사, 전표=override.target_dept)
    const from = state.det.branch;
    const to = $("#edBranch") ? $("#edBranch").value : from;
    const moving = !!to && to !== from;
    const vouchers = (b.전표 || []).map(v => v.erp_row_id);
    const hasPlan = !String(b.구분 ?? "").startsWith("신규") && b.구분 !== "미매핑";
    // 내용이 실제로 바뀐 게 없으면 이력을 남기지 않는다(신규 사업 이동 등).
    const edited = planChanged || itemChanged
      || fields["사업명"] !== b.사업명
      || fields["속성"] !== String(b.속성 ?? "")
      || fields["주관부서명"] !== String(b.주관부서명 ?? "")
      || fields["부서부"] !== String(b.부서부 ?? "");
    if (moving) {
      const parts = [`연예산 ${fmt(b.연예산원)}원`, `전표 ${vouchers.length}건`];
      if (!confirm(`"${fields["사업명"]}" 사업을 ${from} → ${to}(으)로 통째 이동합니다.\n(${parts.join(" + ")})\n\n계속할까요?`)) return;
      if (hasPlan) fields["처지사"] = to;      // 계획행(연예산)도 함께 이동
    } else if (!edited) { state.det.editKey = null; renderPage(); return; }
    busy(true, moving ? "사업 이동 저장 중..." : "사업 내용 저장 중...");
    try {
      if (edited || "처지사" in fields) {
        await api("/api/biz-edit", {method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({year: state.year, budget: b.budget, 예산과목: b.예산과목,
                                처지사: from, 사업명: b.사업명, fields})});
      }
      if (moving && vouchers.length) {
        await api("/api/override", {method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({year: state.year, budget: b.budget, erp_row_ids: vouchers,
                                target_name: fields["사업명"], target_dept: to,
                                memo: `사업 통째 이동 ${from}→${to}`})});
      }
      state.det.editKey = null;
      state.det.sel.clear(); state.det.selBudget = null;
    } catch (err) { toast(err.message); busy(false); return; }
    finally { busy(false); }
    // 분석은 하지 않는다 — 화면은 즉시 패치분으로 갱신되고, 확정은 '분석 반영'에서.
    await afterSave(moving ? `이동 저장 — "${fields["사업명"]}" → ${to}`
                           : `저장 — "${fields["사업명"]}"`);
  }
  if (act === "ask-delete") {
    state.det.delKey = e.target.closest("[data-action]").dataset.ekey;
    renderPage();
  }
  if (act === "cancel-delete") { state.det.delKey = null; renderPage(); }
  if (act === "confirm-delete") {
    const key = e.target.closest("[data-action]").dataset.ekey;
    const b = state.det.data.biz.map((x, idx) => ({...x, _key: `${x.budget}|${x.예산과목}|${x.사업명}|${idx}`}))
      .find(x => x._key === key);
    if (!b) return;
    const vouchers = (b.전표 || []).map(v => v.erp_row_id);
    // 계획행이 없는 행(신규·미매핑)은 '그 전표들의 집합'일 뿐이다 — 전표를 옮기면 사라진다.
    //   여기에 삭제 기록(이름 기준)을 남기면 같은 이름의 계획행까지 지워지므로 남기지 않는다.
    const hasPlan = !String(b.구분 ?? "").startsWith("신규") && b.구분 !== "미매핑";
    let moveTo = null;
    if (vouchers.length) {
      const pick = $("#delTarget") ? $("#delTarget").value : "";
      if (!pick) { toast("전표를 옮길 사업을 선택하세요."); return; }
      moveTo = pick === "__unassigned__" ? unassignedName(b) : pick;
      if (hasPlan && moveTo === b.사업명) { toast("같은 이름의 사업으로는 옮길 수 없습니다."); return; }
      const tail = hasPlan ? `\n그 뒤 "${b.사업명}" 사업을 삭제합니다.` : "";
      if (!confirm(`귀속 전표 ${vouchers.length}건(${fmt(b.실적원)}원)을 "${moveTo}"(으)로 옮깁니다.${tail}\n\n계속할까요?`)) return;
    } else if (!confirm(`"${b.사업명}" 사업을 삭제합니다. (연예산 ${fmt(b.연예산)}천원, 귀속 전표 없음)\n설정 탭 이력에서 되돌릴 수 있습니다.\n\n계속할까요?`)) {
      return;
    }
    busy(true, hasPlan ? "사업 삭제 중..." : "전표 이동 중...");
    try {
      if (moveTo) {
        await api("/api/override", {method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({year: state.year, budget: b.budget, erp_row_ids: vouchers,
                                target_name: moveTo, target_dept: state.det.branch,
                                memo: `사업 정리에 따른 전표 이동 (${b.사업명} → ${moveTo})`})});
      }
      if (hasPlan) {
        await api("/api/biz-delete", {method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({year: state.year, budget: b.budget, 예산과목: b.예산과목,
                                처지사: state.det.branch, 사업명: b.사업명,
                                memo: moveTo ? `전표 ${vouchers.length}건 → ${moveTo}` : null})});
      }
      state.det.delKey = null; state.det.editKey = null;
      state.det.sel.clear(); state.det.selBudget = null;
    } catch (err) { toast(err.message); busy(false); return; }
    finally { busy(false); }
    await afterSave((hasPlan ? `삭제 저장 — "${b.사업명}"` : `정리 저장 — "${b.사업명}"`)
                    + (moveTo ? ` (전표 ${vouchers.length}건 → ${moveTo})` : ""));
  }
  if (act === "save-override") {
    const manual = $("#ovManual").value.trim();
    const target = manual || $("#ovTarget").value;
    if (!target) { toast("이동할 사업을 목록에서 고르거나, 새 사업명을 직접 입력하세요."); return; }
    const destDept = $("#ovDept") ? $("#ovDept").value : "";
    const isUnmapped = !!state.det.data?.unmapped;
    if (!destDept) { toast("이동할 지사를 선택하세요."); return; }
    // 미매핑 전표는 항상 지사 지정, 일반 전표는 지사가 바뀐 경우만 지정
    const targetDept = (isUnmapped || destDept !== state.det.branch) ? destDept : null;
    const cnt = state.det.sel.size;          // 선택을 비우기 전에 세어둔다
    const movedDept = targetDept && targetDept !== state.det.branch ? targetDept : null;
    busy(true, "재배정 저장 중...");
    try {
      await api("/api/override", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({year: state.year, budget: state.det.selBudget,
                              erp_row_ids: [...state.det.sel], target_name: target,
                              target_dept: targetDept})});
      state.det.sel.clear(); state.det.selBudget = null;
      state.det.ovDept = ""; state.det.ovTarget = ""; state.det.ovManual = "";
    } catch (err) { toast(err.message); busy(false); return; }
    finally { busy(false); }
    // 분석은 하지 않는다 — 여러 건 모아서 상단 '분석 반영'으로 한 번에.
    await afterSave(`재배정 저장 — 전표 ${cnt}건 → "${target}"`
                    + (movedDept ? ` (${movedDept})` : ""));
  }
  if (act === "learn") {
    busy(true, `${state.year}년 확정 결과를 학습 중...`);
    try {
      const r = await api("/api/learn", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({year: state.year})});
      toast(`${r.notice} (사람확정 ${r.learned["수동확정"]}건 · 자동 ${r.learned["자동확정"]}건)`);
      await navigate("settings");
    } catch (err) { toast(err.message); }
    finally { busy(false); }
  }
  if (act === "lock-year") {
    if (!confirm(`${state.year}년을 마감(잠금)할까요? 업로드·분석·재배정·수정이 차단됩니다.`)) return;
    try {
      const r = await api("/api/lock", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({year: state.year})});
      toast(r.notice);
      await navigate("settings");
    } catch (err) { toast(err.message); }
  }
  if (act === "unlock-year") {
    if (!confirm(`${state.year}년 잠금을 해제할까요? 데이터 변경이 다시 가능해집니다.`)) return;
    try {
      await api(`/api/lock/${state.year}`, {method: "DELETE"});
      toast(`${state.year}년 잠금 해제됨`);
      await navigate("settings");
    } catch (err) { toast(err.message); }
  }
  if (act === "clear-learned") {
    if (!confirm("학습 DB를 모두 지울까요? 다음 분석부터 학습이 적용되지 않습니다.")) return;
    try { await api("/api/learned", {method: "DELETE"}); toast("학습 초기화 완료"); await navigate("settings"); }
    catch (err) { toast(err.message); }
  }
  const exp = e.target.closest("[data-export]");
  if (exp) {
    // 산출물 파일은 분석 때 만들지 않는다(그래야 수정이 빠름) → 첫 다운로드에서 생성.
    toast("내보내기 준비 중… 분석 후 첫 다운로드는 파일 생성으로 30초쯤 걸립니다. 잠시 기다려 주세요.");
    window.location.href = `/api/export?year=${state.year}&budget=${exp.dataset.budget}&kind=${exp.dataset.export}`;
  }
  const texp = e.target.closest("[data-team-export]");
  if (texp) {
    // 손익·자본 두 분석을 한 번에 담는 팀 연계 파일 — 어느 한쪽이 최신 파일보다 새로우면 서버가 재생성.
    toast("팀 연계 파일 준비 중… 손익·자본 분석을 다시 읽어 만듭니다(첫 다운로드 30초쯤). 잠시 기다려 주세요.");
    window.location.href = `/api/export-team?year=${state.year}&kind=${texp.dataset.teamExport}`;
  }
  const delOv = e.target.closest("[data-del-override]");
  if (delOv) {
    try {
      await api(`/api/override/${delOv.dataset.delOverride}`, {method: "DELETE"});
      toast("재배정 삭제됨 — 다음 분석 실행부터 반영됩니다.");
      await navigate("settings");
    } catch (err) { toast(err.message); }
  }
  const delMb = e.target.closest("[data-del-manual]");
  if (delMb) {
    try {
      await api(`/api/manual-biz/${delMb.dataset.delManual}`, {method: "DELETE"});
      toast("수동 추가 사업 삭제됨 — 다음 분석 실행부터 제외됩니다.");
      await navigate("settings");
    } catch (err) { toast(err.message); }
  }
  const delEd = e.target.closest("[data-del-edit]");
  if (delEd) {
    try {
      await api(`/api/biz-edit/${delEd.dataset.delEdit}`, {method: "DELETE"});
      toast("수정 이력 삭제됨 — 다음 분석 실행부터 원본으로 복원됩니다.");
      await navigate("settings");
    } catch (err) { toast(err.message); }
  }
  const restore = e.target.closest("[data-restore-del]");
  if (restore) {
    try {
      await api(`/api/biz-delete/${restore.dataset.restoreDel}`, {method: "DELETE"});
      toast("되돌렸습니다 — 다음 분석 실행부터 그 사업이 다시 살아납니다.");
      await navigate("settings");
    } catch (err) { toast(err.message); }
  }
});

document.addEventListener("change", async e => {
  if (e.target.id === "yearSelect" || e.target.dataset.yearpick) { changeYear(e.target.value); return; }
  if (e.target.id === "planFile" && e.target.files[0]) { uploadFile("plan", e.target.files[0]); e.target.value = ""; return; }
  if (e.target.id === "erpFile" && e.target.files[0]) { uploadFile("erp", e.target.files[0]); e.target.value = ""; return; }
  if ((e.target.id === "masterItemFile" || e.target.id === "masterDeptFile") && e.target.files[0]) {
    const kind = e.target.id === "masterItemFile" ? "item" : "dept";
    const file = e.target.files[0];
    e.target.value = "";
    busy(true, "마스터 갱신 중...");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await api(`/api/upload/master?kind=${kind}`, {method: "POST", body: fd});
      toast(r.notice);
      await navigate("settings");
    } catch (err) { toast(err.message); }
    finally { busy(false); }
    return;
  }
  // 재배정 바 입력 보존 — 전표를 하나 더 체크해도 고른 지사·사업이 풀리지 않게
  //   상태에 담아둔다(재렌더 없음).
  if (e.target.id === "ovDept") {
    const dept = e.target.value;
    state.det.ovDept = dept;
    state.det.ovTarget = "";                 // 지사가 바뀌면 사업 선택은 초기화
    if (dept && dept !== state.det.branch && !state.ovBiz[`${state.year}|${dept}`]) {
      busy(true, `${dept} 사업 목록 조회 중...`);
      try { await loadOvBiz(dept); } catch (err) { toast(err.message); }
      finally { busy(false); }
    }
    renderPage();
    return;
  }
  if (e.target.id === "ovTarget") { state.det.ovTarget = e.target.value; return; }
  const f = e.target.dataset.filter;
  if (f === "type") { state.type = e.target.value; renderPage(); }
  if (f === "sort") { state.sort = e.target.value; renderPage(); }
  const chk = e.target.dataset.detCheck;
  if (chk === "hideMissing") { state.det.hideMissing = e.target.checked; renderPage(); return; }
  const det = e.target.dataset.det;
  if (det === "branch" && e.target.value) {
    busy(true, "지사 상세 로딩...");
    try { await loadDetail(e.target.value); } catch (err) { toast(err.message); }
    finally { busy(false); }
    renderPage(); return;
  }
  if (det === "budget") { state.det.budget = e.target.value; renderPage(); }
  if (det === "item") { state.det.item = e.target.value; renderPage(); }
  if (det === "attr") { state.det.attr = e.target.value; renderPage(); }
  if (e.target.dataset.addBudget) {
    state.det.add = {budget: e.target.value};
    renderPage();
    return;
  }
  // 사업행 헤더 체크박스 = 그 사업의 전표 전체 선택/해제(라벨 글자는 '예산과목'만)
  const vall = e.target.dataset.vall;
  if (vall) {
    const b = state.det.data.biz.map((x, idx) => ({...x, _key: `${x.budget}|${x.예산과목}|${x.사업명}|${idx}`}))
      .find(x => x._key === vall);
    if (!b) return;
    const vb = e.target.dataset.vbudget;
    if (e.target.checked) {
      if (state.det.selBudget && state.det.selBudget !== vb) {
        toast("손익과 자본 전표는 함께 재배정할 수 없습니다.");
        e.target.checked = false;
        return;
      }
      state.det.selBudget = vb;
      b.전표.forEach(x => state.det.sel.add(x.erp_row_id));
    } else {
      b.전표.forEach(x => state.det.sel.delete(x.erp_row_id));
      if (!state.det.sel.size) state.det.selBudget = null;
    }
    renderPage();
    return;
  }
  const v = e.target.dataset.voucher;
  if (v) {
    const id = Number(v);
    if (e.target.checked) {
      const vb = e.target.dataset.vbudget;
      if (state.det.selBudget && state.det.selBudget !== vb) {
        toast("손익과 자본 전표는 함께 재배정할 수 없습니다.");
        e.target.checked = false;
        return;
      }
      state.det.selBudget = vb;
      state.det.sel.add(id);
    } else {
      state.det.sel.delete(id);
      if (!state.det.sel.size) state.det.selBudget = null;
    }
    renderPage();
  }
});

// 검색 입력: 결과 영역만 부분 갱신 — 입력창 DOM을 유지해 한글 조합(IME)이
// 끊기지 않는다(전체 재렌더 금지).

document.addEventListener("input", e => {
  // 직접 입력한 사업명도 재렌더에 견디게 상태로 보관(입력창 DOM은 그대로 → IME 안전)
  if (e.target.id === "ovManual") { state.det.ovManual = e.target.value; return; }
  const f = e.target.dataset.filter;
  const det = e.target.dataset.det;
  if (f === "search") {
    state.search = e.target.value;
    const el = $("#brResults");
    if (el) el.innerHTML = brResultsHtml();
    return;
  }
  if (det === "q") {
    state.det.q = e.target.value;
    const el = $("#detResults");
    if (el) el.innerHTML = detResultsHtml();
  }
});

export function openMenu() { $("#sidebar").classList.remove("-translate-x-full"); $("#backdrop").classList.remove("hidden"); }

export function closeMenu() { if (window.innerWidth >= 1024) return; $("#sidebar").classList.add("-translate-x-full"); $("#backdrop").classList.add("hidden"); }

$("#menuButton").addEventListener("click", openMenu);

$("#backdrop").addEventListener("click", closeMenu);

$("#addYearBtn").addEventListener("click", () => addYearFromInput(null));

$("#loginForm").addEventListener("submit", e => { e.preventDefault(); doLogin(); });

$("#trainingFile").addEventListener("change", async e => {
  const f = e.target.files[0];
  if (!f) return;
  const fd = new FormData(); fd.append("file", f);
  try {
    const r = await api(`/api/training/import?name=${encodeURIComponent(state.trainingName)}`, {method: "POST", body: fd});
    toast(`학습 CSV 가져오기 — 추가 ${r.inserted} · 갱신 ${r.updated} · 건너뜀 ${r.skipped}`);
    await navigate("settings");
  } catch (err) { toast(err.message); }
  e.target.value = "";
});

checkAuth().then(ok => { if (ok) navigate("home"); }).catch(() => navigate("home"));
