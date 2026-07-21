// 예산 실적 자동 집계 — 핵심 파이프라인 (2025년 기준)
// 순수 로직. SheetJS로 파싱한 행 배열을 받아 처리. node/브라우저 공용(UMD).
(function (root, factory) {
  if (typeof module === "object" && module.exports)
    module.exports = factory(require("./constants.js"));
  else root.BUDGET_PIPELINE = factory(root.BUDGET_CONST);
})(typeof self !== "undefined" ? self : this, function (C) {
  const nfc = (s) => (typeof s === "string" ? s.normalize("NFC") : s);

  // 텍스트 정규화: 공백/괄호 정도 무시하고 완전일치 판정용 키
  function textKey(t) {
    return (t == null ? "" : String(t))
      .normalize("NFC")
      .replace(/[\s()\[\]（）]/g, "")
      .trim();
  }

  // ── [1] raw 파싱 ─────────────────────────────────────────
  // rows: SheetJS sheet_to_json(header:1) 결과 (2차원 배열). 헤더 1줄 가정.
  // 열: A자금텍스트 B약정항목 C약정항목텍스트 D기간 E전기일 F참조전표 G금액
  //     H텍스트 I이름 J이름 K코스트센터 L손익센터 M내역 N오더 O공급업체 P자금관리센터
  function parseRaw(rows) {
    const out = [];
    for (let i = 1; i < rows.length; i++) {
      const r = rows[i];
      const acct = String(r[1] == null ? "" : r[1]).trim();
      if (!acct) continue; // 합계행 등 약정항목 빈 행 제거
      const amount = Number(r[6]) || 0;
      out.push({
        fund: nfc(r[0]),
        acct,
        acctName: nfc(r[2]),
        date: r[4],
        docNo: String(r[5] == null ? "" : r[5]).trim(),
        amount,
        text: nfc(r[7] == null ? "" : String(r[7])).trim(),
        nameI: nfc(r[8]),
        mgmtCenter: String(r[15] == null ? "" : r[15]).trim(), // P열 = 지사 키
        bucket: C.bucketOf(acct),
        ledger: C.ledgerOf(acct),
      });
    }
    return out;
  }

  // ── [2] netting: (지사 × 과목) 그룹 안에서만 상계·통합 ────
  // 반환: 정리된 실적 항목 [{dept, acct, acctName, ledger, bucket, text, amount, docNos:[], n}]
  function nettingGroup(items) {
    // Step A: 같은 참조전표번호끼리 합산 (1순위 합0제거 / 3순위 합+통합)
    const byDoc = new Map();
    const noDoc = []; // 전표번호 없는 건 개별 취급
    for (const it of items) {
      if (it.docNo) {
        if (!byDoc.has(it.docNo)) byDoc.set(it.docNo, []);
        byDoc.get(it.docNo).push(it);
      } else noDoc.push(it);
    }
    let stage = [];
    const repText = (arr) => {
      let best = arr[0];
      for (const x of arr) if (Math.abs(x.amount) > Math.abs(best.amount)) best = x;
      return best.text;
    };
    for (const [docNo, arr] of byDoc) {
      const net = arr.reduce((s, x) => s + x.amount, 0);
      if (net === 0) continue; // 1순위: 합0 → 제거
      stage.push({ text: repText(arr), amount: net, docNos: [docNo], n: arr.length });
    }
    for (const it of noDoc) stage.push({ text: it.text, amount: it.amount, docNos: [], n: 1 });

    // Step B: 텍스트 완전일치끼리 합이 0이면 제거 (2순위). 0 아니면 그대로 둠(4순위 미사용)
    const byText = new Map();
    for (const s of stage) {
      const k = textKey(s.text);
      if (!byText.has(k)) byText.set(k, []);
      byText.get(k).push(s);
    }
    const result = [];
    for (const [, arr] of byText) {
      const net = arr.reduce((s, x) => s + x.amount, 0);
      if (net === 0) continue; // 2순위: 합0 → 제거
      for (const s of arr) result.push(s); // 나머지는 개별 유지
    }
    return result;
  }

  // 전체 netting: dept(자금관리센터) × acct 로 그룹핑 후 nettingGroup 적용
  // 경상정비는 예외: 지사(dept)별로 전부 하나로 합산
  function netting(rawItems) {
    const groups = new Map(); // key: dept||acct
    for (const it of rawItems) {
      const k = it.mgmtCenter + "" + it.acct;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(it);
    }
    const cleaned = [];
    for (const [k, items] of groups) {
      const [dept, acct] = k.split("");
      const meta = {
        dept, acct, acctName: items[0].acctName,
        ledger: items[0].ledger, bucket: items[0].bucket,
        deptName: items[0].nameI,
      };
      if (meta.bucket === "gyeongsang") {
        // 경상정비: 전표수·전기일·사업명 무관 지사별 1건 합산
        const total = items.reduce((s, x) => s + x.amount, 0);
        cleaned.push({ ...meta, text: "경상정비 통합", amount: total, docNos: [], n: items.length });
        continue;
      }
      let netted = nettingGroup(items);
      // 열원보완및개선: 빈 텍스트 처리
      if (meta.bucket === "boan") {
        netted = netted.map((x) => {
          if (textKey(x.text) === "") {
            const startsWith6 = x.docNos.some((d) => d[0] === "6");
            return { ...x, text: startsWith6 ? "저장품 대체" : "예비품 대체" };
          }
          return x;
        });
      }
      for (const x of netted) cleaned.push({ ...meta, ...x });
    }
    return cleaned;
  }

  // ── netting 결과 → 검토용 시트 데이터(AOA) ──────────────
  // C: constants (지사 매핑용). 반환: {items:[[...]], pivot:[[...]]}
  function buildReviewSheets(cleaned, C) {
    const deptName = (d) => C.resolveDept(d) || "(지사아님)";
    const chp = (d) => {
      const nm = C.resolveDept(d);
      return nm && C.CHP_GROUP[nm] ? C.CHP_GROUP[nm] : "";
    };
    // 정렬: 자본/손익 → 지사 → 과목 → 금액 desc
    const sorted = [...cleaned].sort((a, b) =>
      (a.ledger).localeCompare(b.ledger) ||
      String(a.dept).localeCompare(String(b.dept)) ||
      String(a.acct).localeCompare(String(b.acct)) ||
      b.amount - a.amount
    );
    const items = [[
      "자본/손익", "사업군", "지사", "자금관리센터", "예산과목코드", "예산과목",
      "버킷", "대표텍스트(사업명)", "실적금액", "관련전표수",
    ]];
    for (const x of sorted) {
      items.push([
        x.ledger, chp(x.dept), deptName(x.dept), x.dept,
        x.acct, x.acctName, x.bucket, x.text, x.amount, x.n,
      ]);
    }
    // 피벗: (지사 × 과목) 합계
    const pivMap = new Map();
    for (const x of cleaned) {
      const k = x.dept + "" + x.acct;
      if (!pivMap.has(k))
        pivMap.set(k, { ledger: x.ledger, dept: x.dept, acct: x.acct, acctName: x.acctName, sum: 0, cnt: 0 });
      const p = pivMap.get(k);
      p.sum += x.amount; p.cnt++;
    }
    const pivot = [["자본/손익", "사업군", "지사", "자금관리센터", "예산과목코드", "예산과목", "실적합계", "정리항목수"]];
    for (const p of [...pivMap.values()].sort((a, b) =>
      a.ledger.localeCompare(b.ledger) || String(a.dept).localeCompare(String(b.dept)) || String(a.acct).localeCompare(String(b.acct))
    )) {
      pivot.push([p.ledger, chp(p.dept), deptName(p.dept), p.dept, p.acct, p.acctName, p.sum, p.cnt]);
    }
    return { items, pivot };
  }

  return { nfc, textKey, parseRaw, nettingGroup, netting, buildReviewSheets };
});
