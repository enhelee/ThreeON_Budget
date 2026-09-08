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

  // 동의어(약어↔정식명) 정규화: raw·계획 양쪽에 같이 적용돼 매칭됨. 담당자 규칙(GT=가스터빈 등). 확장 쉬움.
  const SYNONYMS = [
    [/\bGT\b/gi, "가스터빈"],
    [/\bHRSG\b/gi, "배열회수보일러"],
  ];
  // 반복 기성/분납 마커: 회차·월·분기·비용인식을 제거해 "N회 기성"류가 한 사업으로 모이게(담당자 규칙: LTSA 등 분기기성 합산).
  // 변동비·Extra Work처럼 회차마커 없는 건 그대로 남아 별개 사업으로 유지됨.
  const INSTALLMENT_NOISE = [/\d+\s*회/g, /\d+\s*분기/g, /'?\d+\s*년?\s*\d+\s*월/g, /비용\s*역?\s*인식/g];
  // 유사도 매칭용 정규화: 동의어 치환 → 반복기성 마커 제거 → 연도·구분자 제거하고 핵심 단어만 남김
  function simNorm(t) {
    let s = (t == null ? "" : String(t)).normalize("NFC");
    for (const [re, rep] of SYNONYMS) s = s.replace(re, rep);
    for (const re of INSTALLMENT_NOISE) s = s.replace(re, " ");
    return s
      .replace(/\d{4}\s*년도?/g, " ")   // 2025년, 2024년도
      .replace(/['"’”()\[\]（）·:,\-_/]/g, " ")
      .replace(/\s+/g, "")
      .trim();
  }
  // 보정사전 키: 회차·연도·동의어까지 정규화(simNorm 규칙)해서 "29회/30회/내년껀"이 한 키로 모임 → 한 번 보정하면 매년 재사용.
  // (textKey는 회차를 남겨 매년 다른 키가 됐던 문제를 해결. netting 등 다른 textKey 사용처는 그대로 둠.)
  const corrKey = (t) => simNorm(t);
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
    ? Number(process.env.SIM_TH) : 0.35; // 매칭 임계 (overlap 기준, SIM_TH 환경변수로 튜닝)
  // 고유키 부분문자열 가점 가중. 실험 결과 금액정확도 개선 없음(오히려 미세 하락) → 기본 off(0).
  // 맞는 케이스만큼 우연 일치도 끌어와 상쇄됨. ANCHOR_W 환경변수로 재실험 가능.
  const ANCHOR_W = (typeof process !== "undefined" && process.env && process.env.ANCHOR_W != null)
    ? Number(process.env.ANCHOR_W) : 0;
  // 4순위: 전표번호 다르지만 텍스트 유사한 건 통합(네팅 Step C). diceSim 이 임계 이상끼리 한 건으로.
  // null=끄기(완전일치 통합만). NET_SIM 환경변수로 튜닝.
  const NET_SIM_TH = (typeof process !== "undefined" && process.env && process.env.NET_SIM != null)
    ? Number(process.env.NET_SIM) : null;
  // 강제배정: 임계 미만이어도 같은 조직 최고줄에 억지로 얹을지. 기본 ON(금액정확도 유지).
  // OFF로 하면 0이어야 할 사업줄 오염은 줄지만, conf 0.2~0.34 정당매칭이 미배분으로 빠져 금액정확도가 하락.
  // → 담당자 목표(사업별 금액)상 기본 on. FORCE_ASSIGN=0으로 끌 수 있음.
  const FORCE_ASSIGN = !(typeof process !== "undefined" && process.env && process.env.FORCE_ASSIGN === "0");
  // 소액(≤200만) 처리: 기본 on = Codex방식(텍스트 보존 후 매칭). SMALL_TEXT_MATCH=0 → 옛 방식(무조건 소액자재구매 합산).
  const SMALL_TEXT_MATCH = !(typeof process !== "undefined" && process.env && process.env.SMALL_TEXT_MATCH === "0");
  // 강제배정 바닥값: 유사도가 이 값 미만이면 "아무 사업에나 던지지 말고" 검토목록으로. (담당자 규칙: 판단 가능하게)
  // 기본 0.12 — "수선유지비 대체"(0.095) 같은 사업단서 없는 노이즈는 걸러지고, "소방용역"(0.235) 같은 약한 진짜매칭은 유지.
  const FORCE_FLOOR = (typeof process !== "undefined" && process.env && process.env.FORCE_FLOOR != null) ? Number(process.env.FORCE_FLOOR) : 0.12;
  // 키워드 우선매칭(실험): 희귀 2글자 하나로 덮어쓰면 오배정↑(측정 -4%p) → 기본 off. KEYWORD_MATCH=1로 실험.
  const KEYWORD_MATCH = (typeof process !== "undefined" && process.env && process.env.KEYWORD_MATCH === "1");
  // 명백한 1위: 유사도 임계 이상 + 2위와 이 격차 이상이면 신뢰도 낮아도 "검토필요" 안 붙임(반복 사업 재검토 방지). 배정은 불변.
  const CLEAR_GAP = (typeof process !== "undefined" && process.env && process.env.CLEAR_GAP != null) ? Number(process.env.CLEAR_GAP) : 0.1;
  // 역분개 상쇄: 같은(지사×과목) 안에서 금액이 정확히 +X/−X로 짝지는 전표쌍 제거(전표번호·텍스트 달라도).
  // 취소전표(9600·9100…)가 원전표와 안 지워지는 것 방지. ⚠️우연 상쇄 위험 → 검증 필요. 기본 on, REVERSAL=0으로 끔.
  const REVERSAL_CANCEL = !(typeof process !== "undefined" && process.env && process.env.REVERSAL === "0");
  // 전기일 묶음 과목: 같은 (지사×전기일)에 취득한 건 같은 사업으로 본다(담당자 규칙).
  // 예: 기계장치(20704001) — 5/9 취득분(구입관세·통관·운송·TCP·HMI·성능개선 등)이 다 한 사업(동남권 가스터빈 성능개선).
  // 날짜별 합산이라 +/− 상쇄도 자동 처리. 대표 사업명=그 날짜 최대금액 텍스트. 연도무관.
  const DATE_COLLAPSE = new Set([]);
  // 실적 제외 텍스트: 열수송·배전 인프라 "이설공사 자산취득"(남의 공사로 관로/배전선 옮긴 보상)은 실적 아님.
  // 여러 지사(강남·삼송·화성 등)에 걸친 체계적 제외. "이설"+"취득" 둘 다 있어야(손익 정상 이설수선 오제외 방지). 연도무관.
  const EXCLUDE_TEXT = (t) => /이설/.test(t) && /취득/.test(t);
  const AMOUNT_UNIT = 1000;   // 집계표는 천원 단위, raw는 원 단위 → 출력 시 원/1000
  const toUnit = (won) => Math.round((Number(won) || 0) / AMOUNT_UNIT); // 원 → 천원(반올림)

  // ── [1] raw 파싱 ─────────────────────────────────────────
  // rows: SheetJS sheet_to_json(header:1) 결과 (2차원 배열). 헤더 1줄 가정.
  // 열: A자금텍스트 B약정항목 C약정항목텍스트 D기간 E전기일 F참조전표 G금액
  //     H텍스트 I이름 J이름 K코스트센터 L손익센터 M내역 N오더 O공급업체 P자금관리센터
  function parseRaw(rows, orgMap) {
    const out = [];
    for (let i = 1; i < rows.length; i++) {
      const r = rows[i];
      const acct = String(r[1] == null ? "" : r[1]).trim();
      if (!acct) continue; // 합계행 등 약정항목 빈 행 제거
      const text0 = nfc(r[7] == null ? "" : String(r[7])).trim();
      if (EXCLUDE_TEXT(text0)) continue; // 열수송·배전 인프라 이설공사 자산취득 = 실적 제외(담당자 규칙)
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
        lossCenter: nfc(r[11]), // L열 손익센터 — 검토목록 ERP 조회용
        mgmtCenter,
        org: C.resolveOrg(mgmtCenter, nameJ, nfc(r[8]), orgMap), // 지사 or 처 or null. 본사는 자금관리센터 전체코드→부서코드시트
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
      stage.push({ text: b.text, amount: net, docNos: [docNo], n: arr.length, costName: b.nameI, vendor: b.vendor, date: b.date, lossCenter: b.lossCenter });
    }
    for (const it of noDoc) stage.push({ text: it.text, amount: it.amount, docNos: [], n: 1, costName: it.nameI, vendor: it.vendor, date: it.date, lossCenter: it.lossCenter });

    // Step A2 (역분개 상쇄): 금액이 정확히 +X/−X로 짝지는 항목쌍 제거 (전표번호·텍스트 달라도).
    if (REVERSAL_CANCEL) {
      const posByAmt = new Map(); // 양수 금액 → stage 인덱스 목록
      for (let i = 0; i < stage.length; i++) if (stage[i].amount > 0) { const k = stage[i].amount; if (!posByAmt.has(k)) posByAmt.set(k, []); posByAmt.get(k).push(i); }
      const removed = new Set();
      for (let j = 0; j < stage.length; j++) {
        if (stage[j].amount >= 0) continue;
        const arr = posByAmt.get(-stage[j].amount);
        if (arr && arr.length) { removed.add(arr.pop()); removed.add(j); } // 원전표 1건과 취소전표 1건 짝지어 제거
      }
      if (removed.size) stage = stage.filter((_, i) => !removed.has(i));
    }

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
      result.push({ text: best.text, amount: net, docNos, n: arr.reduce((a, x) => a + (x.n || 1), 0), costName: best.costName, vendor: best.vendor, date: best.date, lossCenter: best.lossCenter });
    }
    // Step C (4순위): 전표번호 다르지만 텍스트 유사한 건 통합. 금액 큰 워딩을 대표로.
    // IDF 가중: 그룹 내 흔한 bigram은 약하게, 구별되는(희귀) bigram은 강하게 → 핵심어가 겹칠 때만 통합.
    if (NET_SIM_TH != null) {
      const gdf = new Map();
      for (const s of result) { s._g = bigrams(simNorm(s.text)); for (const g of s._g) gdf.set(g, (gdf.get(g) || 0) + 1); }
      const M = result.length || 1;
      const gidf = (g) => Math.log((M + 1) / (gdf.get(g) || 1)) + 1;
      const wsim = (a, b) => { // IDF 가중 overlap(포함도)
        let inter = 0, sa = 0, sb = 0;
        for (const g of a) { const w = gidf(g); sa += w; if (b.has(g)) inter += w; }
        for (const g of b) sb += gidf(g);
        return Math.min(sa, sb) ? inter / Math.min(sa, sb) : 0;
      };
      const byLen = result.slice().sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount));
      const clusters = [];
      for (const s of byLen) {
        if (textKey(s.text) === "") { clusters.push({ rep: s, members: [s] }); continue; } // 빈텍스트는 유사통합 안 함
        let placed = null;
        for (const c of clusters) {
          if (textKey(c.rep.text) === "") continue;
          if (wsim(s._g, c.rep._g) >= NET_SIM_TH) { placed = c; break; }
        }
        if (placed) placed.members.push(s); else clusters.push({ rep: s, members: [s] });
      }
      const merged = [];
      for (const c of clusters) {
        const net = c.members.reduce((a, x) => a + x.amount, 0);
        if (net === 0) continue; // 상계로 0 → 제거
        const rep = c.members.reduce((a, x) => (Math.abs(x.amount) > Math.abs(a.amount) ? x : a), c.members[0]);
        const docNos = c.members.reduce((a, x) => a.concat(x.docNos || []), []);
        merged.push({ text: rep.text, amount: net, docNos, n: c.members.reduce((a, x) => a + (x.n || 1), 0), costName: rep.costName, vendor: rep.vendor });
      }
      return merged;
    }
    return result;
  }

  // 전체 netting: dept(자금관리센터) × acct 로 그룹핑 후 nettingGroup 적용
  // 경상정비는 예외: 지사(dept)별로 전부 하나로 합산
  function netting(rawItems) {
    // 이름열(I)의 괄호 하위구분(예: "강남(동남권)"→"동남권"). 종합표는 org로 재합산돼 불변,
    // netting/매칭에서만 하위그룹을 분리해 사업 매칭 정확도를 높인다.
    const SUB_TAGS = []; // name-column sub-tag whitelist; empty = disabled (no net gain in tests, re-enable by adding tags)
    const subTagOf = (nm) => { const s = nfc(nm == null ? "" : String(nm)).replace(/\s/g, ""); return SUB_TAGS.find((t) => s.indexOf(t) >= 0) || ""; };
    // 전기일 배치 전파: 같은 (조직×과목×전기일)에 텍스트 있는 전표가 있으면, 빈텍스트 전표에
    // 그 날짜의 대표 텍스트(금액 최대)를 물려줌 — 담당자의 "날짜+키워드" 수기 유추를 코드화.
    // (부수효과: 빈텍스트가 같은 날짜 역분개 텍스트를 물려받아 상계 제거되기도 함)
    const propagateByDate = (its) => {
      const byD = new Map();
      for (const it of its) { const d = String(it.date == null ? "" : it.date); if (!byD.has(d)) byD.set(d, []); byD.get(d).push(it); }
      return its.map((it) => {
        if (textKey(it.text) !== "") return it;
        const same = (byD.get(String(it.date == null ? "" : it.date)) || []).filter((x) => textKey(x.text) !== "");
        if (!same.length) return it;
        const rep = same.reduce((a, x) => (Math.abs(x.amount) > Math.abs(a.amount) ? x : a), same[0]);
        return { ...it, text: rep.text, _dateProp: true };
      });
    };
    const groups = new Map(); // key: org(+하위태그) + SEP + acct — 같은 조직·(하위)·과목만 통합
    for (const it of rawItems) {
      const orgKey = (it.org || ("X:" + it.mgmtCenter)) + (subTagOf(it.nameI) ? "" + subTagOf(it.nameI) : "");
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
        subTag: subTagOf(items[0].nameI), // 하위구분(예: 동남권). 종합표엔 영향 없음(org로 합산).
      };
      if (meta.bucket === "gyeongsang") {
        // 경상정비: 전표수·전기일·사업명 무관 지사별 1건 합산
        const total = items.reduce((s, x) => s + x.amount, 0);
        cleaned.push({ ...meta, text: "경상정비 통합", amount: total, docNos: [], n: items.length, costName: items[0].nameI });
        continue;
      }
      if (meta.bucket === "rule3") {
        // rule3(자산화예비품·고온부품·저장품):
        //  - 텍스트 있는 건: 일반 netting → 계획 사업명과 텍스트 매칭
        //  - 텍스트 없는 건: 지사별 × 전기일(날짜)별로 합산 → "제1차/2차… 예비품 입고"로 고정 정리
        const textItems = items.filter((x) => textKey(x.text) !== "");
        const emptyItems = items.filter((x) => textKey(x.text) === "");
        for (const x of nettingGroup(textItems)) cleaned.push({ ...meta, ...x });
        const byDate = new Map();
        for (const it of emptyItems) { const k = String(it.date == null ? "" : it.date); if (!byDate.has(k)) byDate.set(k, []); byDate.get(k).push(it); }
        const dateKeys = [...byDate.keys()].sort((a, b) => {
          const na = Number(a), nb = Number(b);
          if (!isNaN(na) && !isNaN(nb)) return na - nb; // 엑셀 날짜 serial 등 숫자면 수치 정렬
          return a < b ? -1 : a > b ? 1 : 0;            // 문자열이면 사전식(날짜 문자열도 대개 정렬됨)
        });
        let cha = 0;
        for (const dk of dateKeys) {
          const arr = byDate.get(dk);
          const net = arr.reduce((s, x) => s + x.amount, 0);
          if (net === 0) continue; // 상계로 0이면 제거
          cha++;
          const b = arr.reduce((a, x) => (Math.abs(x.amount) > Math.abs(a.amount) ? x : a), arr[0]);
          cleaned.push({ ...meta, text: "제" + cha + "차 예비품 입고", amount: net, date: b.date, lossCenter: b.lossCenter, docNos: arr.map((x) => x.docNo).filter(Boolean), n: arr.length, costName: b.nameI, vendor: b.vendor, fixedRow: true });
        }
        continue;
      }
      if (meta.bucket === "boan") {
        // 열원보완및개선(60909009):
        //  - 개별 전표 |금액| ≤ 200만: 텍스트 보존 후 후보 매칭, 불명확한 잔여만 소액 합산
        //  - 200만 초과: 기존 netting → 텍스트 매칭 (빈텍스트는 예비품/저장품 대체)
        const SMALL_TH = 2000000;
        const small = items.filter((x) => Math.abs(x.amount) <= SMALL_TH);
        const big = items.filter((x) => Math.abs(x.amount) > SMALL_TH);
        // 소액이라도 사업 텍스트를 보존: 명확한 후보가 있으면 먼저 배정한다.(SMALL_TEXT_MATCH=0이면 옛 방식: 무조건 합산)
        if (SMALL_TEXT_MATCH) {
          for (const x of nettingGroup(small)) cleaned.push({ ...meta, ...x, smallPurchase: true });
        } else {
          const smallSum = small.reduce((s, x) => s + x.amount, 0);
          if (smallSum !== 0) { const orgName = meta.org || meta.deptName || ""; cleaned.push({ ...meta, text: (orgName ? orgName + " " : "") + "소액자재구매", amount: smallSum, docNos: [], n: small.length, costName: (small[0] || {}).nameI, fixedRow: true }); }
        }
        let netted = nettingGroup(propagateByDate(big)).map((x) => {
          if (textKey(x.text) === "") {
            const startsWith6 = x.docNos.some((d) => d[0] === "6");
            return { ...x, text: startsWith6 ? "저장품 대체" : "예비품 대체" };
          }
          return x;
        });
        for (const x of netted) cleaned.push({ ...meta, ...x });
        continue;
      }
      if (DATE_COLLAPSE.has(meta.acct)) {
        // 전기일 묶음: 같은 (지사×전기일) = 같은 사업. 날짜별 합산(+/−상쇄 자동), 대표=최대금액 텍스트.
        const byDate = new Map();
        for (const it of items) { const k = String(it.date == null ? "" : it.date); if (!byDate.has(k)) byDate.set(k, []); byDate.get(k).push(it); }
        for (const [, arr] of byDate) {
          const net = arr.reduce((s, x) => s + x.amount, 0);
          if (net === 0) continue; // 그 날짜 전액 상쇄 → 제거
          const withText = arr.filter((x) => textKey(x.text) !== "");
          const pool = withText.length ? withText : arr;
          const rep = pool.reduce((a, x) => (Math.abs(x.amount) > Math.abs(a.amount) ? x : a), pool[0]);
          cleaned.push({ ...meta, text: rep.text, amount: net, docNos: arr.map((x) => x.docNo).filter(Boolean), n: arr.length, costName: rep.nameI, vendor: rep.vendor });
        }
        continue;
      }
      const netted = nettingGroup(propagateByDate(items));
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
  function fillChipInPlace(aoa, cleaned, ledger, C, corrections) {
    const corr = corrections || new Map();
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
      annual: find((h) => h.includes("연예산")),
      actual: find((h) => h.includes("실적")),
    };
    if (ci.actual < 0) ci.actual = header.length - 1;
    // 과목별 색인을 만들고, 실제 후보 선택은 같은 조직 안으로 제한
    const planByCode = new Map();
    let planRows = 0;
    for (let r = hr + 1; r < grid.length; r++) {
      const biz = String(grid[r][ci.biz] == null ? "" : grid[r][ci.biz]).trim();
      if (!biz) continue;
      if (biz.includes("미반영") || String(grid[r][0]).includes("예시")) continue;
      const code = C.resolveAcctCode(grid[r][ci.acctName]);
      if (!code) continue;
      if (!planByCode.has(code)) planByCode.set(code, []);
      // actual0 = 업로드 집계표의 기존 실적(있으면). 예비품 등 텍스트 없는 합산 배치를 금액으로 사업에 연결할 때 사용(담당자 규칙: 금액 일치=확정).
      const actual0 = (ci.actual >= 0 ? Number(grid[r][ci.actual]) || 0 : 0);
      planByCode.get(code).push({ r, biz, org: nrm(grid[r][ci.deptName]), annual: (ci.annual >= 0 ? Number(grid[r][ci.annual]) || 0 : 0), actual0 });
      grid[r][ci.actual] = 0; // 입력 파일의 기존 실적을 재사용하지 않고 raw로 재계산(예비품 금액매칭은 위 actual0 사본 사용)
      planRows++;
    }
    // 실적 항목을 예산과목 코드별로 그룹핑
    const actByCode = new Map();
    for (const x of cleaned) {
      if (x.ledger !== ledger) continue;
      if (!actByCode.has(x.acct)) actByCode.set(x.acct, []);
      actByCode.get(x.acct).push(x);
    }
    // 각 실적 항목 → 같은 조직·과목의 후보로 배정
    let filled = 0;
    const unmatched = [];
    const sumByRow = {};
    const log = []; // 배정 기록: [지사, 예산과목, 전표텍스트, 금액천원, 내가붙인사업명, 비고]
    // IDF 가중 dice: 과목 내에서 공통인 bigram은 약하게, 희귀(구분되는) bigram은 강하게
    const METRIC = (typeof process !== "undefined" && process.env && process.env.SIM_METRIC) || "overlap";
    const wDice = (ag, bg, idf, defW) => {
      let inter = 0, sa = 0, sb = 0;
      for (const g of ag) { const w = idf.get(g) || defW; sa += w; if (bg.has(g)) inter += w; }
      for (const g of bg) sb += (idf.get(g) || defW);
      if (METRIC === "overlap") return Math.min(sa, sb) ? inter / Math.min(sa, sb) : 0; // 포함도
      return (sa + sb) ? (2 * inter) / (sa + sb) : 0; // dice
    };
    for (const [code, items] of actByCode) {
      const prows = planByCode.get(code) || [];
      // 금액매칭 힌트도 같은 조직·과목 안에서만 산출
      const annualHint = (amtCheon, org) => { if (!amtCheon) return ""; const hits = prows.filter((p) => p.org === nrm(org) && p.annual && p.annual === amtCheon); return hits.length === 1 ? "연예산일치→" + hits[0].biz : (hits.length > 1 ? "연예산일치(다수)" : ""); };
      // 과목 내 사업명 bigram IDF 계산 (지역/분야 등 구분 단어 강조)
      const df = new Map();
      for (const p of prows) { p._g = featSet(p.biz); for (const g of p._g) df.set(g, (df.get(g) || 0) + 1); }
      // 고유 식별어(키워드): 과목 내 df<=2 인 희귀 bigram만 (소방·승강기 등). 흔한 어(용역·점검)는 df 커서 자동 제외.
      for (const p of prows) p._kw = new Set([...p._g].filter((g) => (df.get(g) || 0) <= 2));
      const N = prows.length || 1;
      const idf = new Map();
      for (const [g, d] of df) idf.set(g, Math.log((N + 1) / d) + 1);
      const defW = Math.log(N + 1) + 1; // 계획에 없던 bigram = 희귀 취급
      // ── 고유키 anchor: 과목 내 사업명의 희귀 부분문자열(3~6자)이 전표텍스트에 그대로 나오면 가점 ──
      // 흔한 단어(정기점검/구매 등)는 여러 사업명에 겹쳐 df가 커져 자동 배제됨. 연도무관 런타임 계산.
      const A_MAXDF = 2;   // 과목 내 이 개수 이하 사업명에만 등장하는 부분문자열만 고유키로 인정
      const subsOf = (s) => { const set = new Set(); const n = s.length; for (let L = 3; L <= 6; L++) for (let i = 0; i + L <= n; i++) set.add(s.slice(i, i + L)); return set; };
      const subDf = new Map();
      for (const p of prows) { p._sn = simNorm(p.biz); p._subs = [...subsOf(p._sn)]; for (const g of p._subs) subDf.set(g, (subDf.get(g) || 0) + 1); }
      for (const p of prows) {
        p._anchors = p._subs.filter((g) => (subDf.get(g) || 99) <= A_MAXDF);
        p._anchorTot = p._anchors.reduce((s, g) => s + g.length, 0); // 길수록 구체적 → 가중
      }
      const anchorFrac = (p, txtNorm) => {
        if (!p._anchorTot) return 0;
        let s = 0; for (const g of p._anchors) if (txtNorm.indexOf(g) >= 0) s += g.length;
        return s / p._anchorTot; // 이 사업명 고유키가 전표에 얼마나 들어있나 (0~1)
      };
      const pickBest = (pool, tg, txtNorm) => {
        let row = null, best = 0, second = 0;
        for (const p of pool) {
          let sc = wDice(tg, p._g, idf, defW);
          if (ANCHOR_W && txtNorm) sc += ANCHOR_W * anchorFrac(p, txtNorm);
          if (sc > best) { second = best; best = sc; row = p; }
          else if (sc > second) { second = sc; }
        }
        return { row, best, second };
      };
      // 키워드 픽: 전표텍스트에 어떤 사업의 고유 식별어가 가장 많이 들어있나. 유일한 최다면 그 사업(동점·0이면 판단 보류).
      const keywordPick = (pool, tg) => {
        let row = null, best = 0, tie = false;
        for (const p of pool) {
          let c = 0; for (const g of p._kw) if (tg.has(g)) c++;
          if (c > best) { best = c; row = p; tie = false; }
          else if (c === best && c > 0) tie = true;
        }
        return (row && best > 0 && !tie) ? row : null;
      };
      // 하위태그(이름열 괄호, 예: 동남권) 기반 사업 구분: 계획 사업명에 그 태그가 들어있으면 같은 하위로 본다.
      const subTagSet = [...new Set(items.map((x) => x.subTag).filter(Boolean))];
      for (const p of prows) { p._sub = ""; const pb = nrm(p.biz); for (const t of subTagSet) if (pb.indexOf(t) >= 0) { p._sub = t; break; } }
      const rowsByOrg = {};
      for (const p of prows) (rowsByOrg[p.org] = rowsByOrg[p.org] || []).push(p);
      const vendorToRow = {}; // 런타임 학습: vendor → 계획줄 r (텍스트 매칭에서 배움)
      // 1패스: 텍스트 있는 항목 배정 + vendor→사업 학습
      const empties = [];
      for (const it of items) {
        // 경상정비는 계획대비실적에 넣지 않음(정답과 동일) — 종합표에만 반영됨
        if (it.bucket === "gyeongsang") continue;
        // 보정사전은 합산 항목에도 우선 적용
        const io = nrm(it.org);
        // 0) 보정 사전 우선: (조직|과목|전표텍스트)가 등록돼 있으면 그 사업으로 확정
        const ckey = it.org + "|" + it.acct + "|" + corrKey(it.text);
        if (corr.has(ckey)) {
          if (/^제외/.test(nfc(String(corr.get(ckey))).trim())) { log.push([it.org, it.acctName, it.text, toUnit(it.amount), "(제외)", 1, "보정:제외", it.date, (it.docNos || []).join(","), it.lossCenter, ""]); continue; } // 보정사전 "제외" → 실적에서 뺌
          const target = textKey(corr.get(ckey));
          const prow = prows.find((p) => p.org === io && textKey(p.biz) === target);
          if (prow) { sumByRow[prow.r] = (sumByRow[prow.r] || 0) + it.amount; if (it.vendor && vendorToRow[it.vendor] == null) vendorToRow[it.vendor] = prow.r; log.push([it.org, it.acctName, it.text, toUnit(it.amount), prow.biz, 1, "보정됨", it.date, (it.docNos || []).join(","), it.lossCenter, ""]); continue; }
        }
        // 금액매칭(모든 과목): 전표/배치 금액이 그 지사 사업의 집계표 실적과 유일 정확일치하면, 텍스트가 달라도 그 사업 확정(담당자 규칙: 계정+금액 일치=같은 사업).
        {
          const amt = Math.round(it.amount / AMOUNT_UNIT);
          const amtHit = prows.filter((p) => p.org === io && p.actual0 && Math.round(p.actual0) === amt);
          if (amtHit.length === 1) { sumByRow[amtHit[0].r] = (sumByRow[amtHit[0].r] || 0) + it.amount; if (it.vendor && vendorToRow[it.vendor] == null) vendorToRow[it.vendor] = amtHit[0].r; log.push([it.org, it.acctName, it.text, toUnit(it.amount), amtHit[0].biz, 1, "명확(금액일치)", it.date, (it.docNos || []).join(","), it.lossCenter, ""]); continue; }
        }
        if (it.fixedRow) {
          const exact = prows.filter((p) => p.org === io && textKey(p.biz) === textKey(it.text));
          // 금액매칭: 배치 금액이 이 지사 사업의 (업로드 집계표)실적과 유일하게 정확히 일치하면 그 사업 확정(담당자 규칙: 금액 일치=맞음).
          const amt = Math.round(it.amount / AMOUNT_UNIT);
          const amtHit = prows.filter((p) => p.org === io && p.actual0 && Math.round(p.actual0) === amt);
          if (exact.length === 1) {
            sumByRow[exact[0].r] = (sumByRow[exact[0].r] || 0) + it.amount;
            log.push([it.org, it.acctName, it.text, toUnit(it.amount), exact[0].biz, 1, "합산사업명 일치", it.date, (it.docNos || []).join(","), it.lossCenter, ""]);
          } else if (amtHit.length === 1) {
            sumByRow[amtHit[0].r] = (sumByRow[amtHit[0].r] || 0) + it.amount;
            log.push([it.org, it.acctName, it.text, toUnit(it.amount), amtHit[0].biz, 1, "명확(금액일치)", it.date, (it.docNos || []).join(","), it.lossCenter, ""]);
          } else if (/자산화예비품/.test(nfc(it.acctName))) {
            // 담당자 규칙: 자산화예비품은 금액이 딱 안 맞는 배치는 그 지사 최대 예비품 사업으로 합침(못 나누면 하나로).
            const cands = prows.filter((p) => p.org === io && p.actual0 > 0).sort((a, b) => b.actual0 - a.actual0);
            if (cands.length) {
              sumByRow[cands[0].r] = (sumByRow[cands[0].r] || 0) + it.amount;
              log.push([it.org, it.acctName, it.text, toUnit(it.amount), cands[0].biz, 1, "예비품 지사합산(대표사업)", it.date, (it.docNos || []).join(","), it.lossCenter, ""]);
            } else {
              unmatched.push({ ...it, _fixedName: true });
              log.push([it.org, it.acctName, it.text, toUnit(it.amount), "", 0, "합산사업 확인요망", it.date, (it.docNos || []).join(","), it.lossCenter, ""]);
            }
          } else {
            unmatched.push({ ...it, _fixedName: true });
            log.push([it.org, it.acctName, it.text, toUnit(it.amount), "", 0, "합산사업 확인요망", it.date, (it.docNos || []).join(","), it.lossCenter, ""]);
          }
          continue;
        }
        if (it.emptyText) { empties.push(it); continue; }
        const tg = featSet(it.text + " " + (it.costName || ""));
        const txtNorm = simNorm(it.text + " " + (it.costName || ""));
        // ★ 반드시 같은 조직(지사/처) 안에서만 매칭 — 지사 간 이동 금지. + 하위태그(동남권 등) 우선.
        const itSub = it.subTag || "";
        let pool = prows.filter((p) => p.org === io && p._sub === itSub);
        if (!pool.length) pool = prows.filter((p) => p.org === io); // 같은 하위 없으면 조직 전체로 폴백
        const soR = pickBest(pool, tg, txtNorm);
        // 같은 조직·과목의 유일한 연예산 정확일치 + 텍스트 근거를 함께 확인.
        // 반올림으로 만든 우연 일치나 동액 후보 여러 개는 자동 확정하지 않는다.
        const amountHits = pool.filter((p) => p.annual > 0 && p.annual === it.amount / AMOUNT_UNIT);
        const amountRow = amountHits.length === 1 && wDice(tg, amountHits[0]._g, idf, defW) >= SIM_THRESHOLD ? amountHits[0] : null;
        const kwRow = KEYWORD_MATCH ? keywordPick(pool, tg) : null;   // 사업명 고유 키워드가 텍스트에 있으면 우선
        let chosen = amountRow || kwRow;
        let how = amountRow ? "연예산 정확일치+텍스트" : (kwRow ? "키워드 일치" : "");
        if (!chosen && soR.row && soR.best >= SIM_THRESHOLD) chosen = soR.row;        // 같은 조직 임계 이상
        else if (!chosen && soR.row && FORCE_ASSIGN && soR.best >= FORCE_FLOOR) chosen = soR.row; // 바닥값 이상만 강제. 미만이면 검토목록
        // 명백한 1위(임계 이상 + 2위와 큰 격차)면 신뢰도 낮아도 검토불요 — 반복 사업(LTSA 기성 등) 매년 재검토 방지
        if (chosen && chosen === soR.row && !amountRow && !kwRow && soR.best >= SIM_THRESHOLD && (soR.best - soR.second) >= CLEAR_GAP) how = "명확한 1위";
        // 텍스트로 배정된 사업이 "연예산 정확일치 사업"과 같으면 확정(두 신호 일치) — 연료전지 LTSA 등. 유사도 낮아도 검토불요.
        if (chosen && !amountRow && amountHits.length === 1 && chosen.r === amountHits[0].r) how = "명확(연예산+텍스트 일치)";
        // 소액: 명확히 매칭된 사업(0.5↑)은 사업명 배정. 나머지만 지사별 소액자재구매로 합산(개별 검토 불요 — 합산 금액이 목적).
        if (it.smallPurchase && (!chosen || (amountRow ? wDice(tg, chosen._g, idf, defW) : soR.best) < 0.5)) {
          unmatched.push({ ...it, text: (it.org || it.deptName || "") + " 소액자재구매", _fixedName: true, _smallRemainder: true });
          log.push([it.org, it.acctName, it.text, toUnit(it.amount), "", 0, "소액합산(지사별)", it.date, (it.docNos || []).join(","), it.lossCenter, annualHint(it.amount / AMOUNT_UNIT, it.org)]);
          continue;
        }
        if (chosen) {
          sumByRow[chosen.r] = (sumByRow[chosen.r] || 0) + it.amount;
          if (it.vendor && vendorToRow[it.vendor] == null) vendorToRow[it.vendor] = chosen.r;
          const conf = Math.round(((amountRow || kwRow) ? wDice(tg, chosen._g, idf, defW) : soR.best || 0) * 100) / 100; // 매칭 신뢰도(0~1)
          log.push([it.org, it.acctName, it.text, toUnit(it.amount), chosen.biz, conf, (how || (textKey(it.text) === "" ? "빈텍스트·확인요망" : "")), it.date, (it.docNos || []).join(","), it.lossCenter, annualHint(it.amount / AMOUNT_UNIT, it.org)]);
        } else {
          unmatched.push(it);
          log.push([it.org, it.acctName, it.text, toUnit(it.amount), "", 0, "후보 미일치·확인요망", it.date, (it.docNos || []).join(","), it.lossCenter, annualHint(it.amount / AMOUNT_UNIT, it.org)]);
        }
      }
      // 2패스: 빈텍스트(vendor별) — 학습 vendor면 그 줄 / 조직에 사업 1개면 그 줄 / 아니면 미배분 집계
      const unassigned = {};
      for (const it of empties) {
        const io = nrm(it.org);
        if (it.vendor && vendorToRow[it.vendor] != null && (rowsByOrg[io] || []).some((p) => p.r === vendorToRow[it.vendor])) {
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
    const smallRemainders = new Map();
    const extraItems = unmatched.filter((it) => {
      if (!it._smallRemainder) return true;
      const key = JSON.stringify([it.org, it.acct]);
      if (!smallRemainders.has(key)) smallRemainders.set(key, { ...it, amount: 0 });
      smallRemainders.get(key).amount += it.amount;
      return false;
    }).concat([...smallRemainders.values()].filter((it) => it.amount !== 0));
    for (const it of extraItems) {
      const row = new Array(Math.max(grid[hr].length, ci.actual + 1)).fill("");
      if (ci.acctName >= 0) row[ci.acctName] = it.acctName;
      if (ci.deptName >= 0) row[ci.deptName] = it.org || "";
      row[ci.biz] = it._fixedName ? it.text : (it._unassigned ? "(미배분·검토) " : "(신규) ") + it.text;
      row[ci.actual] = toUnit(it.amount);
      extra.push(row);
    }
    // 담당자 검토용: 각 로그행에 "매칭사업 집계표실적"과 "내합계−집계표 차이"(천원)를 붙임.
    // 차이가 크면 오배정 의심(예: 예비품 지사합산 초과, 잘못 붙은 것) → 한눈에 확인.
    const prowIdx = new Map();
    for (const [code, prs] of planByCode) for (const p of prs) prowIdx.set(p.org + "|" + code + "|" + textKey(p.biz), p);
    for (const x of log) {
      const bkey = x[4] ? textKey(x[4]) : "";
      const code = C.resolveAcctCode(x[1]);
      const p = (bkey && code) ? prowIdx.get(nrm(x[0]) + "|" + code + "|" + bkey) : null;
      if (p) { const chip = Math.round(p.actual0); x[11] = chip; x[12] = toUnit(sumByRow[p.r] || 0) - chip; }
      else { x[11] = ""; x[12] = ""; }
    }
    return { aoa: grid.concat(extra), stats: { planRows, filled, unplanned: extra.length }, log };
  }

  // ── 보정 사전 파싱: [지사, 예산과목, 전표텍스트, 올바른사업명] → Map(org|code|textKey → 사업명) ──
  function parseCorrections(aoa, C) {
    const map = new Map();
    if (!aoa || !aoa.length) return map;
    const nrm2 = (x) => String(x == null ? "" : x).normalize("NFC").replace(/\s/g, "");
    let hr = -1, H = null;
    for (let i = 0; i < Math.min(aoa.length, 6); i++) {
      const h = (aoa[i] || []).map(nrm2);
      if (h.some((x) => x.includes("전표텍스트")) && h.some((x) => x.includes("사업명"))) { hr = i; H = h; break; }
    }
    if (hr < 0) return map;
    const ci = {
      dep: H.findIndex((h) => h.includes("지사") || h.includes("부서")),
      acct: H.findIndex((h) => h.includes("예산과목") || h.includes("과목")),
      text: H.findIndex((h) => h.includes("전표텍스트")),
      // "올바른사업명"(사람이 채우는 칸)을 우선. 없을 때만 "사업명". 도구 자동칸("내가붙인사업명") 오독 방지.
      biz: (H.findIndex((h) => h.includes("올바른")) >= 0) ? H.findIndex((h) => h.includes("올바른")) : H.findIndex((h) => h.includes("사업명")),
    };
    for (let r = hr + 1; r < aoa.length; r++) {
      const row = aoa[r] || [];
      const biz = nfc(String(row[ci.biz] == null ? "" : row[ci.biz])).trim();
      if (!biz) continue; // 올바른 사업명 안 채운 줄은 스킵
      const code = C.resolveAcctCode(row[ci.acct]) || String(row[ci.acct] || "").trim();
      const org = nfc(row[ci.dep]);
      const key = org + "|" + code + "|" + corrKey(row[ci.text]);
      map.set(key, biz);
    }
    return map;
  }

  // ── 전체 오케스트레이션: raw + 예산(자본/손익) → 결과 AOA 묶음 ──
  // 입력은 SheetJS sheet_to_json(header:1) 2차원 배열들.
  function runAll(input, C) {
    const cleaned = netting(parseRaw(input.rawRows || [], input.orgMap));

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
    // 보정 사전(있으면): (조직|과목|전표텍스트)→올바른 사업명
    const corr = parseCorrections(input.correctionRows || [], C);
    // 계획대비실적: 업로드 집계표의 계획 줄을 그대로 두고 실적(B)만 채움
    let chipCap, chipPl, stats = { planRows: 0, filled: 0, unplanned: 0, corrections: corr.size };
    const CONF_REVIEW = 0.5; // 신뢰도 이 미만이면 검토 권장
    const _clRows = [];
    // "명확한 1위"·"보정됨"은 신뢰도 낮아도 검토불요. "확인" 문구 있으면 검토필요.
    const NOREVIEW = ["명확", "보정", "소액합산", "연예산"]; // 이 문구는 신뢰도 낮아도 검토불요(자동확정·집계용)
    // 검토 기준: 자재류(예비품·고온부품·저장품·공구)는 지사×과목 총액만 맞으면 됨 → 배정만 되면 통과(사업별 차이 무관).
    // 그 외 과목: 매칭 사업 총액이 집계표와 차이=0이면 통과, 차이≠0이면 검토(사업별 금액 목표).
    const JAEJAE = /자산화예비품|재생고온부품|저장품|공구와기구/;
    // 검토 판정: (1)확정문구(금액일치·보정·명확·연예산)면 원칙 통과 (2)자신없는 건(빈텍스트·미일치·저신뢰) 검토
    //          (3)단, 사업 총액이 집계표보다 크게 어긋나면(BIG_DIFF 이상) 큰 오배정이므로 검토로 노출.
    // 자재류는 지사×과목 총액 기준 → 배정만 되면 통과.
    const BIG_DIFF = 50000; // 천원. 이보다 큰 사업 총액 차이만 별도 검토 노출(작은 차이는 통과).
    const addLog = (lg) => { for (const x of lg || []) {
      const note = String(x[6] || ""); const assigned = (x[11] !== "" && x[11] != null);
      // 확정 = 확정문구(금액일치·보정·명확·연예산) 또는 사업 총액이 집계표와 일치(차이=0). 담당자 규칙: 지사별 합쳐서 총액 맞으면 통과(클라우드 사용료 월별 등).
      const confirmed = NOREVIEW.some((k) => note.includes(k)) || (assigned && Number(x[12]) === 0);
      const bigOff = assigned && Math.abs(Number(x[12]) || 0) >= BIG_DIFF; // 사업 총액이 크게 어긋남
      let review;
      if (JAEJAE.test(nfc(x[1]))) { review = assigned ? "" : ((note.includes("확인") || x[5] < CONF_REVIEW) ? "검토필요" : ""); }
      else { review = (bigOff || note.includes("확인") || (x[5] < CONF_REVIEW && !confirmed)) ? "검토필요" : ""; }
      _clRows.push([x[0], x[1], x[2], x[3], x[4], x[5], review, "", x[6], x[7], x[8], x[9], x[10] || "", x[11] == null ? "" : x[11], x[12] == null ? "" : x[12]]);
    } };
    if (input.capChipRows && input.capChipRows.length) {
      const r = fillChipInPlace(input.capChipRows, cleaned, "자본", C, corr);
      chipCap = r.aoa; stats.planRows += r.stats.planRows; stats.filled += r.stats.filled; stats.unplanned += r.stats.unplanned; addLog(r.log);
    } else {
      chipCap = buildChipgyepyoAOA((usedChip ? matchPlanToActual(cleaned, plan, C) : matchToBudget(cleaned, plan, C)).rows, "자본");
    }
    if (input.plChipRows && input.plChipRows.length) {
      const r = fillChipInPlace(input.plChipRows, cleaned, "손익", C, corr);
      chipPl = r.aoa; stats.planRows += r.stats.planRows; stats.filled += r.stats.filled; stats.unplanned += r.stats.unplanned; addLog(r.log);
    } else {
      chipPl = buildChipgyepyoAOA((usedChip ? matchPlanToActual(cleaned, plan, C) : matchToBudget(cleaned, plan, C)).rows, "손익");
    }

    // 금액 큰 순 정렬(파레토): 위에서부터 큰 건만 검토하면 대부분의 돈을 커버
    _clRows.sort((a, b) => Math.abs(Number(b[3]) || 0) - Math.abs(Number(a[3]) || 0));
    const checklist = [["지사", "예산과목", "전표텍스트", "금액(천원)", "내가붙인사업명", "신뢰도", "검토필요", "올바른사업명(수정시 작성)", "비고", "전기일", "전표번호", "손익센터", "연예산일치(참고)", "매칭사업 집계표실적(천원)", "차이(내합계-집계표)"], ..._clRows];
    stats.reviewNeeded = _clRows.filter((r) => r[6] === "검토필요").length;

    return {
      cleaned, plan, stats, checklist,
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
    fillJonghap, fillRowSubtotals, fillChipInPlace, parseChipPlan, matchPlanToActual, parseCorrections, runAll,
  };
});
