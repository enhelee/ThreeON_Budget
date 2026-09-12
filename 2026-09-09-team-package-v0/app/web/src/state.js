export const state = {
  view: "home", year: "", years: [],
  type: "all", search: "", sort: "rateDesc",
  status: null, branches: null, stats: null, overview: null,
  learned: null, overrides: null, bizEdits: null,
  ovBiz: {},        // 재배정 대상 지사의 사업 목록 캐시 {"연도|지사": [{budget,사업명}]}
  pending: null,    // 분석 미반영 변경 {total, counts, learn_pending, analyzed_at}
  det: { branch: "", data: null, item: "", attr: "", q: "", budget: "all",
         hideMissing: false, sortKey: "", sortDir: 1,
         open: new Set(), sel: new Set(), selBudget: null, editKey: null, delKey: null,
         // 재배정 바 입력값 — 전표 체크·검색마다 #detResults가 다시 그려지므로
         //   상태로 들고 있어야 입력한 지사·사업명이 날아가지 않는다.
         ovDept: "", ovTarget: "", ovManual: "" },
};

export const viewMeta = {
  home: ["홈", "다년도 실적과 대상연도 집행 현황을 확인합니다."],
  budget: ["예산 계획", "연도를 선택하고 계획본(양식1)을 업로드해 DB에 등록합니다."],
  collect: ["실적 집계", "연도를 선택하고 ERP(zrfm2)를 업로드 → 자동 매칭을 실행합니다."],
  branches: ["실적 분석", "전체 지사의 계획·실적·집행률을 조회합니다."],
  detail: ["실적분석(상세)", "지사별 사업 목록과 귀속 ERP 전표를 검토·수정합니다."],
  stats: ["통계·내보내기", "손익/자본 통계와 Excel 산출물을 내려받습니다."],
  forecast: ["중장기 예측", "표준금액에 팩터를 적용해 미래 예산을 살펴봅니다. (개발 예정)"],
  settings: ["설정", "데이터셋·수동 재배정·학습·사업수정 이력을 관리합니다."],
};

// ───────────────────────── 공통 유틸 ─────────────────────────
