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

  // 유사도 매칭용 정규화: 연도·구분자 제거하고 핵심 단어만 남김
  function simNorm(t) {
    return (t == null ? "" : String(t))
      .normalize("NFC")
      .replace(/\d{4}\s*년도?/g, " ")   // 2025년, 2024년도
      .replace(/['"’”()\[\]（）·:,\-_/]/g, " ")
      .replace(/\s+/g, "")
      .trim();
  }
  // 문자 bigram 집합
  function bigrams(s) {
    const set = new Set();
    for (let i = 0; i < s.length - 1; i++) set.add(s.slice(i, i + 2));
    if (s.length === 1) set.add(s);
    return set;
  }
  // 단어 토큰 집합 (연도 제거, 구분자로 분리, 2자 이상). 사업명은 단어 매칭이 더 선명.
  function tokens(t) {
    const s = (t == null ? "" : String(t)).normalize("NFC").replace(/\d{4}\s*년도?/g, " ").replace(/\d+년/g, " ");
    const set = new Set();
    for (const w of s.split(/[\s,.·:;_\/()\[\]（）"'’”\-]+/)) { const x = w.trim(); if (x.length >= 2) set.add(x); }
    return set;
  }
  // 특징 집합: FEAT=token이면 토큰, 아니면 문자bigram+토큰 혼합(기본)
  function featSet(text) {
    const mode = (typeof process !== "undefined" && process.env && process.env.FEAT) || "bigram";
    if (mode === "token") return tokens(text);
    if (mode === "mix") { const s = tokens(text); for (const g of bigrams(simNorm(text))) s.add("::" + g); return s; }
    return bigrams(simNorm(text)); // 기본: 문자 bigram (A/B에서 최선)
  }
  // Dice 계수 (0~1)
  function diceSim(aStr, bStr) {
    const a = bigrams(simNorm(aStr)), b = bigrams(simNorm(bStr));
    if (a.size === 0 || b.size === 0) return 0;
    let inter = 0;
    for (const g of a) if (b.has(g)) inter++;
    return (2 * inter) / (a.size + b.size);
  }
  const SIM_THRESHOLD = (typeof process !== "undefined" && process.env && process.env.SIM_TH)
    ? Number(process.env.SIM_TH) : 0.35; // 매칭 임계 (정답 대조 후 튜닝, 튜닝 시 SIM_TH 환경변수)
  const AMOUNT_UNIT = 1000;   // 집계표는 천원 단위, raw는 원 단위 → 출력 시 원/1000
  const toUnit = (won) => Math.round((Number(won) || 0) / AMOUNT_UNIT); // 원 → 천원(반올림)

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
      const mgmtCenter = String(r[15] == null ? "" : r[15]).trim(); // P열 = 조직 키
      const nameJ = nfc(r[9]); // 이름(부서명) — 본사의 처 구분이 여기 있음
      out.push({
        fund: nfc(r[0]),
        acct,
        acctName: nfc(r[2]),
        date: r[4],
        docNo: String(r[5] == null ? "" : r[5]).trim(),
        amount,
        text: nfc(r[7] == null ? "" : String(r[7])).trim(),
        nameI: nfc(r[8]),
        nameJ,
        vendor: String(r[14] == null ? "" : r[14]).trim(), // O열 공급업체 — 빈텍스트 사업 식별 단서
        mgmtCenter,
        org: C.resolveOrg(mgmtCenter, nameJ), // 종합표 열(지사 or 처) or null
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
    const repItem = (arr) => {
      let best = arr[0];
      for (const x of arr) if (Math.abs(x.amount) > Math.abs(best.amount)) best = x;
      return best;
    };
    for (const [docNo, arr] of byDoc) {
      const net = arr.reduce((s, x) => s + x.amount, 0);
      if (net === 0) continue; // 1순위: 합0 → 제거
      const b = repItem(arr);
      stage.push({ text: b.text, amount: net, docNos: [docNo], n: arr.length, costName: b.nameI, vendor: b.vendor });
    }
    for (const it of noDoc) stage.push({ text: it.text, amount: it.amount, docNos: [], n: 1, costName: it.nameI, vendor: it.vendor });

    // Step B: 텍스트 완전일치끼리 통합. 합0이면 제거(2순위), 아니면 한 줄로 합산(중복 제거)
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
      // 같은 텍스트는 한 줄로 합치고, 대표 워딩은 금액(절대값) 최대 건
      let best = arr[0];
      for (const x of arr) if (Math.abs(x.amount) > Math.abs(best.amount)) best = x;
      const docNos = arr.reduce((a, x) => a.concat(x.docNos || []), []);
      result.push({ text: best.text, amount: net, docNos, n: arr.reduce((a, x) => a + (x.n || 1), 0), costName: best.costName, vendor: best.vendor });
    }
    return result;
  }

  // 전체 netting: dept(자금관리센터) × acct 로 그룹핑 후 nettingGroup 적용
  // 경상정비는 예외: 지사(dept)별로 전부 하나로 합산
  function netting(rawItems) {
    const groups = new Map(); // key: org(또는 fallback) + SEP + acct — 같은 조직·과목만 통합
    for (const it of rawItems) {
      const orgKey = it.org || ("X:" + it.mgmtCenter);
      const k = orgKey + "" + it.acct;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(it);
    }
    const cleaned = [];
    for (const [, items] of groups) {
      const acct = items[0].acct;
      const meta = {
        dept: items[0].mgmtCenter, acct, acctName: items[0].acctName,
        ledger: items[0].ledger, bucket: items[0].bucket,
        org: items[0].org,
        deptName: items[0].org || items[0].nameI,
      };
      if (meta.bucket === "gyeongsang") {
        // 경상정비: 전표수·전기일·사업명 무관 지사별 1건 합산
        const total = items.reduce((s, x) => s + x.amount, 0);
        cleaned.push({ ...meta, text: "경상정비 통합", amount: total, docNos: [], n: items.length, costName: items[0].nameI });
        continue;
      }
      if (meta.bucket === "rule3") {
        // rule3(자산화예비품·고온부품·저장품): 텍스트 있는 건 일반 netting,
        // 텍스트 없는 건 공급업체(vendor)별로 합산해 유지(사업 배정은 fillChipInPlace에서)
        const textItems = items.filter((x) => textKey(x.text) !== "");
        const emptyItems = items.filter((x) => textKey(x.text) === "");
        for (const x of nettingGroup(textItems)) cleaned.push({ ...meta, ...x });
        const byV = new Map();
        for (const it of emptyItems) { const v = it.vendor || "(무vendor)"; if (!byV.has(v)) byV.set(v, []); byV.get(v).push(it); }
        for (const [v, arr] of byV) {
          const net = arr.reduce((s, x) => s + x.amount, 0);
          if (net === 0) continue; // 상계로 0이면 제거
          const b = arr.reduce((a, x) => (Math.abs(x.amount) > Math.abs(a.amount) ? x : a), arr[0]);
          cleaned.push({ ...meta, text: "", amount: net, docNos: [], n: arr.length, costName: b.nameI, vendor: v, emptyText: true });
        }
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
    const deptName = (x) => x.org || x.deptName || "(제외)";
    const chp = (x) => x.org && C.CHP_GROUP[x.org] ? C.CHP_GROUP[x.org] : (C.isCheo(x.org) ? "본사" : "");
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
        x.ledger, chp(x), deptName(x), x.dept,
        x.acct, x.acctName, x.bucket, x.text, x.amount, x.n,
      ]);
    }
    // 피벗: (지사 × 과목) 합계
    const pivMap = new Map();
    for (const x of cleaned) {
      const k = x.dept + "" + x.acct;
      if (!pivMap.has(k))
        pivMap.set(k, { ledger: x.ledger, org: x.org, dept: x.dept, acct: x.acct, acctName: x.acctName, sum: 0, cnt: 0 });
      const p = pivMap.get(k);
      p.sum += x.amount; p.cnt++;
    }
    const pivot = [["자본/손익", "사업군", "지사/처", "자금관리센터", "예산과목코드", "예산과목", "실적합계", "정리항목수"]];
    for (const p of [...pivMap.values()].sort((a, b) =>
      a.ledger.localeCompare(b.ledger) || String(a.org || a.dept).localeCompare(String(b.org || b.dept)) || String(a.acct).localeCompare(String(b.acct))
    )) {
      pivot.push([p.ledger, chp(p), deptName(p), p.dept, p.acct, p.acctName, p.sum, p.cnt]);
    }
    // 미배분 vendor 목록: 빈텍스트(rule3)라 사업 자동배정이 안 되는 항목 → 담당자가 사업명 채우면 사전이 됨
    const vRows = [["자본/손익", "지사/처", "예산과목코드", "예산과목", "공급업체(vendor)", "실적금액(천원)", "→ 사업명(담당자 작성)"]];
    const vAgg = new Map();
    for (const x of cleaned) {
      if (!x.emptyText) continue;
      const k = (x.org || x.dept) + "|" + x.acct + "|" + (x.vendor || "");
      if (!vAgg.has(k)) vAgg.set(k, { ledger: x.ledger, org: x.org || x.dept, acct: x.acct, acctName: x.acctName, vendor: x.vendor || "", sum: 0 });
      vAgg.get(k).sum += x.amount;
    }
    for (const v of [...vAgg.values()].sort((a, b) => a.acct.localeCompare(b.acct) || String(a.org).localeCompare(String(b.org))))
      vRows.push([v.ledger, deptName({ org: v.org }), v.acct, v.acctName, v.vendor, Math.round(v.sum / 1000), ""]);
    return { items, pivot, vendors: vRows };
  }

  // ── [3] 예산 파싱 (양식1(월별) 시트) ─────────────────────
  // 25년/26년 열 구조가 다르므로(본부·중점전략 유무), 고정 위치가 아니라
  // 헤더 이름으로 열을 찾는다. 공백/줄바꿈 제거 후 부분일치.
  function parseBudget(rows) {
    const norm = (s) => String(s == null ? "" : s).normalize("NFC").replace(/[\s\r\n]/g, "");
    // 헤더 행 탐색: '예산코드'와 '사업명'을 동시에 포함하는 행
    let hIdx = -1, header = null;
    for (let i = 0; i < Math.min(rows.length, 8); i++) {
      const hs = rows[i].map(norm);
      if (hs.some((h) => h.includes("예산코드")) && hs.some((h) => h.includes("사업명"))) {
        hIdx = i; header = hs; break;
      }
    }
    if (hIdx < 0) return [];
    const col = (pred) => header.findIndex(pred);
    const ci = {
      hqDept: col((h) => h.includes("주관부서명")),
      dept: col((h) => h.includes("부서코드")),
      deptName: col((h) => h.includes("부서명(처") || h.includes("처.지사")),
      teamName: col((h) => h.includes("부서명(부)") || h.includes("부서명(팀)")),
      attr: col((h) => h === "속성" || h.includes("속성")),
      acct: col((h) => h.includes("예산코드")),
      acctName: col((h) => h.includes("예산과목")),
      biz: col((h) => h.includes("사업명")),
      annual: col((h) => h.includes("연예산")),
    };
    const g = (r, k) => (ci[k] >= 0 ? r[ci[k]] : "");
    const out = [];
    for (let i = hIdx + 1; i < rows.length; i++) {
      const r = rows[i];
      const acct = String(g(r, "acct") == null ? "" : g(r, "acct")).trim();
      if (!acct || acct === "0") continue;
      const dept = String(g(r, "dept") == null ? "" : g(r, "dept")).trim();
      if (!dept || dept === "0") continue;
      out.push({
        hqDept: nfc(g(r, "hqDept")), dept,
        deptName: nfc(g(r, "deptName")), teamName: nfc(g(r, "teamName")),
        attr: nfc(g(r, "attr")),
        acct, acctName: nfc(g(r, "acctName")),
        biz: nfc(g(r, "biz") == null ? "" : String(g(r, "biz"))).trim(),
        annual: Number(g(r, "annual")) || 0,
        ledger: C.ledgerOf(acct),
      });
    }
    return out;
  }

  // ── [4] netting 결과 ↔ 예산 사업명 매칭 → 집계표 행 생성 ──
  // 반환: {rows:[...], stats:{matched,shingyu,noActual}}
  function matchToBudget(cleaned, budget, C) {
    const key = (d, a) => d + "" + a;
    // 예산: (지사×과목) → 사업 리스트
    const bmap = new Map();
    for (const b of budget) {
      const k = key(b.dept, b.acct);
      if (!bmap.has(k)) bmap.set(k, []);
      bmap.get(k).push(b);
    }
    // 실적: (지사×과목) → netting 항목
    const amap = new Map();
    for (const x of cleaned) {
      const k = key(x.dept, x.acct);
      if (!amap.has(k)) amap.set(k, []);
      amap.get(k).push(x);
    }
    const rows = [];
    const stats = { matched: 0, shingyu: 0, noActual: 0 };
    const allKeys = new Set([...bmap.keys(), ...amap.keys()]);

    for (const k of allKeys) {
      const blist = bmap.get(k) || [];
      const alist = (amap.get(k) || []).slice();
      const sample = alist[0] || blist[0];
      const bucket = sample ? (sample.bucket || (alist[0] && alist[0].bucket)) : null;
      const meta0 = alist[0] || {};
      const b0 = blist[0] || {};
      const acct = (meta0.acct || b0.acct);
      const acctName = (meta0.acctName || b0.acctName);
      const dept = (meta0.dept || b0.dept);
      const ledger = C.ledgerOf(acct);
      const deptName = C.resolveDept(dept) || (b0.deptName || meta0.deptName || "");
      const buck = C.bucketOf(acct);

      const base = {
        ledger, acct, acctName, dept, deptName,
        attr: b0.attr || "", hqDept: b0.hqDept || "", teamName: b0.teamName || "",
      };

      // 경상정비: 지사당 1줄 (사업 구분 없음)
      if (buck === "gyeongsang") {
        const actualSum = alist.reduce((s, x) => s + x.amount, 0);
        const annualSum = blist.reduce((s, x) => s + x.annual, 0);
        const biz = blist.length === 1 ? blist[0].biz : (blist.length ? "경상정비(통합)" : "경상정비(통합)");
        rows.push({ ...base, biz, annual: annualSum, actual: actualSum, flag: blist.length ? "매칭" : "신규" });
        if (blist.length) stats.matched++; else stats.shingyu++;
        continue;
      }

      // 일반: 예산 사업명별로 실적 매칭 (텍스트 유사도)
      // 각 실적 항목을, 같은 (지사×과목)의 예산 사업명 중 가장 유사한 것에 배정.
      const assign = new Array(alist.length).fill(-1);
      const score = new Array(alist.length).fill(0);
      for (let i = 0; i < alist.length; i++) {
        let bestJ = -1, best = 0;
        for (let j = 0; j < blist.length; j++) {
          const s = diceSim(alist[i].text, blist[j].biz);
          if (s > best) { best = s; bestJ = j; }
        }
        if (bestJ >= 0 && best >= SIM_THRESHOLD) { assign[i] = bestJ; score[i] = best; }
      }
      // 예산 사업명별 실적 합산
      for (let j = 0; j < blist.length; j++) {
        let sum = 0, hit = false;
        for (let i = 0; i < alist.length; i++) if (assign[i] === j) { sum += alist[i].amount; hit = true; }
        rows.push({ ...base, biz: blist[j].biz, annual: blist[j].annual, actual: hit ? sum : 0, flag: hit ? "매칭" : "실적없음" });
        if (hit) stats.matched++; else stats.noActual++;
      }
      // 어느 사업에도 못 붙은 실적 → 계획 미반영 신규
      for (let i = 0; i < alist.length; i++) {
        if (assign[i] >= 0) continue;
        rows.push({ ...base, biz: alist[i].text, annual: "", actual: alist[i].amount, flag: "신규" });
        stats.shingyu++;
      }
    }
    return { rows, stats };
  }

  // 집계표 "계획 대비 실적" 시트 AOA (연번·예산과목·속성·주관부서명·부서명(처.지사)·부서명(팀)·사업명·연예산·실적)
  function buildChipgyepyoAOA(rows, ledger) {
    const filtered = rows.filter((r) => r.ledger === ledger);
    filtered.sort((a, b) =>
      String(a.dept).localeCompare(String(b.dept)) ||
      String(a.acct).localeCompare(String(b.acct)) ||
      (b.actual - a.actual)
    );
    const aoa = [["연번", "예산과목", "속성", "주관부서명", "예산귀속 부서명(처.지사)", "예산귀속 부서명(팀)", "사업명", "연예산(A)", "최종 실적금액(B)", "구분"]];
    filtered.forEach((r, i) => {
      aoa.push([i + 1, r.acctName, r.attr, r.hqDept, r.deptName, r.teamName, r.biz, r.annual, toUnit(r.actual), r.flag]);
    });
    return aoa;
  }

  // 종합표: 정답 격자(양식2/양식3) 그대로. 행=예산과목(구분별), 열=처/CHP지사/소계/합계
  // cleaned(netting 결과)를 (지사 × 약정항목코드)로 합산해 채운다.
  function buildJonghapAOA(cleaned, ledger, C) {
    const cols = C.JONGHAP_COLS;
    const tmpl = ledger === "자본" ? C.JONGHAP_ROWS_CAP : C.JONGHAP_ROWS_PL;
    // 코드 → 지사명 → 합계
    const byCode = {};
    for (const x of cleaned) {
      if (x.ledger !== ledger) continue;
      if (!x.org) continue; // 종합표 조직(지사/처)만, 제외 조직 스킵
      byCode[x.acct] = byCode[x.acct] || {};
      byCode[x.acct][x.org] = (byCode[x.acct][x.org] || 0) + (Number(x.amount) || 0);
    }
    const gtIdx = cols.findIndex((c) => c.kind === "grandtotal");
    // 한 과목(code) 행의 열 배열 계산
    function itemValues(code) {
      const src = code ? byCode[code] || {} : {};
      const arr = cols.map((c) => (c.kind === "jisa" ? toUnit(src[c.name] || 0) : 0));
      cols.forEach((c, i) => {
        if (c.kind === "subtotal") {
          const members = C.CHP_MEMBERS[c.group] || [];
          arr[i] = members.reduce((s, nm) => s + toUnit(src[nm] || 0), 0);
        }
      });
      arr[gtIdx] = cols.reduce((s, c, i) => (c.kind === "subtotal" ? s + arr[i] : s), 0);
      return arr;
    }
    const addArr = (a, b) => a.map((v, i) => v + b[i]);
    const zero = cols.map(() => 0);

    // 헤더 2줄(그룹/열이름)
    const groupRow = ["구분", "예산과목"].concat(cols.map((c) => {
      if (c.kind === "subtotal") return c.group + " 소계";
      if (c.kind === "grandtotal") return "합계";
      return "";
    }));
    const nameRow = ["", ""].concat(cols.map((c) => (c.kind === "jisa" || c.kind === "cheo") ? c.name : ""));

    const aoa = [groupRow, nameRow];
    const itemArrays = []; // {gu, arr}
    for (const row of tmpl) {
      if (row.kind === "item") {
        const arr = itemValues(row.code);
        itemArrays.push({ gu: row.gu, arr });
        aoa.push([row.gu, row.name].concat(arr));
      } else if (row.kind === "subtotal") {
        // 직전 그룹(gu) 아이템 합 — 손익 "계" = 수선유지비 합
        const grp = "수선유지비";
        const sum = itemArrays.filter((x) => x.gu === grp).reduce((a, x) => addArr(a, x.arr), zero.slice());
        aoa.push([row.gu, row.name].concat(sum));
      } else if (row.kind === "total") {
        const sum = itemArrays.reduce((a, x) => addArr(a, x.arr), zero.slice());
        aoa.push([row.gu, row.name].concat(sum));
      }
    }
    return aoa;
  }

  // 한 행의 소계/합계 열 계산 (소계=직전 소계 이후 지사합, 합계=전체 지사합)
  function fillRowSubtotals(row, colType) {
    let run = 0, grand = 0;
    for (let c = 0; c < colType.length; c++) {
      const ct = colType[c];
      if (!ct) continue;
      if (ct.t === "jisa" || ct.t === "cheo") { const v = Number(row[c]) || 0; run += v; grand += v; }
      else if (ct.t === "sub") { row[c] = run; run = 0; }
      else if (ct.t === "grand") { row[c] = grand; }
    }
  }

  // 업로드된 집계표의 종합표 틀(AOA)을 읽어 실적을 채운다. 분류·행·열은 파일 그대로.
  function fillJonghap(aoa, cleaned, ledger, C) {
    const nrm = (x) => String(x == null ? "" : x).normalize("NFC").replace(/\s/g, "");
    const grid = aoa.map((r) => (r || []).slice());
    const jisaNames = new Set(Object.values(C.DEPT_PREFIX).filter((n) => C.isJisa(n)));
    const cheoNames = new Set(C.CHP_MEMBERS.cheo);
    // 1) 헤더행: 지사명 최다인 행 (합계/그룹은 병합으로 윗행에 있을 수 있음)
    let hr = -1, bestHits = -1;
    for (let r = 0; r < grid.length; r++) {
      const hits = grid[r].map(nrm).filter((c) => jisaNames.has(c)).length;
      if (hits > bestHits) { bestHits = hits; hr = r; }
    }
    if (hr < 0 || bestHits <= 0) return grid;
    // 2) 열 분류 — 지사명 행 + (병합으로 비면) 윗행 라벨 참조
    const above = hr > 0 ? grid[hr - 1] : [];
    const colType = grid[hr].map((v, c) => {
      const nm = nrm(v) || nrm(above[c]);
      if (nm === "합계") return { t: "grand" };
      if (nm === "소계") return { t: "sub" };
      if (jisaNames.has(nm)) return { t: "jisa", name: nm };
      if (cheoNames.has(nm)) return { t: "cheo", name: nm };
      return null;
    });
    // 3) 과목명→코드 사전, 과목 열 탐색
    const name2code = {};
    C.JONGHAP_ROWS_CAP.concat(C.JONGHAP_ROWS_PL).forEach((row) => { if (row.code) name2code[nrm(row.name)] = row.code; });
    const maxC = Math.max(...grid.map((r) => r.length), 0);
    let ac = -1, acHits = -1;
    for (let c = 0; c < maxC; c++) {
      let h = 0;
      for (let r = hr + 1; r < grid.length; r++) if (name2code[nrm((grid[r] || [])[c])]) h++;
      if (h > acHits) { acHits = h; ac = c; }
    }
    // 4) cleaned → 코드→지사명→합계
    const byCode = {};
    for (const x of cleaned) {
      if (x.ledger !== ledger) continue;
      if (!x.org) continue; // 종합표 조직(지사/처)만
      byCode[x.acct] = byCode[x.acct] || {};
      byCode[x.acct][x.org] = (byCode[x.acct][x.org] || 0) + (Number(x.amount) || 0);
    }
    // 5) 아이템 행 채우기
    const itemRows = [];
    for (let r = hr + 1; r < grid.length; r++) {
      const code = name2code[nrm((grid[r] || [])[ac])];
      if (!code) continue;
      itemRows.push(r);
      const src = byCode[code] || {};
      for (let c = 0; c < colType.length; c++) {
        const ct = colType[c];
        if (!ct) continue;
        if (ct.t === "jisa" || ct.t === "cheo") grid[r][c] = toUnit(src[ct.name] || 0);
      }
      fillRowSubtotals(grid[r], colType);
    }
    // 6) 총계/소계 행 재계산 (열별 아이템 합)
    for (let r = hr + 1; r < grid.length; r++) {
      if (itemRows.indexOf(r) >= 0) continue;
      const label = String((grid[r] || [])[ac] == null ? "" : grid[r][ac]) + " " +
        String((grid[r] || [])[0] == null ? "" : grid[r][0]);
      const hasNum = colType.some((ct, c) => ct && typeof grid[r][c] === "number");
      if (!hasNum && !/합계|계/.test(label)) continue; // 값 없는 빈 행은 건드리지 않음
      const isGrand = /예산/.test(label); // "자본예산 합계", "손익예산 계"
      const src = isGrand ? itemRows : itemRows.filter((ir) => ir < r);
      for (let c = 0; c < colType.length; c++) {
        if (!colType[c]) continue;
        grid[r][c] = src.reduce((s, ir) => s + (Number(grid[ir][c]) || 0), 0);
      }
    }
    return grid;
  }

  // ── 집계표 「계획 대비 실적」 시트에서 계획(사업명·연예산) 읽기 ──
  function parseChipPlan(aoa, C) {
    const nrm = (x) => String(x == null ? "" : x).normalize("NFC").replace(/\s/g, "");
    let hr = -1, header = null;
    for (let i = 0; i < Math.min(aoa.length, 10); i++) {
      const hs = (aoa[i] || []).map(nrm);
      if (hs.some((h) => h.includes("사업명")) && hs.some((h) => h.includes("예산과목"))) { hr = i; header = hs; break; }
    }
    if (hr < 0) return [];
    const find = (pred) => header.findIndex(pred);
    const ci = {
      acctName: find((h) => h.includes("예산과목")),
      attr: find((h) => h.includes("속성")),
      hqDept: find((h) => h.includes("주관부서명")),
      deptName: find((h) => h.includes("부서명(처") || h.includes("처.지사")),
      teamName: find((h) => h.includes("부서명(팀") || h.includes("부서명(부")),
      biz: find((h) => h.includes("사업명")),
      annual: find((h) => h.includes("연예산")),
    };
    const g = (r, k) => (ci[k] >= 0 ? r[ci[k]] : "");
    const out = [];
    for (let i = hr + 1; i < aoa.length; i++) {
      const r = aoa[i] || [];
      const acctName = nfc(g(r, "acctName"));
      const biz = nfc(String(g(r, "biz") == null ? "" : g(r, "biz"))).trim();
      if (!acctName && !biz) continue;
      if (String(g(r, "biz")).includes("미반영") || String(r[0]).includes("예시")) continue; // 안내/예시 행
      const acct = C.resolveAcctCode(acctName);
      if (!acct) continue; // 코드 매칭 안 되는 과목(건설공사 등)은 실적 대상 아님
      out.push({
        acct, acctName, ledger: C.ledgerOf(acct),
        attr: nfc(g(r, "attr")), hqDept: nfc(g(r, "hqDept")),
        deptName: nfc(g(r, "deptName")), teamName: nfc(g(r, "teamName")),
        biz, annual: Number(g(r, "annual")) || 0,
      });
    }
    return out;
  }

  // ── 계획(사업명) ↔ 실적(netting) 매칭. (지사명 × 과목코드) 기준, 사업명은 유사도 ──
  function matchPlanToActual(cleaned, plan, C) {
    const key = (dn, a) => dn + "" + a;
    const pmap = new Map();
    for (const p of plan) { const k = key(p.deptName, p.acct); if (!pmap.has(k)) pmap.set(k, []); pmap.get(k).push(p); }
    const amap = new Map();
    for (const x of cleaned) {
      const dn = x.org; // 종합표 조직명(지사/처)
      if (!dn) continue;
      const k = key(dn, x.acct); if (!amap.has(k)) amap.set(k, []); amap.get(k).push(x);
    }
    const rows = [];
    const stats = { matched: 0, shingyu: 0, noActual: 0 };
    for (const k of new Set([...pmap.keys(), ...amap.keys()])) {
      const plist = pmap.get(k) || [];
      const alist = (amap.get(k) || []);
      const p0 = plist[0] || {};
      const a0 = alist[0] || {};
      const acct = p0.acct || a0.acct;
      const deptName = p0.deptName || a0.org;
      const base = {
        ledger: C.ledgerOf(acct), acct, acctName: p0.acctName || a0.acctName,
        dept: deptName, deptName, attr: p0.attr || "", hqDept: p0.hqDept || "", teamName: p0.teamName || "",
      };
      if (C.bucketOf(acct) === "gyeongsang") {
        const actual = alist.reduce((s, x) => s + x.amount, 0);
        const annual = plist.reduce((s, x) => s + x.annual, 0);
        rows.push({ ...base, biz: plist.length === 1 ? plist[0].biz : "경상정비(통합)", annual, actual, flag: plist.length ? "매칭" : "신규" });
        plist.length ? stats.matched++ : stats.shingyu++;
        continue;
      }
      const assign = new Array(alist.length).fill(-1);
      for (let i = 0; i < alist.length; i++) {
        let bj = -1, best = 0;
        for (let j = 0; j < plist.length; j++) { const s = diceSim(alist[i].text, plist[j].biz); if (s > best) { best = s; bj = j; } }
        if (bj >= 0 && best >= SIM_THRESHOLD) assign[i] = bj;
      }
      for (let j = 0; j < plist.length; j++) {
        let sum = 0, hit = false;
        for (let i = 0; i < alist.length; i++) if (assign[i] === j) { sum += alist[i].amount; hit = true; }
        rows.push({ ...base, biz: plist[j].biz, annual: plist[j].annual, actual: hit ? sum : 0, flag: hit ? "매칭" : "실적없음" });
        hit ? stats.matched++ : stats.noActual++;
      }
      for (let i = 0; i < alist.length; i++) {
        if (assign[i] >= 0) continue;
        rows.push({ ...base, biz: alist[i].text, annual: "", actual: alist[i].amount, flag: "신규" });
        stats.shingyu++;
      }
    }
    return { rows, stats };
  }

  // ── 계획대비실적 시트를 "있는 줄 그대로" 두고 실적(B)만 채움 (줄 추가 안 함) ──
  // 같은 (조직 × 과목) 안에서 각 실적 항목을 가장 유사한 사업명 줄에 배정(그룹 내 argmax).
  // 계획에 아예 없는 (조직×과목)의 실적은 맨 뒤에 집계 1줄씩만 "(계획미반영)"으로 추가.
  function fillChipInPlace(aoa, cleaned, ledger, C) {
    const nrm = (x) => String(x == null ? "" : x).normalize("NFC").replace(/\s/g, "");
    const grid = aoa.map((r) => (r || []).slice());
    let hr = -1, header = null;
    for (let i = 0; i < Math.min(grid.length, 10); i++) {
      const h = (grid[i] || []).map(nrm);
      if (h.some((x) => x.includes("사업명")) && h.some((x) => x.includes("예산과목"))) { hr = i; header = h; break; }
    }
    if (hr < 0) return { aoa: grid, stats: { planRows: 0, filled: 0, unplanned: 0 } };
    const find = (pr) => header.findIndex(pr);
    const ci = {
      acctName: find((h) => h.includes("예산과목")),
      deptName: find((h) => h.includes("부서명(처") || h.includes("처.지사")),
      biz: find((h) => h.includes("사업명")),
      actual: find((h) => h.includes("실적")),
    };
    if (ci.actual < 0) ci.actual = header.length - 1;
    // 계획 줄을 "예산과목 코드"별로만 그룹핑(부서 무관) — 사업명은 raw 전체에서 검색해 매칭
    const planByCode = new Map();
    let planRows = 0;
    for (let r = hr + 1; r < grid.length; r++) {
      const biz = String(grid[r][ci.biz] == null ? "" : grid[r][ci.biz]).trim();
      if (!biz) continue;
      if (biz.includes("미반영") || String(grid[r][0]).includes("예시")) continue;
      const code = C.resolveAcctCode(grid[r][ci.acctName]);
      if (!code) continue;
      if (!planByCode.has(code)) planByCode.set(code, []);
      planByCode.get(code).push({ r, biz, org: nrm(grid[r][ci.deptName]) });
      planRows++;
    }
    // 실적 항목을 예산과목 코드별로 그룹핑
    const actByCode = new Map();
    for (const x of cleaned) {
      if (x.ledger !== ledger) continue;
      if (!actByCode.has(x.acct)) actByCode.set(x.acct, []);
      actByCode.get(x.acct).push(x);
    }
    // 각 실적 항목 → 같은 과목의 계획 사업명 중 최고 유사도 줄에 배정(부서 무관). 임계 미만은 신규.
    let filled = 0;
    const unmatched = [];
    const sumByRow = {};
    // IDF 가중 dice: 과목 내에서 공통인 bigram은 약하게, 희귀(구분되는) bigram은 강하게
    const wDice = (ag, bg, idf, defW) => {
      let inter = 0, sa = 0, sb = 0;
      for (const g of ag) { const w = idf.get(g) || defW; sa += w; if (bg.has(g)) inter += w; }
      for (const g of bg) sb += (idf.get(g) || defW);
      return (sa + sb) ? (2 * inter) / (sa + sb) : 0;
    };
    for (const [code, items] of actByCode) {
      const prows = planByCode.get(code) || [];
      // 과목 내 사업명 bigram IDF 계산 (지역/분야 등 구분 단어 강조)
      const df = new Map();
      for (const p of prows) { p._g = featSet(p.biz); for (const g of p._g) df.set(g, (df.get(g) || 0) + 1); }
      const N = prows.length || 1;
      const idf = new Map();
      for (const [g, d] of df) idf.set(g, Math.log((N + 1) / d) + 1);
      const defW = Math.log(N + 1) + 1; // 계획에 없던 bigram = 희귀 취급
      const pickBest = (pool, tg) => {
        let row = null, best = 0;
        for (const p of pool) { const sc = wDice(tg, p._g, idf, defW); if (sc > best) { best = sc; row = p; } }
        return { row, best };
      };
      const rowsByOrg = {};
      for (const p of prows) (rowsByOrg[p.org] = rowsByOrg[p.org] || []).push(p);
      const vendorToRow = {}; // 런타임 학습: vendor → 계획줄 r (텍스트 매칭에서 배움)
      // 1패스: 텍스트 있는 항목 배정 + vendor→사업 학습
      const empties = [];
      for (const it of items) {
        // 경상정비는 계획대비실적에 넣지 않음(정답과 동일) — 종합표에만 반영됨
        if (it.bucket === "gyeongsang") continue;
        if (it.emptyText) { empties.push(it); continue; }
        const tg = featSet(it.text + " " + (it.costName || ""));
        const io = nrm(it.org);
        const soR = pickBest(prows.filter((p) => p.org === io), tg);
        let chosen = null;
        if (soR.row && soR.best >= SIM_THRESHOLD) chosen = soR.row;      // 같은 조직 매칭(임계 이상)
        else {
          const gR = pickBest(prows, tg);
          if (gR.row && gR.best >= SIM_THRESHOLD) chosen = gR.row;       // 강한 전역 매칭만 허용(처 집행 등)
          else if (it.bucket !== "gyeongsang" && soR.row) chosen = soR.row; // 강제배정은 '같은 조직 안'에서만 → 지사 간 누수 방지
        }
        if (chosen) {
          sumByRow[chosen.r] = (sumByRow[chosen.r] || 0) + it.amount;
          if (it.vendor && vendorToRow[it.vendor] == null) vendorToRow[it.vendor] = chosen.r;
        } else unmatched.push(it); // 같은 조직에 계획줄 없음 → 신규(해당 조직으로 유지)
      }
      // 2패스: 빈텍스트(vendor별) — 학습 vendor면 그 줄 / 조직에 사업 1개면 그 줄 / 아니면 미배분 집계
      const unassigned = {};
      for (const it of empties) {
        const io = nrm(it.org);
        if (it.vendor && vendorToRow[it.vendor] != null) {
          const rr = vendorToRow[it.vendor]; sumByRow[rr] = (sumByRow[rr] || 0) + it.amount;
        } else if ((rowsByOrg[io] || []).length === 1) {
          const rr = rowsByOrg[io][0].r; sumByRow[rr] = (sumByRow[rr] || 0) + it.amount;
        } else {
          const k = io + "||" + code;
          unassigned[k] = unassigned[k] || { org: it.org, acctName: it.acctName, sum: 0 };
          unassigned[k].sum += it.amount;
        }
      }
      for (const k of Object.keys(unassigned)) {
        const u = unassigned[k];
        unmatched.push({ org: u.org, acctName: u.acctName, text: "미배분", amount: u.sum, _unassigned: true });
      }
    }
    for (const code of planByCode.keys())
      for (const pr of planByCode.get(code))
        if (sumByRow[pr.r] != null) { grid[pr.r][ci.actual] = toUnit(sumByRow[pr.r]); if (sumByRow[pr.r]) filled++; }
    // 계획에 없는 실적 → 신규 줄 추가(개별)
    const extra = [];
    for (const it of unmatched) {
      const row = new Array(Math.max(grid[hr].length, ci.actual + 1)).fill("");
      if (ci.acctName >= 0) row[ci.acctName] = it.acctName;
      if (ci.deptName >= 0) row[ci.deptName] = it.org || "";
      row[ci.biz] = (it._unassigned ? "(미배분·검토) " : "(신규) ") + it.text;
      row[ci.actual] = toUnit(it.amount);
      extra.push(row);
    }
    return { aoa: grid.concat(extra), stats: { planRows, filled, unplanned: extra.length } };
  }

  // ── 전체 오케스트레이션: raw + 예산(자본/손익) → 결과 AOA 묶음 ──
  // 입력은 SheetJS sheet_to_json(header:1) 2차원 배열들.
  function runAll(input, C) {
    const cleaned = netting(parseRaw(input.rawRows || []));

    // 계획(사업명·연예산) 소스: ① 집계표의 계획대비실적 시트 ② (하위호환) 주관부서예산
    let plan = [], usedChip = false;
    if ((input.capChipRows && input.capChipRows.length) || (input.plChipRows && input.plChipRows.length)) {
      usedChip = true;
      if (input.capChipRows) plan = plan.concat(parseChipPlan(input.capChipRows, C));
      if (input.plChipRows) plan = plan.concat(parseChipPlan(input.plChipRows, C));
    } else if ((input.capBudgetRows && input.capBudgetRows.length) || (input.plBudgetRows && input.plBudgetRows.length)) {
      if (input.capBudgetRows) plan = plan.concat(parseBudget(input.capBudgetRows));
      if (input.plBudgetRows) plan = plan.concat(parseBudget(input.plBudgetRows));
    }
    // 계획대비실적: 업로드 집계표의 계획 줄을 그대로 두고 실적(B)만 채움
    let chipCap, chipPl, stats = { planRows: 0, filled: 0, unplanned: 0 };
    if (input.capChipRows && input.capChipRows.length) {
      const r = fillChipInPlace(input.capChipRows, cleaned, "자본", C);
      chipCap = r.aoa; stats.planRows += r.stats.planRows; stats.filled += r.stats.filled; stats.unplanned += r.stats.unplanned;
    } else {
      chipCap = buildChipgyepyoAOA((usedChip ? matchPlanToActual(cleaned, plan, C) : matchToBudget(cleaned, plan, C)).rows, "자본");
    }
    if (input.plChipRows && input.plChipRows.length) {
      const r = fillChipInPlace(input.plChipRows, cleaned, "손익", C);
      chipPl = r.aoa; stats.planRows += r.stats.planRows; stats.filled += r.stats.filled; stats.unplanned += r.stats.unplanned;
    } else {
      chipPl = buildChipgyepyoAOA((usedChip ? matchPlanToActual(cleaned, plan, C) : matchToBudget(cleaned, plan, C)).rows, "손익");
    }

    return {
      cleaned, plan, stats,
      review: buildReviewSheets(cleaned, C),
      chipCap, chipPl,
      // 종합표: 업로드 집계표의 종합표 틀이 있으면 그걸 채움(분류·행·열 파일 그대로), 없으면 자체 생성
      jongCap: (input.capJongRows && input.capJongRows.length) ? fillJonghap(input.capJongRows, cleaned, "자본", C) : buildJonghapAOA(cleaned, "자본", C),
      jongPl: (input.plJongRows && input.plJongRows.length) ? fillJonghap(input.plJongRows, cleaned, "손익", C) : buildJonghapAOA(cleaned, "손익", C),
    };
  }

  return {
    nfc, textKey, simNorm, bigrams, diceSim, SIM_THRESHOLD,
    parseRaw, nettingGroup, netting, buildReviewSheets,
    parseBudget, matchToBudget, buildChipgyepyoAOA, buildJonghapAOA,
    fillJonghap, fillRowSubtotals, fillChipInPlace, parseChipPlan, matchPlanToActual, runAll,
  };
});
