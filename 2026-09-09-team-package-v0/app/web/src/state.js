export const state = {
  view: "home", year: "", years: [],
  type: "all", search: "", sort: "rateDesc",
  brTableOpen: true,   // 3번 탭 지사 표 펼침 — 접으면 아래 계획–실적 분포 차트가 바로 보인다
  status: null, branches: null, stats: null, overview: null,
  health: null,        // GET /healthz — DB 종류·인증 여부·리비전 (메인 헤더/카드)
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
  fc: { baseYear: "", baseYears: [], lockedYears: [], tab: "manage", manageTab: "grades",
        data: null, bench: null, table: null, site: "__total__",
        dirty: new Set(), preview: null, benchGroup: "all",
        benchEdits: {methods: {}, overrides: {}},
        // 표준화 방향 반영(2026-10-26) — 참고 엑셀 대조 · 정기비용 분리 · 표준화 탭 안쪽 보기
        compare: null, regular: null, refPreview: null, refFile: null, benchView: "std", cmpOnlyDiff: true,
        backtest: null, showRange: false,   // 백테스트 결과(눌렀을 때만 계산) · 전망 표 예측 범위 표시
        // 중장기 전망 한눈에 보기(views/forecast_viz.js) — 단계·고른 해·과목·색 기준·애니메이션·발표 모드
        viz: {level: "map", year: null, acct: "", mode: "amt", anim: null, origin: "", present: false} },
  lockStates: null, // 마감을 풀어 놓고 아직 다시 잠그지 않은 연도들 — 전 화면 배너
  loadErrors: [],   // 이번 화면에서 못 불러온 구역들 — 조용히 비어 보이지 않게 배너로 알린다
  statOpen: null,   // 통계 과목 표에서 펼친 행(«예산|과목») — 지사별 드릴다운
  alerts: null,     // /api/alerts — {alerts, summary, prev_year}
  // 검토 큐(2026-10-27, views/review.js) — data = /api/review-queue · n = 보기 건수("10"|"20"|"50"|"80"|"all")
  //   show = 미처리|처리됨|전체 · open = 전표를 펼친 줄 · sugg = 줄별 추천 재배정 캐시 · pick = 전표별 고른 사업
  rq: { data: null, n: "20", show: "open", reason: "", branch: "", budget: "all",
        open: null, noteKey: null, focus: null, sugg: {}, pick: {} },
  rqBrief: null,    // 메인 «다음 할 일»용 요약(/api/review-queue?brief=1)
  alertKind: "",    // 이상 알림 종류 필터(빈 값 = 전체)
  alertsAll: false, // 이상 알림 전부 보기(기본은 위 10건)
  settingsTab: "year",   // 설정 화면 탭(연도·학습 | 기준정보 | 데이터셋·모델 | 이력)
  helpOpen: false,  // 오른쪽 아래 도움말 말풍선 — 화면을 옮기면 닫는다
  det: { branch: "", data: null, item: "", attr: "", q: "", budget: "all",
         hideMissing: false, sortKey: "", sortDir: 1,
         pickSort: {key: "gap", dir: -1},   // 지사 카드 정렬(views/detail.js PICK_SORTS)
         lowConf: false,
         guideOpen: false,  // «? 표 보는 법» 펼침(표 머리 줄)
         varOnly: false,   // «사유 대상만» — 집행률 ±20%p 를 벗어난 사업만
         noteKey: null,    // 차이 사유 입력창이 열린 행
         open: new Set(), sel: new Set(), selBudget: null, editKey: null, delKey: null,
         // 재배정 바 입력값 — 전표 체크·검색마다 #detResults가 다시 그려지므로
         //   상태로 들고 있어야 입력한 지사·사업명이 날아가지 않는다.
         ovDept: "", ovTarget: "", ovManual: "" },
};

export const viewMeta = {
  home: "메인",
  budget: "예산 계획",
  collect: "실적 집계",
  branches: "실적 분석",
  detail: "실적분석(상세)",
  review: "검토 큐",
  stats: "통계·내보내기",
  forecast: "중장기 예측",
  settings: "설정",
};

// ───────────────────────── 공통 유틸 ─────────────────────────
