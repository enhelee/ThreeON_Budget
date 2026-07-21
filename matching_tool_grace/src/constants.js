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

  // raw 이름(I열) 안의 키워드 → 종합표 지사명
  // (raw는 "강남(동남권)", "판교사업소" 처럼 표기가 달라서 키워드로 정규화. 첫 매칭 우선)
  const DEPT_KEYWORDS = [
    ["광주전남", "광주전남지사"],
    ["동탄", "동탄지사"], ["화성", "화성지사"], ["파주", "파주지사"],
    ["광교", "광교지사"], ["판교", "판교지사"], ["삼송", "삼송지사"],
    ["대구", "대구지사"], ["청주", "청주지사"],
    ["수원", "수원사업소"], ["강남", "강남지사"], ["서울남부", "강남지사"],
    ["중앙", "중앙지사"], ["고양", "고양사업소"], ["용인", "용인지사"],
    ["분당", "분당사업소"], ["세종", "세종지사"], ["김해", "김해사업소"],
    ["양산", "양산지사"], ["경남", "양산지사"], ["평택", "평택지사"],
  ];
  function resolveDeptName(rawName) {
    const s = (rawName || "").normalize("NFC");
    for (const [kw, dept] of DEPT_KEYWORDS) if (s.includes(kw)) return dept;
    return null; // 미매핑(본사/태양광/연료전지 등) → 검토 대상
  }

  return { BUCKET, bucketOf, ledgerOf, CHP_GROUP, DEPT_KEYWORDS, resolveDeptName };
});
