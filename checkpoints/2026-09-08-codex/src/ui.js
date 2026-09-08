// 브라우저 UI 글루: 파일 읽기 → runAll → 다운로드
(function () {
  const $ = (id) => document.getElementById(id);
  const msg = $("msg");
  let RESULT = null;

  function setMsg(t, cls) { msg.textContent = t; msg.className = "msg" + (cls ? " " + cls : ""); }

  async function fileToRows(file, preferSheet) {
    const buf = await file.arrayBuffer();
    const wb = XLSX.read(new Uint8Array(buf), { type: "array" });
    let sn = wb.SheetNames[0];
    if (preferSheet) {
      const f = wb.SheetNames.find((s) => s.normalize("NFC").includes(preferSheet));
      if (f) sn = f;
    }
    const ws = wb.Sheets[sn];
    // 병합셀 펼치기: 병합된 텍스트(예: "가스터빈 제어시스템 성능개선")를 병합 범위 전 행에 채움
    for (const m of (ws["!merges"] || [])) {
      const a = ws[XLSX.utils.encode_cell({ r: m.s.r, c: m.s.c })];
      if (!a) continue;
      for (let r = m.s.r; r <= m.e.r; r++) for (let c = m.s.c; c <= m.e.c; c++) {
        const ad = XLSX.utils.encode_cell({ r, c });
        if (!ws[ad]) ws[ad] = { t: a.t, v: a.v };
        else if (String(ws[ad].v == null ? "" : ws[ad].v).trim() === "") ws[ad].v = a.v;
      }
    }
    return XLSX.utils.sheet_to_json(ws, { header: 1, defval: "" });
  }
  // 집계표 파일에서 「계획대비실적」과 「종합표」 두 시트를 각각 AOA로
  async function chipFileToSheets(file) {
    const buf = await file.arrayBuffer();
    const wb = XLSX.read(new Uint8Array(buf), { type: "array" });
    const pick = (kw) => {
      const s = wb.SheetNames.find((n) => n.normalize("NFC").replace(/\s/g, "").includes(kw));
      return s ? XLSX.utils.sheet_to_json(wb.Sheets[s], { header: 1, defval: "" }) : [];
    };
    return { chip: pick("계획대비실적") , jong: pick("종합") };
  }

  function downloadWb(sheets, filename) {
    const wb = XLSX.utils.book_new();
    for (const [n, aoa] of sheets) XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(aoa), n);
    const out = XLSX.write(wb, { type: "array", bookType: "xlsx" });
    const blob = new Blob([out], { type: "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename; document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
  }

  function renderStats(R) {
    const s = R.stats;
    const cards = [
      ["netting 정리 항목", R.cleaned.length],
      ["계획 사업 줄", s.planRows],
      ["실적 채운 줄", s.filled],
      ["계획 미반영(추가줄)", s.unplanned],
    ];
    $("stats").innerHTML = cards.map(([k, n]) =>
      `<div class="stat"><div class="n">${n.toLocaleString()}</div><div class="k">${k}</div></div>`
    ).join("");
  }

  $("run").addEventListener("click", async () => {
    try {
      const fRaw = $("fRaw").files[0];
      if (!fRaw) { setMsg("ERP raw data 파일을 올려주세요.", "err"); return; }
      $("run").disabled = true;
      setMsg("처리 중… (파일이 크면 수십 초 걸릴 수 있어요)");

      const privateFile = $("fPrivate").files[0];
      const privateData = privateFile ? JSON.parse(await privateFile.text()) : { cases: [] };
      if (!Array.isArray(privateData.cases) || privateData.cases.some(c =>
          !c || typeof c.org !== 'string' || typeof c.acct !== 'string' ||
          !Array.isArray(c.targets) || !c.targets.every(t => typeof t === 'string') ||
          !Array.isArray(c.texts) || !c.texts.every(t => t && typeof t.text === 'string'))) {
        throw new Error('보정 JSON의 cases/지사/과목/사업명/텍스트 형식을 확인하세요.');
      }
      BUDGET_CORRECTIONS.cases = privateData.cases;
      const rawRows = await fileToRows(fRaw, null);
      const cap = $("fCap").files[0] ? await chipFileToSheets($("fCap").files[0]) : { chip: [], jong: [] };
      const pl = $("fPl").files[0] ? await chipFileToSheets($("fPl").files[0]) : { chip: [], jong: [] };
      const correctionRows = $("fCorr") && $("fCorr").files[0] ? await fileToRows($("fCorr").files[0], "검토목록") : [];

      const R = BUDGET_PIPELINE.runAll(
        {
          rawRows,
          capChipRows: cap.chip, capJongRows: cap.jong,
          plChipRows: pl.chip, plJongRows: pl.jong,
          correctionRows,
          matchFinalActual: $("matchFinalActual").checked,
          builtinCorrections: $("builtinCorrections").checked,
        },
        BUDGET_CONST
      );
      RESULT = R;
      renderStats(R);
      $("resultCard").style.display = "";
      setMsg(R.amountMatching ? "최종 실적금액 대조 완료. 금액 일치·묶음 내역과 남은 검토목록을 확인하세요." : "완료! 아래에서 결과를 내려받으세요.", "okmsg");
    } catch (e) {
      setMsg("오류: " + (e && e.message ? e.message : e), "err");
      console.error(e);
    } finally {
      $("run").disabled = false;
    }
  });

  $("exportJson").addEventListener("click", () => {
    if (!RESULT) return;
    const data = {schemaVersion: 1, amountUnit: 'KRW_THOUSAND',
      amountMatching: RESULT.amountMatching, reconciliation: RESULT.reconciliation};
    const url = URL.createObjectURL(new Blob([JSON.stringify(data)], {type: 'application/json'}));
    const a = document.createElement('a'); a.href = url; a.download = 'checkpoint-result.json';
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  });
  document.querySelectorAll("[data-dl]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!RESULT) return;
      const kind = btn.getAttribute("data-dl");
      if (kind === "pl") downloadWb([["종합표", RESULT.jongPl], ["계획대비실적", RESULT.chipPl]], "양식2_손익_실적집계.xlsx");
      else if (kind === "cap") downloadWb([["종합표", RESULT.jongCap], ["계획대비실적", RESULT.chipCap]], "양식3_자본_실적집계.xlsx");
      else if (kind === "amount") downloadWb([["금액일치묶음", RESULT.reconciliation.groups], ["묶음배분", RESULT.reconciliation.details], ["대응전표미확정", RESULT.reconciliation.differences]], "금액일치_묶음내역.xlsx");
      else if (kind === "spares") downloadWb([["예비품전기일", RESULT.reconciliation.spareDates], ["원천전표", RESULT.reconciliation.spareSources]], "예비품_전기일별_합산.xlsx");
      else if (kind === "corrections") downloadWb([["보정반영내역", RESULT.reconciliation.corrections], ["제외내역", RESULT.reconciliation.exclusions]], "보정반영_제외내역.xlsx");
      else if (kind === "review") downloadWb([["지사x과목합계", RESULT.review.pivot], ["정리내역", RESULT.review.items], ["미배분vendor", RESULT.review.vendors]], "netting검토표.xlsx");
      else if (kind === "checklist") downloadWb([["검토목록(보정사전)", RESULT.checklist]], "검토목록_보정사전.xlsx");
    });
  });
})();
