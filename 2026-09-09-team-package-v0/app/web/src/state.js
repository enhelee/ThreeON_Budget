export const state = {
  view: "home", year: "", years: [],
  type: "all", search: "", sort: "rateDesc",
  status: null, branches: null, stats: null, overview: null,
  health: null,        // GET /healthz — DB 종류·인증 여부·리비전 (메인 헤더/카드)
  exportStatus: null,  // GET /api/export-status — 팀 연계 산출물을 마지막으로 넘긴 연도·시각
  returnHash: null,  // 401 로 게이트에 튕기기 직전 보던 주소 — 로그인 후 여기로 돌아간다
  learned: null, overrides: null, bizEdits: null,
  ovBiz: {},        // 재배정 대상 지사의 사업 목록 캐시 {"연도|지사": [{budget,사업명}]}
  pending: null,    // 분석 미반영 변경 {total, counts, learn_pending, analyzed_at}
  // 설정 화면 「연도 기준정보」 — 그 해 구성 한 벌 + 연도 축 없는 별칭 + 마스터 조회
  yearConfig: null, ycTab: "depts", ycAliasKind: "dept",
  // 손댄 표만 저장한다 — 안 바뀐 표까지 보내면 «미반영» 건수가 부풀어
  //   한 번 고치고 한 번 저장했는데 배지에 3건이 잡힌다.
  ycDirty: new Set(),
  // 5번 탭 — 전망 기준연도(base_year)는 헤더 대상연도와 다른 축이다(«어느 해에 세운 가정인가»).
  //   data = 그 기준연도의 가정 9종(/api/forecast/state) · bench = 표준화 결과 · table = 전망 표.
  //   dirty = 손댄 가정 표(저장 버튼에서만 보낸다) · benchEdits = 산출방식·표준금액 편집분.
  fc: { baseYear: "", baseYears: [], lockedYears: [], tab: "manage",
        data: null, bench: null, table: null, site: "__total__",
        dirty: new Set(), preview: null, benchGroup: "all",
        benchEdits: {methods: {}, overrides: {}} },
  lockStates: null, // 마감을 풀어 놓고 아직 다시 잠그지 않은 연도들 — 전 화면 배너
  loadErrors: [],   // 이번 화면에서 못 불러온 구역들 — 조용히 비어 보이지 않게 배너로 알린다
  det: { branch: "", data: null, item: "", attr: "", q: "", budget: "all",
         hideMissing: false, sortKey: "", sortDir: 1,
         open: new Set(), sel: new Set(), selBudget: null, editKey: null, delKey: null,
         // 재배정 바 입력값 — 전표 체크·검색마다 #detResults가 다시 그려지므로
         //   상태로 들고 있어야 입력한 지사·사업명이 날아가지 않는다.
         ovDept: "", ovTarget: "", ovManual: "" },
};

export const viewMeta = {
  home: ["메인", "계획·실적·전망의 오늘 기준 현황입니다. 숫자는 모두 DB 실측치입니다."],
  budget: ["예산 계획", "연도를 선택하고 계획본(양식1)을 업로드해 DB에 등록합니다."],
  collect: ["실적 집계", "연도를 선택하고 ERP(zrfm2)를 업로드 → 자동 매칭을 실행합니다."],
  branches: ["실적 분석", "전체 지사의 계획·실적·집행률을 조회합니다."],
  detail: ["실적분석(상세)", "지사별 사업 목록과 귀속 ERP 전표를 검토·수정합니다."],
  stats: ["통계·내보내기", "손익/자본 통계와 Excel 산출물을 내려받습니다."],
  forecast: ["중장기 예측", "마감된 연도의 실적으로 표준금액을 만들고(3단계) 기준연도부터 10개년을 전망합니다(4단계)."],
  settings: ["설정", "데이터셋·수동 재배정·학습·사업수정 이력을 관리합니다."],
};

// ───────────────────────── 공통 유틸 ─────────────────────────
