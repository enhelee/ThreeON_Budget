// 브라우저 UI 글루: 파일 읽기 → runAll → 다운로드
(function () {
  const $ = (id) => document.getElementById(id);
  const msg = $("msg");
  let RESULT = null;

  function setMsg(t, cls) { msg.textContent = t; msg.className = "msg" + (cls ? " " + cls : ""); }

  // ── 보정사전 기억(localStorage): 한 번 올리면 브라우저가 저장 → 다음부터 자동 적용 ──
  const CORR_KEY = "budget_corrections_v1";
  // 저장 크기 줄이기: 헤더 + "올바른사업명"이 채워진 줄만 남김
  function corrFilter(rows) {
    if (!rows || !rows.length) return rows || [];
    let hr = 0;
    for (let i = 0; i < Math.min(rows.length, 6); i++) {
      const h = (rows[i] || []).map((x) => String(x == null ? "" : x));
      if (h.some((v) => v.includes("전표텍스트")) && h.some((v) => v.includes("사업명"))) { hr = i; break; }
    }
    const H = (rows[hr] || []).map((x) => String(x == null ? "" : x));
    let bi = H.findIndex((v) => v.includes("올바른"));
    if (bi < 0) bi = H.findIndex((v) => v.includes("사업명"));
    const kept = [rows[hr]];
    for (let i = hr + 1; i < rows.length; i++) { if (String((rows[i] || [])[bi] == null ? "" : (rows[i] || [])[bi]).trim()) kept.push(rows[i]); }
    return kept;
  }
  function saveCorr(rows) { try { localStorage.setItem(CORR_KEY, JSON.stringify(corrFilter(rows))); } catch (e) {} }
  function loadCorr() { try { const s = localStorage.getItem(CORR_KEY); return s ? JSON.parse(s) : null; } catch (e) { return null; } }
  function updateCorrStatus() {
    const el = $("corrStatus"), btn = $("corrClear");
    const r = loadCorr();
    const n = r ? Math.max(0, r.length - 1) : 0;
    if (el) el.textContent = n ? "✅ 저장된 보정사전 사용 중 (" + n + "건) — 새 파일을 올리면 교체됩니다" : "저장된 보정사전 없음 — 한 번 올리면 기억합니다";
    if (btn) btn.style.display = n ? "" : "none";
  }

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

      const rawRows = await fileToRows(fRaw, null);
      const cap = $("fCap").files[0] ? await chipFileToSheets($("fCap").files[0]) : { chip: [], jong: [] };
      const pl = $("fPl").files[0] ? await chipFileToSheets($("fPl").files[0]) : { chip: [], jong: [] };
      let correctionRows;
      if ($("fCorr") && $("fCorr").files[0]) {
        correctionRows = await fileToRows($("fCorr").files[0], "검토목록");
        saveCorr(correctionRows);          // 업로드하면 브라우저에 저장(기억)
        updateCorrStatus();
      } else {
        correctionRows = loadCorr() || []; // 파일 없으면 저장된 보정 사용
      }

      const R = BUDGET_PIPELINE.runAll(
        {
          rawRows,
          capChipRows: cap.chip, capJongRows: cap.jong,
          plChipRows: pl.chip, plJongRows: pl.jong,
          correctionRows,
        },
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
      else if (kind === "review") downloadWb([["지사x과목합계", RESULT.review.pivot], ["정리내역", RESULT.review.items], ["미배분vendor", RESULT.review.vendors]], "netting검토표.xlsx");
      else if (kind === "checklist") downloadWb([["검토목록(보정사전)", RESULT.checklist]], "검토목록_보정사전.xlsx");
    });
  });

  // 저장된 보정 지우기
  if ($("corrClear")) $("corrClear").addEventListener("click", () => {
    try { localStorage.removeItem(CORR_KEY); } catch (e) {}
    updateCorrStatus();
    setMsg("저장된 보정사전을 지웠어요.", "okmsg");
  });
  updateCorrStatus(); // 페이지 열 때 상태 표시
})();
