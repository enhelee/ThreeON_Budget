// 예산 실적 자동 집계 — 상수 정의 (2025년 기준)
// node(require)와 브라우저(<script>) 양쪽에서 쓰이도록 UMD 형태로 노출.
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.BUDGET_CONST = factory();
})(typeof self !== "undefined" ? self : this, function () {
  // 약정항목 코드 → 규칙 버킷
  // gyeongsang: 경상정비(지사당 1줄 통합) / boan: 열원보완및개선 / rule3: 예산리스트 매칭 / common: 공통만
  const BUCKET = {
    "60909007": "gyeongsang",     // 수선유지비-열원경상정비
    "60909009": "boan",           // 수선유지비-열원보완및개선
    "20790006": "rule3",          // 건설중인자산-자산화예비품
    "20790005": "rule3",          // 건설중인자산-재생고온부품
    "10702001": "rule3",          // 저장품-열원(보수)
    // 아래는 공통만 (명시 안 된 코드도 전부 common 처리)
    "20704001": "common",         // 기계장치
    "20706001": "common",         // 공구와기구-열원시설공기구
    "20703001": "common",         // 구축물
    "20702001": "common",         // 건물
    "60913003": "common",         // 지급수수료-열원점검수수료
    "60909008": "common",         // 수선유지비-열원정기유지보수
    "60909002": "common",         // 수선유지비-열원정기점검
    "60909001": "common",         // 수선유지비-건물/구축물
    "60602015": "common",         // 외주비-열원정기점검 (A급정비)
  };
  function bucketOf(acct) {
    return BUCKET[String(acct).trim()] || "common";
  }

  // 예산과목(표시명) → 약정항목 코드. 종합표/계획대비실적의 과목명에서 코드를 역인식.
  const ACCT_NAME_TO_CODE = {
    "수선유지비-열원경상정비": "60909007",
    "수선유지비-열원보완및개선": "60909009",
    "수선유지비-열원보완개선및기타": "60909009",
    "수선유지비-열원정기유지보수": "60909008",
    "수선유지비-열원정기점검": "60909002",
    "수선유지비-건물/구축물": "60909001",
    "지급수수료-열원점검수수료": "60913003",
    "지급수수료-열원점검검사수수료": "60913003",
    "건설중인자산-자산화예비품": "20790006",
    "건설중인자산-재생고온부품": "20790005",
    "저장품-열원(보수)": "10702001",
    "기계장치": "20704001",
    "공구와기구-열원시설공기구": "20706001",
    "구축물": "20703001",
    "건물": "20702001",
    "외주비-열원정기점검": "60602015",
    "외주비-열원공사비": null, // 건설처 소관
    "재료비-열원자재비": null,
    "외주비-열원기술용역비": null,
  };
  function resolveAcctCode(name) {
    const key = String(name == null ? "" : name).normalize("NFC").replace(/\s/g, "");
    for (const k of Object.keys(ACCT_NAME_TO_CODE)) {
      if (k.replace(/\s/g, "") === key) return ACCT_NAME_TO_CODE[k];
    }
    return null;
  }

  // 자본/손익 구분: 코드 앞자리 1·2 = 자본, 6 = 손익
  // 단, 예외: 60602015(외주비-열원정기점검=A급정비)는 6으로 시작하지만 자본 집계표 항목.
  const LEDGER_OVERRIDE = { "60602015": "자본" };
  function ledgerOf(acct) {
    const a = String(acct).trim();
    if (LEDGER_OVERRIDE[a]) return LEDGER_OVERRIDE[a];
    if (a[0] === "6") return "손익";
    if (a[0] === "1" || a[0] === "2") return "자본";
    return "기타";
  }

  // 종합표 지사 → 사업군(CHP) 매핑
  const CHP_GROUP = {
    "동탄지사": "중대형CHP", "화성지사": "중대형CHP", "파주지사": "중대형CHP",
    "광교지사": "중대형CHP", "판교지사": "중대형CHP", "삼송지사": "중대형CHP",
    "대구지사": "중대형CHP", "청주지사": "중대형CHP",
    "수원사업소": "소형CHP", "광주전남지사": "소형CHP", "강남지사": "소형CHP",
    "중앙지사": "DH", "고양사업소": "DH", "용인지사": "DH", "분당사업소": "DH",
    "세종지사": "DH", "김해사업소": "DH", "양산지사": "DH", "평택지사": "DH",
  };

  // 자금관리센터(P열) 앞 4자리 → 조직명 (종합표 표기 기준)
  // raw 표기(판교사업소, 강남(동남권) 등)와 종합표 표기(판교지사, 강남지사)가 달라
  // 코드 접두로 매핑하면 흔들리지 않는다.
  const DEPT_PREFIX = {
    "1000": "본사",
    "2010": "중앙지사", "2020": "강남지사",
    "2030": "미래개발원", "2032": "미래개발원",
    "3010": "분당사업소", "3020": "고양사업소", "3030": "수원사업소",
    "3040": "용인지사", "3050": "화성지사", "3060": "파주지사",
    "3070": "판교지사", "3080": "삼송지사", "3090": "광교지사",
    "3100": "동탄지사", "3110": "평택지사",
    "4010": "대구지사", "4020": "양산지사", "4022": "김해사업소",
    "4030": "청주지사", "4040": "세종지사", "4050": "광주전남지사",
  };
  function resolveDept(mgmtCenter) {
    const pre = String(mgmtCenter || "").trim().slice(0, 4);
    return DEPT_PREFIX[pre] || null; // 미등록 접두 → 검토 대상
  }
  // 종합표 지사인지 (본사·미래개발원은 지사 아님 → CHP군 없음)
  function isJisa(deptName) {
    return Object.prototype.hasOwnProperty.call(CHP_GROUP, deptName);
  }

  // 종합표 컬럼(지사 또는 처) 해석. 본사(1000)는 이름(J열)에서 처를 뽑는다.
  // 반환: 종합표 열 이름(지사 or 처) | null(종합표에 없는 조직=제외)
  const CHEO_LIST = ["플랜트기술처", "안전처", "통합운영처", "건설처", "미래사업처"];
  function resolveOrg(mgmtCenter, nameJ, nameI, orgMap) {
    const dept = resolveDept(mgmtCenter);
    if (dept && isJisa(dept)) return dept;         // 지사(자금관리센터 앞 4자리)
    const pre = String(mgmtCenter || "").trim().slice(0, 4);
    if (pre === "1000") {                           // 본사
      // ① 자금관리센터 전체코드 → 부서코드시트 → 처 (가장 정확, 전표별). 종합표에 없는 처는 제외(null).
      if (orgMap) { const full = String(mgmtCenter || "").trim(); if (orgMap[full] !== undefined) return isCheo(orgMap[full]) ? orgMap[full] : null; }
      // ② orgMap 없거나 코드 미등록 시: J열·I열 키워드 폴백
      const sig = (String(nameJ || "") + " " + String(nameI || "")).normalize("NFC");
      for (const cheo of CHEO_LIST) if (sig.includes(cheo)) return cheo;
      if (/신재생사업부|태양광/.test(sig)) return "미래사업처";
      return null;
    }
    return null; // 미래개발원 등
  }
  function isCheo(name) { return CHEO_LIST.indexOf(name) >= 0; }

  // ── 종합표 격자 구조 (양식2/양식3 실제 레이아웃) ──
  // 열: 처 5개 + 소계, 중대형CHP 8지사 + 소계, 소형CHP 3 + 소계, DH 8 + 소계, 합계
  const JONGHAP_COLS = [
    { name: "플랜트기술처", kind: "cheo" }, { name: "안전처", kind: "cheo" },
    { name: "통합운영처", kind: "cheo" }, { name: "건설처", kind: "cheo" },
    { name: "미래사업처", kind: "cheo" }, { name: "소계", kind: "subtotal", group: "cheo" },
    { name: "동탄지사", kind: "jisa" }, { name: "화성지사", kind: "jisa" },
    { name: "파주지사", kind: "jisa" }, { name: "광교지사", kind: "jisa" },
    { name: "판교지사", kind: "jisa" }, { name: "삼송지사", kind: "jisa" },
    { name: "대구지사", kind: "jisa" }, { name: "청주지사", kind: "jisa" },
    { name: "소계", kind: "subtotal", group: "중대형CHP" },
    { name: "수원사업소", kind: "jisa" }, { name: "광주전남지사", kind: "jisa" },
    { name: "강남지사", kind: "jisa" }, { name: "소계", kind: "subtotal", group: "소형CHP" },
    { name: "중앙지사", kind: "jisa" }, { name: "고양사업소", kind: "jisa" },
    { name: "용인지사", kind: "jisa" }, { name: "분당사업소", kind: "jisa" },
    { name: "세종지사", kind: "jisa" }, { name: "김해사업소", kind: "jisa" },
    { name: "양산지사", kind: "jisa" }, { name: "평택지사", kind: "jisa" },
    { name: "소계", kind: "subtotal", group: "DH" },
    { name: "합계", kind: "grandtotal" },
  ];
  // 상단 그룹 헤더(중대형CHP/소형CHP/DH)에 속한 지사 묶음
  const CHP_MEMBERS = {
    "중대형CHP": ["동탄지사", "화성지사", "파주지사", "광교지사", "판교지사", "삼송지사", "대구지사", "청주지사"],
    "소형CHP": ["수원사업소", "광주전남지사", "강남지사"],
    "DH": ["중앙지사", "고양사업소", "용인지사", "분당사업소", "세종지사", "김해사업소", "양산지사", "평택지사"],
    "cheo": ["플랜트기술처", "안전처", "통합운영처", "건설처", "미래사업처"],
  };

  // 행: {구분, 과목명, code|null, kind}  kind: item|subtotal|total
  const JONGHAP_ROWS_CAP = [
    { gu: "자산", name: "기계장치", code: "20704001", kind: "item" },
    { gu: "자산", name: "공구와기구-열원시설공기구", code: "20706001", kind: "item" },
    { gu: "자산", name: "건물", code: "20702001", kind: "item" },
    { gu: "자산", name: "구축물", code: "20703001", kind: "item" },
    { gu: "예비품", name: "저장품-열원(보수)", code: "10702001", kind: "item" },
    { gu: "예비품", name: "건설중인자산-재생고온부품", code: "20790005", kind: "item" },
    { gu: "예비품", name: "건설중인자산-자산화예비품", code: "20790006", kind: "item" },
    { gu: "A급 정비", name: "외주비-열원정기점검", code: "60602015", kind: "item" },
    { gu: "건설공사", name: "외주비-열원공사비", code: null, kind: "item" },
    { gu: "건설공사", name: "재료비-열원자재비", code: null, kind: "item" },
    { gu: "건설공사", name: "외주비-열원기술용역비", code: null, kind: "item" },
    { gu: "자본예산 합계", name: "", code: null, kind: "total" },
  ];
  const JONGHAP_ROWS_PL = [
    { gu: "수선유지비", name: "수선유지비-건물/구축물", code: "60909001", kind: "item" },
    { gu: "수선유지비", name: "수선유지비-열원정기점검", code: "60909002", kind: "item" },
    { gu: "수선유지비", name: "수선유지비-열원경상정비", code: "60909007", kind: "item" },
    { gu: "수선유지비", name: "수선유지비-열원정기유지보수", code: "60909008", kind: "item" },
    { gu: "수선유지비", name: "수선유지비-열원보완개선및기타", code: "60909009", kind: "item" },
    { gu: "", name: "계", code: null, kind: "subtotal" },
    { gu: "지급수수료", name: "지급수수료-열원점검수수료", code: "60913003", kind: "item" },
    { gu: "손익예산 계", name: "", code: null, kind: "total" },
  ];

  return {
    BUCKET, bucketOf, ledgerOf, CHP_GROUP,
    ACCT_NAME_TO_CODE, resolveAcctCode,
    DEPT_PREFIX, resolveDept, isJisa, resolveOrg, isCheo, CHEO_LIST,
    JONGHAP_COLS, CHP_MEMBERS, JONGHAP_ROWS_CAP, JONGHAP_ROWS_PL,
  };
});
