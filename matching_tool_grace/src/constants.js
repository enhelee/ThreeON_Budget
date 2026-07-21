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

  // 자본/손익 구분: 코드 앞자리 1·2 = 자본, 6 = 손익
  function ledgerOf(acct) {
    const a = String(acct).trim();
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

  return {
    BUCKET, bucketOf, ledgerOf, CHP_GROUP,
    DEPT_PREFIX, resolveDept, isJisa,
  };
});
