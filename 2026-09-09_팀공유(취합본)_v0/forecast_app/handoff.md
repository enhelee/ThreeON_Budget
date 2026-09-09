# Handoff — 발전플랜트 유지보수 예산 분석 프로그램

최신화: 2026-08-17. 새 채팅에서 이어서 작업하기 위한 인수인계 문서(누적된 세션 로그를 이번에 현재
상태 기준으로 정리함).

## ⚠️ 가장 먼저 확인할 것

1. **커밋 안 된 작업 다수**: `git log`는 여전히 초기 2개 커밋(`842b0c0`, `3b1230b`)뿐이고, **그 이후
   만들어진 기능(예산 표준화, 중장기 예산 예측, Test 모드 전체, 배정 대비 실적 등)이 전부 미커밋
   상태**다. `git status`에 새 파일(`longterm_forecast.py`, `standardization.py`, `views/` 전체 등)이
   `??`로, 기존 파일 수정분이 `M`으로 쌓여있다. 이 리포는 **git push 권한이 없어 사용자가 직접
   커밋/푸시해야 한다** — 작업을 시작하기 전에 사용자에게 커밋 여부를 확인할 것.
2. **`git status`의 `D`(삭제) 표시 파일들**(`__pycache__/*.pyc`, `classified_2016.csv`, `data_2016.csv`,
   `temp_upload.xlsx`, `training_data.csv`, `type_classifier.joblib`, `year_status.json`)은 `.gitignore`
   정리 과정에서 의도적으로 untrack된 것들이다(문제 아님).
3. **Streamlit 앱을 실행한 채로 코드를 수정하면, 재시작 전까지는 이전 코드가 메모리에 남아있다.**
   실제로 한 번 `test_data/` 폴더 도입 후에도 루트에 `longterm_test_budget_plan.csv`가 새로 생성된
   적이 있었다(재시작 안 된 이전 프로세스가 옛 경로로 계속 저장한 것으로 추정, 지금은 `test_data/`로
   옮겨 정리함). **코드를 수정한 뒤에는 사용자에게 Streamlit 앱 재시작을 안내할 것.**

## 프로젝트 개요

- 위치: `C:\Users\User\Documents\AI\예산예측프로그램\개발중`
- Streamlit 멀티페이지 앱. 실행: `streamlit run app.py`
- **완전 오프라인(사내 분리망) 환경에서 동작해야 함** — 외부 CDN/폰트/API 호출 금지.
- 검증은 `streamlit.testing.v1.AppTest` + 실제 참고파일로 한다 — 이 환경의 스크린샷/브라우저 렌더링
  도구는 불안정(compositing 실패)하므로 AppTest 위주로 검증할 것.
- 매 변경 후 `python -m pytest tests/ -q` 전체 통과 확인. 현재 **138개 테스트 통과**.
- 검증용으로 만든 임시 파일(스크립트, 다운로드 결과 xlsx 등)은 작업 후 반드시 삭제해서 저장소를
  깨끗하게 유지할 것. `diagnose_budget_gap.py`(임시 진단 스크립트, 프로젝트 루트)는 아직 남아있음 —
  더 이상 안 쓰면 삭제할 것.

## 메뉴 구조 (`app.py`)

```
예산 계획 수립     → 예산 계획 업로드
예산 실적 집계     → 실적 업데이트(zrfm2) / 사업 매칭 / 계획 대비 실적
예산 실적 분석     → 투자유형 분류 검토 / 투자유형 학습(분류자료) / 집계 & 대시보드 / 맞춤 리포트
예산 표준화        → 예산 표준화
중장기 예산 예측   → 중장기 예산 (26-35년)
설정              → 매핑 관리
Test 모드          → 계획 및 실적 업로드 / 투자유형 예측 테스트 / 집계 & 대시보드 / 맞춤 리포트 /
                     예산 표준화 / 중장기 예산 (26-35년)
```

`PAGE_RENDERERS`는 `dict[(category, page), callable]`로 라우팅한다(같은 페이지명이 정식/Test 모드에
동시 존재하기 때문). Test 모드의 각 페이지는 정식 페이지와 **동일한 화면 구성**을 쓰되, 별도의
`render_test()` 함수와 별도 백데이터(전부 `test_data/` 폴더, `.gitignore`에 등록됨)를 사용한다.

## 핵심 모듈 지도

| 모듈 | 역할 |
|---|---|
| `mapping_config.py` | 지사코드↔지사명 변환(`get_site_display_name`), 지사유형(`get_current_site_type`), 정식 파이프라인용 `apply_mappings()`. 원시 코드로 직접 조회해 실패하면 표시명으로 다시 풀어보는 폴백 포함(아래 "지사유형 매핑" 참고) |
| `builtin_categories.py` | `ALL_ACCOUNTS`/`PROFIT_LOSS_ACCOUNTS`/`CAPITAL_ACCOUNTS`, `normalize_account_name()` — 계정과목 정규화의 단일 소스 |
| `validate_upload.py` | zrfm2 원본 엑셀 파싱·정리(합계행/KSV5/역분개/인지세/상쇄전표 처리). 정식 "실적 업데이트(zrfm2)"와 Test 모드 "계획 및 실적 업로드"가 공유 |
| `budget_upload.py` | 예산계획 엑셀(양식1(월별)/예산코드/부서코드 3시트) 파싱·검증. `budget_{연도}.csv` 저장은 `views/budget_upload_page.py`가 담당 |
| `plan_vs_actual.py` | 사업명 매칭 기준 "계획 대비 실적"(정식 메뉴) — `budget_actual_summary.py`와는 별개 화면/집계 기준 |
| `standardization.py` | 지사×계정과목×정비등급별 "표준금액" 계산(등급별평균/최근실적/N개년평균), 표준화 참고 엑셀 import/export |
| `longterm_forecast.py` | 중장기 예산(26~35년) 계산 엔진, `TEST_DATA_DIR = "test_data"` 상수(Test 모드 백데이터 폴더의 단일 출처) — 아래 상세 |
| `longterm_forecast_template.py` | 중장기 예산 엑셀 export (`builtin_template_중장기예산.xlsx` 채워넣기) |
| `budget_actual_summary.py` | 예산계획(배정)×실적을 **지사유형×계정과목** 기준으로 집계해 배정/실적/잔액/실적률 계산(사업명 매칭 불필요 — Test 모드처럼 매칭 전 데이터에도 그대로 쓸 수 있음) |
| `project_type_classifier.py` | 사업명(+예산과목) → 투자유형/투자유형세부 분류기. 기계장치·외주비 계열만 범위 안(`is_in_scope_account`) |
| `views/longterm_forecast_page.py` | 중장기 예산 예측 화면(정식/Test 모드 공용 `_render_compute_and_export`) |
| `views/dashboard_page.py` | 집계 & 대시보드(정식/Test 공용) — 실적 막대그래프 + "배정 대비 실적" 표(`_render_budget_vs_actual`) |
| `views/project_type_test_page.py` | "투자유형 예측 테스트"(직접 지정한 파일 업로드만) + 예측·검토·저장 공용 함수 `render_predict_review_and_save()`와 저장소 함수(`save_shared_actual_df`/`load_shared_actual_df`/`get_shared_actual_df`) — Test 모드 여러 화면이 공유 |
| `views/test_data_upload_page.py` | Test 모드 "계획 및 실적 업로드"(세부메뉴 맨 위) — 예산계획 업로드 + zrfm2 원본 실적 업로드(`project_type_test_page.render_predict_review_and_save()` 재사용) + 실적 연동 상태 확인 |

## 현재 동작 방식 요약 (자주 헷갈리는 부분 위주)

### 1. 중장기 예산(26~35년) — 26년 값 계산 규칙

`longterm_forecast.compute_site_table()`의 "표준화:" 라인(SITE_TABLE_LINES) 기준, **26년(BASE_YEAR)만**:

```
26년 값 = 지사 자체 몫(예산계획 확정값이 있으면 그 값, 없으면 표준화 계산값)
        + 본사 배분 몫(본사 원가분배 마스터 표, HQ_CATEGORY_TO_ACCOUNT에 있는 계정만 값이 있고 나머지는 0)
```

**합산**이며 우선순위(override)가 아니다 — 원본 "26년" 시트가 "전체 = 본사 + 지사"로 나뉘어 있는 것과
동일한 구조. `"수선유지비-건물/구축물"` 계정만 본사배분 라벨이 `"건물/구축물"`(접두어 없음)이라 표기가
달라서 `STANDARDIZED_ACCOUNT_TO_HQ_LABEL` 별칭으로 따로 매칭한다. 27년 이후는 표준화 금액 × 팩터
복리로 기존 로직 그대로.

### 2. "배정 대비 실적" (집계 & 대시보드)

`budget_actual_summary.py`가 지사유형×계정과목 기준으로 배정(예산계획)과 실적을 각각 집계해 합친다.
`plan_vs_actual.py`(사업명 매칭 기준, "계획 대비 실적" 정식 메뉴)와는 **완전히 다른 화면/집계 기준**이며
사업 매칭 단계가 필요 없다. 정식/Test 모드 둘 다 `views/dashboard_page.py`의 `_render_budget_vs_actual()`
공용 헬퍼를 쓴다.

### 3. Test 모드 데이터 흐름

- 모든 Test 모드 백데이터는 `test_data/` 폴더 하나에 모인다(`.gitignore` 등록, `longterm_forecast.TEST_DATA_DIR`가
  단일 출처). 폴더 안: `longterm_test_actuals.csv`(표준화 참고 실적), `longterm_test_budget_plan.csv`(예산계획,
  "중장기 예산 Test"와 "계획 및 실적 업로드"가 공유), `project_type_test_actual.csv`(투자유형 예측 테스트/
  zrfm2 업로드 확정 결과).
- 실적 확정 결과는 `project_type_test_page.get_shared_actual_df()`로 어디서든 읽는다 — 이번 세션에 방금
  확정한 값(세션 상태)이 있으면 그걸, 없으면 저장된 파일로 대체(재접속해도 다시 안 올려도 됨).
- zrfm2 원본 실적 업로드는 **"계획 및 실적 업로드"에서만** 한다("투자유형 예측 테스트"는 이미 정리된
  파일에서 칸을 직접 지정하는 용도로 남음). 둘 다 예측·검토·저장은 같은 함수
  (`project_type_test_page.render_predict_review_and_save()`)를 공유한다.
- **범위 밖(손익예산 등, 기계장치·외주비가 아닌) 계정과목도 실적 자체에는 포함된다** — 투자유형
  예측만 안 하고 빈 값으로 둘 뿐, 금액은 "배정 대비 실적" 등에 그대로 집계된다(예전엔 통째로 삭제돼서
  손익예산이 실적에서 누락되는 버그가 있었음, 수정됨).

### 4. 지사유형 매핑 — 원시 코드 vs placeholder 주의

`site_type_map.csv`에는 두 종류의 행이 섞여 있을 수 있다: (a) 설정 화면에서 정식으로 입력한 행(표시명이
실제 지사명), (b) "사업장 코드 가져오기"로 등록만 하고 표시명을 안 채운 **placeholder**(표시명이 코드
그대로, 예: `사업장="4040.0", 표시명="4040.0"`). 사용자 환경에 이런 placeholder가 20개 있었고 전부
`지사유형="중대형CHP"`로 잘못 채워져 있어서, 실제로는 DH/소형CHP인 지사의 실적이 전부 중대형CHP로
잘못 집계되는 버그가 있었다(정식 "집계 & 대시보드"에도 영향).

**수정 완료**: `_resolve_site_type()`가 placeholder 행을 lookup에서 제외하고, `get_current_site_type()`/
`apply_mappings()`는 원시 코드 직접 조회가 "미매핑"이면 `get_site_display_name()`으로 표시명을 먼저
구한 뒤 그 이름으로 다시 조회하는 폴백을 쓴다. **다만 site_type_map.csv 데이터 자체(20개 placeholder
행)는 그대로 남아있다** — 코드가 안전하게 우회하므로 기능상 문제는 없지만, 사용자가 "설정 > 매핑 관리"에서
정리하면 더 명확해진다(표시명이 사업장과 똑같은 행을 찾으면 됨).

## 알아둘 설계/제약 사항

- **`기계장치_기타기계장치` 라인 주의**: `SITE_TABLE_LINES`의 라벨(`기계장치_기타기계장치`)과 실제
  계정과목(`기계장치`)이 다르다. lookup은 항상 **계정과목**으로 키를 잡아야 한다.
- **budget_lookup 없을 때 fallback**: 예산계획에 해당 (지사,계정과목) 데이터가 없으면 0이 아니라
  표준화 계산값으로 대체된다 — 업로드 누락 시에도 값이 사라지지 않도록 하는 의도적 설계.
- `fill_total_cost_sheet()`("26년 총원가 배분")·`fill_summary_sheet()`("총괄표")는 서로 다른 라벨셋을
  매칭하는 별개 시트다. 지사별 탭(`fill_site_sheet`), 27~35년 개별 시트, 원본 "26년" 시트(전체/본사/지사
  3블록 구조, `longterm_forecast_template.py`가 아직 안 채움), 자본 "건물"/"구축물" 단독 세부 행(총괄표
  14~15행)은 여전히 범위 밖 — 원본 그대로 유지.
- **투자유형 분류기 범위**: 기계장치·외주비 계열 계정과목만 다룬다(`is_in_scope_account`). 손익예산 등
  범위 밖 계정은 예측 없이 빈 값이지만, 실적 금액 자체는 항상 포함되어야 한다(위 "Test 모드 데이터 흐름" 참고).
- **지사유형 조회는 항상 폴백을 거친다**: 원시 코드 직접 등록(연도별 이력 포함)이 최우선, 없으면 표시명
  경유. 새로운 지사유형 관련 로직을 추가할 때 이 폴백을 건너뛰지 않도록 주의.

## 다음에 할 만한 일 (사용자가 요청하지 않는 한 먼저 진행하지 말 것)

- 지금까지의 모든 변경사항을 커밋할지 사용자에게 확인. 커밋 시 `.gitignore`가 사내 실데이터 파일들을
  잘 걸러내는지 한 번 더 확인(`git status`로 스테이징될 파일 검토).
- "설정 > 매핑 관리"에서 placeholder 행(표시명이 사업장 코드 그대로인 것)들의 실제 지사유형을 확인·
  수정하도록 사용자에게 안내(코드는 이미 안전하게 우회하지만 데이터 정리 자체는 별개 작업).
- "총괄표" 자본계정 "건물"/"구축물" 단독 행을 채우고 싶다는 요청이 나오면, `본사배분:건물/구축물`
  데이터가 이미 계산되어 있으니(다만 건물/구축물 세부 분리가 안 됨) 참고할 것.
- 정식 `dashboard_page.render()`의 "배정 대비 실적"은 아직 AppTest로 직접 검증하지 못했다
  (classified_*.csv+budget_*.csv+site_type_map.csv를 모두 갖춘 통합 fixture 필요). `budget_actual_summary.py`
  자체와 `_render_budget_vs_actual` 헬퍼(정식/Test 공용)는 이미 단위 테스트로 검증됨.
- 원본 "26년" 시트(전체/본사/지사 3블록)를 실제로 엑셀에 채워 내보내고 싶다는 요청이 나오면 새 매칭
  로직이 필요함(지금은 계산 로직만 그 구조를 따르도록 되어 있고, 시트 자체는 안 채움).
- 캡처로 요청 있었던 "연도별(2023~2025) 배정/실적 추이" 다년도 비교 표는 아직 범위 밖(현재는 선택한
  연도들을 합산한 단일 기간 집계만 지원).
- 임시 진단 스크립트 `diagnose_budget_gap.py`가 프로젝트 루트에 남아있음 — 더 필요 없으면 삭제.
