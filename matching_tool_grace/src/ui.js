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
    return XLSX.utils.sheet_to_json(wb.Sheets[sn], { header: 1, defval: "" });
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
      ["예산 라인", R.budget.length],
      ["매칭", s.matched],
      ["신규(계획 미반영)", s.shingyu],
      ["실적없음", s.noActual],
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

      const rawRows = await fileToRows(fRaw, null);
      const capRows = $("fCap").files[0] ? await fileToRows($("fCap").files[0], "양식1(월별)") : [];
      const plRows = $("fPl").files[0] ? await fileToRows($("fPl").files[0], "양식1(월별)") : [];

      const R = BUDGET_PIPELINE.runAll(
        { rawRows, capBudgetRows: capRows, plBudgetRows: plRows },
        BUDGET_CONST
      );
      RESULT = R;
      renderStats(R);
      $("resultCard").style.display = "";
      setMsg("완료! 아래에서 결과를 내려받으세요.", "okmsg");
    } catch (e) {
      setMsg("오류: " + (e && e.message ? e.message : e), "err");
      console.error(e);
    } finally {
      $("run").disabled = false;
    }
  });

  document.querySelectorAll("[data-dl]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!RESULT) return;
      const kind = btn.getAttribute("data-dl");
      if (kind === "pl") downloadWb([["종합표", RESULT.jongPl], ["계획대비실적", RESULT.chipPl]], "양식2_손익_실적집계.xlsx");
      else if (kind === "cap") downloadWb([["종합표", RESULT.jongCap], ["계획대비실적", RESULT.chipCap]], "양식3_자본_실적집계.xlsx");
      else if (kind === "review") downloadWb([["지사x과목합계", RESULT.review.pivot], ["정리내역", RESULT.review.items]], "netting검토표.xlsx");
    });
  });
})();
