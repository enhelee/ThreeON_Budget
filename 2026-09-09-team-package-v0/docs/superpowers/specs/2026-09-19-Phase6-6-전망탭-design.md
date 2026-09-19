# Phase 6-6 설계 — 5번 탭 실구현 (3·4단계 API · iframe 제거 · 엑셀 import 승계)

> 작성 2026-09-19 · 전제 [6-1 계약](2026-09-19-전망포팅-계약.md) · [통합웹앱 §9](2026-09-12-통합웹앱-design.md) · 상태 층 PR #24(6-5)
> 사용자 결정(2026-09-19): ① 3단계 모집단 = **마감된 연도만** ② 기준연도는 **5번 탭 자체 선택기**

## 1. 목표

Streamlit iframe 을 걷어내고, 표준화(3단계)·중장기 전망(4단계)을 **이 앱의 DB·화면·세션 안에서** 돌린다. 계산부(`benchmark`·`forecast_calc`)와 상태 층(`forecast_store`)은 이미 있다. 이번에 만드는 것은 **입력 조립 → 계산 → 화면** 의 세 층과 엑셀 import 4종이다. 엑셀 **내보내기**는 6-7.

## 2. 입력이 어디서 오는가 — v2 와 다른 두 곳

| 입력 | v2 | budget_app (이번) | 근거 |
|---|---|---|---|
| 과년도 실적 (사업장, 연도, 예산과목, 금액) | checkpoint JSON 또는 `classified_*.csv` | **마감된 연도**의 최신 분석 결과 `biz_line` 중 구분 ∈ {계획집행, 신규, 신규(소액집행)} | 6-3 기준선 테스트가 이미 이 모집단을 쓴다. 마감 = 대외 보고에 쓴 확정값 |
| 당해년도 예산계획 | `budget_{연도}.csv` (부서코드 → 표시명 해석) | **1단계 계획본** `plan_row`(base_year). 처지사가 이미 정규화돼 있다 | 어댑터가 v2 열 이름(`예산귀속 \n부서코드`·`연예산 합계`)으로 맞춰 계산부를 안 고친다 |
| 지사 목록 | 정비등급 이력의 사업장 | **`dept_config(base_year)` 의 포함 지사 중 본사 그룹 제외** | 등급 이력이 비어도 표는 나와야 한다(지금 실데이터가 그 상태) |
| 단위 | 원 | **천원** (앱 표준) | 고온부품·본사배분 파서의 천원→원 환산을 뺀다 |

기준연도 기본값: 상태가 있는 기준연도 중 최신, 없으면 **마감 최신연도 + 1**(지금은 2026).

## 3. 백엔드

### 3.1 `src/budget/pipeline_forecast.py` — 입력 조립과 실행 (UI 비의존)

```
locked_actuals(conn)            -> (df[사업장,연도,예산과목,금액], years_used)
budget_plan_for(conn, base_year)-> v2 모양 DataFrame (없으면 빈 DF)
forecast_sites(conn, base_year) -> [지사…]  (dept_config, 본사 제외, 포함만)
run_benchmark(conn, base_year)  -> {rows, years_used, population, has_ltsa}
run_forecast(conn, base_year)   -> {sites, years, tables{site: rows}, total_rows, notes}
```

`run_*` 는 `forecast_store.bind_site_resolvers(conn, base_year)` 를 먼저 부른다. 결과는 저장하지 않는다 — 22개 지사 × 17행 × 10년은 요청마다 계산해도 1초 안이다(설계서 §4.1 의 `forecast_line` 표는 6-6 에서 만들지 않는다, YAGNI).

### 3.2 `forecast_calc` 파라미터화 (계약 §6)

`year_multiplier(year, factors, base_year=BASE_YEAR)` · `compute_site_table(..., base_year=BASE_YEAR, years=None)` · `compute_all_sites(..., base_year=BASE_YEAR, years=None)`. 기본값이 2026 이라 v2 승계 테스트 18개는 그대로 통과한다. `FORECAST_YEARS` 는 `forecast_years(base_year)` 로 만든 10개년.

### 3.3 `src/budget/forecast_import.py` — 엑셀 파서 4종 승계

| v2 | 여기 | 변경 |
|---|---|---|
| `standardization.import_grade_history_from_workbook` | `grades_from_workbook(bytes, site_names)` | 시트명 → 지사명 매핑을 `site_type_map` 대신 **dept_config 지사 이름**에서 만든다(«지사»·«사업소» 접미어 제거 규칙 동일) |
| `longterm_forecast.import_schedule_from_workbook` | `schedule_from_workbook(bytes, site_names)` | 같음 |
| `longterm_forecast.import_hot_parts_from_workbook` | `hot_parts_from_workbook(bytes, site_names)` | **천원 그대로**(×1000 제거) |
| `longterm_forecast.import_hq_master_from_workbook` | `hq_master_from_workbook(bytes, site_names)` | 같음. 반환 (master_wide, ratio) |

파서는 **미리보기용 파싱만** 한다 — 저장은 화면이 확인 뒤 PUT 으로. v2 파서 테스트 6개를 승계한다(단위만 바꿔).

### 3.4 API — `src/budget/api_forecast.py` (APIRouter, `server.py` 가 include)

`server.py` 는 1,480줄이라 여기에 300줄을 더 얹지 않는다. 라우터 파일 하나로 분리하되 `_conn`·`_clean_json`·`_guard_unlocked` 는 server 의 것을 주입받는다(설계서 §10 «라우터 분리는 Phase 6 이후»는 전면 분리를 뜻하고, 새 라우트를 새 파일에 두는 것은 그 반대가 아니다).

| 메서드 · 경로 | 요지 |
|---|---|
| `GET /api/forecast/base-years` | `{base_years, default, locked_years}` |
| `POST /api/forecast/copy-base-year` | `{from_year, to_year, overwrite}` — `base_year_is_untouched` 아니면 409 (config copy-year 와 같은 계약) |
| `GET /api/forecast/state?base_year=` | 상태 9종 전부. hq_master 는 `{columns, rows}` (넓은 표) |
| `PUT /api/forecast/state/{table}` | `{base_year, rows}` — `grades·methods·overrides·factors·hot-parts·hq-ratio·hq-temp·surprise`, `hq-master` 는 `{base_year, columns, rows, ratio_rows}`. 그 기준연도 한 벌 통째 교체 |
| `POST /api/forecast/import?kind=&base_year=` | `kind ∈ grades·schedule·hot-parts·hq-master`. 파일 → 파싱 결과만 반환(저장 안 함) |
| `GET /api/forecast/benchmark?base_year=` | 3단계 결과 |
| `GET /api/forecast/table?base_year=` | 4단계 결과 |

마감 가드: 전망 상태는 **기준연도가 마감 대상이 아니다**(마감은 분석 연도의 개념). 가드 없음. 감사 로그는 미들웨어가 PUT/POST 를 자동으로 남긴다.

`/healthz` 의 `forecast_url` 과 `FORECAST_URL` 은 지운다. Caddy `/forecast` 블록·supervisord 는 6-8 까지 그대로(동료분 확인 전).

## 4. 프론트 — `web/src/views/forecast.js` 재작성

상단: **기준연도 선택기 + ＋기준연도**(직전 복사, 409 시 안내) + 「마감 연도 N개(2023·2025) 실적 기준」 표시.

세 하위 탭(`state.fc.tab`):

| 탭 | 내용 | v2 대응 |
|---|---|---|
| **기준정보** | 정비등급(지사×연도 넓은 표 편집 + 엑셀 가져오기: 표준화 참고·정기점검 일정) · 고온부품(표 + 가져오기) · 본사 원가분배(표 + 가져오기) · 팩터(행 추가·삭제·활성) · 본사 임시사업(추가·삭제) · 지사 돌발사업(추가·삭제) | 두 페이지의 관리 섹션 6개 |
| **표준화** | (지사·구분·과목·등급·산출방식[select]·방식출처·추천사유·표준금액[input]·비고) 표. 방식 바꾸면 `methods`, 금액 바꾸면 `overrides` 로 저장. 지사그룹 필터 | `_render_standardization` |
| **중장기 전망** | 지사 선택 → 17행 × 10년 표 + 전사 합계 표. 계획본 없으면 «투자비 0·당해년도 표준화 대체» 안내 | `_render_compute_and_export` 의 미리보기 |

편집 패턴은 「연도 기준정보」와 같다 — `data-fc` 입력을 상태에 담고 표별 dirty 로 저장 버튼에서 PUT. 가져오기는 파일 → `POST import` → 미리보기 표 → 「적용(기존에 없는 것만 추가 / 전체 교체)」 → PUT. 하단에 「(구) 전망 앱 새 탭에서 열기」 링크만 남긴다(6-8 에서 제거).

`main.js` 의 클릭·change 핸들러에 `data-fc*` 분기를 더한다. `home.js` 의 STAGE 04 카드와 «이음새(JSON 연계)» 문구를 새 흐름(«마감 실적 → 표준화 → 전망»)으로 고친다.

## 5. 테스트

| 파일 | 고정하는 것 |
|---|---|
| `tests/test_pipeline_forecast.py` | 마감 연도만 모집단 · 열린 연도 제외 · 계획본 어댑터 열 이름 · 지사 목록(본사 제외) · run_forecast 가 10년×지사 표를 낸다 |
| `tests/test_forecast_import.py` | v2 파서 테스트 6개 승계(천원) + dept_config 시트명 매핑 |
| `tests/test_forecast_api.py` | base-years 기본값 · state PUT/GET 라운드트립(9종) · copy 409 · import 미리보기 · benchmark/table 가 마감 run 을 읽는다 · `/healthz` 에 forecast_url 없음 |
| `tests/test_forecast_calc.py` 추가 | `base_year=2027` 이면 2027 이 1.0 배, 열이 2027~2036 |
| 기존 | 202 + 전망 앱 183 유지 · `test_deploy_config` 무변(Caddy 는 6-8) |

브라우저 실측(로컬 `DATABASE_URL=" "` + 실DB 사본): 기준연도 2026 생성 → 팩터 편집 저장 → 표준화 표 · 전망 표가 뜬다 → 새로고침 후 값 유지 → 화면 캡처.

## 6. 범위 밖 (그대로 둠)

- 엑셀 내보내기 4종(표준화 양식·중장기 양식·현재값 양식 다운로드·재무팀 양식) → **6-7**
- Streamlit·Caddy·supervisord 삭제 → **6-8** (동료 확인 후)
- Test 모드(v2) — 이관 안 함(설계서 §9.2)
- 시나리오(기준·보수·적극, 설계서 §3.4)·`factor_set` 해시·`forecast_line` 영속 — 고도화 항목. 지금 팩터가 기준연도별로 남으므로 재현성은 기준연도 단위로 확보된다.
- 알고리즘 약점 3(표본 2개·계층 후퇴·등급 공백) — 기준선 문서 §5

## 7. 완료 기준

iframe·`FORECAST_URL` 부재 · 5번 탭 세 하위 탭이 실DB 사본에서 동작 · 상태가 새로고침·재배포 뒤 남음(DB) · 테스트 전부 통과 · 브라우저 캡처.
