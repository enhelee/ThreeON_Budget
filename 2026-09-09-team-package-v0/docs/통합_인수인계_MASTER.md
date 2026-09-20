# 예산·실적 분석 시스템 — 통합 인수인계 MASTER

> **이 문서가 진입점입니다.** 다른 컴퓨터에서 Claude Code로 이 프로젝트를 분석·통합할 때 이 파일부터 읽으세요.
> 작성: 2026-08-04 (rev13) · **현행화 2026-09-21 (Phase 7)** · 상태: **1~5단계(계획·실적·분석·통계·전망) 웹 앱 하나, 테스트 269 passed, Render 배포 운영 중**
>
> **[2026-09-21 · Phase 6·7 이후 읽는 법]** 아래 본문은 rev13(2026-08-04) 기준으로 쓴 것이라 **분석 로직(§4)·DB(§5)·총액 보존 불변식·주의사항(§9)은 그대로 유효**하지만, 다음은 달라졌다:
> - **앱은 하나다.** 3·4단계(표준화·중장기 전망)는 Phase 6(2026-09-19~20)에서 동료 전망 앱(v2)을 흡수해 **5번 탭**이 됐다(`/api/forecast/*`, 입력은 마감 연도의 `biz_line` 을 DB 에서 직접). v2 앱·Caddy·Streamlit·supervisord 는 삭제됐고 컨테이너는 uvicorn 하나다.
> - **v2 로 넘기던 것은 전부 사라졌다.** 결과 JSON·CSV(`/api/export-team`)·`spec_io`·`v2_model_sync` 는 Phase 7 에서 삭제. 계약은 [연계계약_CONTRACT.md](연계계약_CONTRACT.md) 하나.
> - **프론트는 Vite SPA**(`app/web/src/`, 빌드 산출 `app/static/`) — §7 의 `webapp/index.html`·CSS 함정은 Phase 1 이전 이야기다. 지금은 Tailwind 를 정상 빌드한다.
> - **구성(지사·과목·별칭)은 파일이 아니라 DB**(연도별 기준정보, `config_store`). §2 의 `config/*.json` 은 없다.
> - **DB 는 SQLite 또는 PostgreSQL**(`DATABASE_URL`, `dbcore`). 운영은 Supabase PG, 사내 이관은 [사내이관_가이드.md](사내이관_가이드.md).
> - 인증·감사(`auth.py`, `audit_log`)·모델 레지스트리(`ml_registry.py`)·마감(`year_lock`)은 rev15~ 에 추가됐고 유효.
> - 팀원용 요약은 [팀공유_최종안내.html](팀공유_최종안내.html)(Phase 7), 실행법은 [팀원_실행가이드.md](팀원_실행가이드.md).
>
> **[rev14 · 2026-09-08 팀 병합 / rev15 · 2026-09-09 배포 준비]** 당시 기록은 [변경이력_CHANGELOG.md](변경이력_CHANGELOG.md) 참조.

---

## 0. 이관 체크리스트 — 이것만 복사하면 됩니다

| 우선순위 | 대상 | 내용 |
|---|---|---|
| **필수** | `budget_app/` 폴더 전체 | 코드 + **data/budget.db(모든 데이터)** + config + webapp + tests |
| **필수** | 루트 `*.md` 문서 | 이 파일, 변경이력_CHANGELOG.md, 알고리즘_명세.html |
| 권장 | 바탕화면 `예산과목.xlsx`, `부서코드.xlsx` | 마스터 원본(내용은 이미 DB에 들어 있음 — 재갱신용) |
| 권장 | `표준화 검증 자료(23년)/` 폴더 | 23년 원본·수기 정답지(회귀검증용) |
| 참고 | 루트 `zrfm2.XLSX`, `양식1_월별_템플릿(25년 계획분)_R1.xlsx` | 25년 원본(내용은 이미 DB에 흡수됨) |
| 참고 | `PRD_V1.html`, [`연계계약_CONTRACT.md`](연계계약_CONTRACT.md) | 파일·인터페이스 계약(2026-09-20 통합본) |

**핵심: `budget_app/data/budget.db` 하나에 모든 원자료·분석결과·사용자 확정·학습이 들어 있습니다.**
이 파일만 있으면 업로드했던 Excel 원본 없이도 전부 재현됩니다.

> **이관·백업 직전에 반드시 2단계를 실행하세요** (반복 재분석으로 `match_line`/`biz_line`이 누적됩니다):
> ```bash
> cd budget_app
> py scripts/db_정리.py          # 최신 run만 남기고 VACUUM (원본·사용자 확정 데이터 무손실)
> py scripts/make_db_snapshot.py # docs/DB_스냅샷.md 최신화
> ```
> 2026-08-04 16:22 기준 정리 전 **101.9MB** → 정리 후 약 20MB.

새 컴퓨터에서 실행:
```bash
cd budget_app
py -m pip install -r requirements.txt
py -m uvicorn server:app --port 8010        # 또는 분석프로그램_실행.bat 더블클릭
# → http://localhost:8010
py -m pytest -q                             # 71 passed 확인
```

---

## 1. 프로젝트 개요

**목적**: 발전플랜트 유지보수 예산의 4단계 자동화
① 예산 계획 수립 → ② 실적 집계·사업 매칭 → ③ 예산 표준화(벤치마크) → ④ 중장기(10개년) 예측

**현재 구현**: ①~④ 전부 — 검토·수정·학습 웹 시스템 + 5번 탭 표준화·중장기 전망(Phase 6). 표본은 마감 연도 2개(2023·2025)라 얇다 — 알려진 한계.

**검증 상태**: 23년(수기 분석본 대비 손익 −0.06%)·25년 실데이터로 전 과정 검증.
23·25년 모두 **미매핑 0 · 종합표 = ERP 전체**로 마무리, 확정 결과 학습 완료(10,888건).

**보안 설계**: 업로드 파일은 행 단위로 SQLite에 흡수 후 즉시 삭제(원본 미보관).
프론트(정적 HTML)는 API 응답만 표시. 외부 전송 없음(로컬/사내망 전용).

---

## 2. 디렉토리 구조 (2026-09-21 현재 — 저장소 `2026-09-09-team-package-v0/`)

```
2026-09-09-team-package-v0/
├─ README.md                    저장소 진입점 · 로컬 실행 · 배포
├─ .env.example                 환경변수 예시 (로컬은 app/.env, Docker 는 루트 .env)
├─ app/                         ★ 애플리케이션 본체 (FastAPI + Vite SPA)
│  ├─ server.py                 API 전체 + 정적 서빙 + 보안 헤더·gzip 미들웨어
│  ├─ src/budget/               도메인 로직 — normalize·matching·pipeline_* · db/dbcore · auth · config_store ·
│  │                            ml_registry · benchmark·forecast_calc·forecast_store·pipeline_forecast·
│  │                            forecast_import·forecast_export·api_forecast (5번 탭)
│  ├─ web/src/                  프론트 원본 (views/ 10화면 · router · data · state)
│  ├─ static/                   빌드 산출물 — 커밋하지 않음 (npm run build)
│  ├─ templates/                내장 양식 3종 (사업별예산 · 표준화 · 중장기예산)
│  ├─ tests/                    pytest 269
│  ├─ scripts/                  db_check(PG 접속·이전) · db_정리 · make_db_snapshot · make_business_template
│  └─ data/ output/ .env        로컬 상태·비밀 — 커밋하지 않음
├─ deploy/                      Dockerfile · entrypoint.sh · docker-compose.yml · requirements.txt · onprem/(사내 반입 스크립트)
└─ docs/                        이 문서 · 연계계약_CONTRACT · 배포가이드 · 사내이관_가이드 · 보안설계 · 팀원_실행가이드 ·
                                학습데이터_모델_관리 · DB_스냅샷 · 변경이력_CHANGELOG · 팀공유_최종안내.html · superpowers/(설계·계획)
```

옛 트리(바탕화면 `중장기 예산 소요 전망/` 의 `budget_app/`·`webapp/`·`config/`·v2 폴더)는 rev13 시절 것으로, 저장소로 옮기며 위 구조가 됐다.

## 3. 아키텍처

```
[브라우저 SPA]  webapp/index.html (정적, 원자료 미보유)
      │ REST (JSON)
[FastAPI]  server.py :8010
      │
[분석 엔진]  src/budget/pipeline_db.py → pipeline_actual.py → matching.py
      │
[SQLite]  data/budget.db  (원자료·결과·사용자확정·학습·마스터·마감)
      │
[산출물]  output/*.xlsx, *.csv  (Excel export)
```

### 저장 / 분석 / 학습 3분리 (rev13 — 성능 설계의 핵심)

수정할 때마다 전체 재분석을 돌리면 매번 30초가 걸렸다. 프로파일링 결과 **그 시간의 63%가
Excel 산출물 생성**(zrfm2_V1 8.2초)이었다. 그래서 세 가지를 분리했다.

| 기능 | 트리거 | 하는 일 | 실측 |
|---|---|---|---|
| **저장** | 재배정·✎수정·삭제·사업추가 | 지시 테이블에 기록만. 재분석·학습 안 함 | **0.04초** |
| **분석 반영** | 헤더 `분석 반영 (N)` 버튼 | 손익+자본 매칭 + run 기록. **파일은 안 만듦**(`make_files=False`) | 16~19초 |
| **AI 학습** | 설정 탭 `[AI 학습]` 버튼 | `learn_from_year` 일괄 학습 | 수초 |
| 산출물 파일 | 내보내기 클릭 | 없거나 최신 run보다 오래됐을 때만 생성(`record_run=False`) | 첫 34초 → 이후 0.23초 |

- `GET /api/pending?year=`이 "최신 run 이후 저장된 지시 건수"를 세어 배지·미반영 바를 띄운다.
- **주의**: 내보내기용 재생성은 반드시 `record_run=False`. 새 run을 남기면 방금 만든 파일이
  곧바로 'run보다 오래됨'이 되어 **매 다운로드마다 재생성**된다(rev13에서 실제로 겪고 고친 버그).
- 권장 작업 순서: ① 수정·저장 여러 건 → ② 분석 반영 1회 → ③ AI 학습 → ④ 연도 마감.

- 업로드 → `db.ingest_plan/ingest_erp`(행 단위 저장, 임시파일 삭제)
- 분석 실행 → `pipeline_db.run_actual_db(year, budget)` — 손익·자본 각각, DB의 최신 데이터셋 + 오버라이드 + 학습 + 사업수정 + 수동사업을 모두 반영해 실행하고 run/match_line/biz_line 기록 + Excel 산출
- 조회 → 최신 run의 biz_line(사업 단위) + match_line(전표 단위) 조인
- **수정은 전부 "지시 테이블"에 저장 후 재분석으로 반영** (원자료 불변):
  - `override` 전표 재배정(+`target_dept`=타지사 이동)
  - `biz_edit` 사업 내용 수정 — **사업명·속성·주관부서명·부서(부)·처지사·연예산·예산과목**
  - `manual_biz` 사업 추가 / `biz_delete` 사업 삭제(=분석 제외)
  - 원본 `plan_row`/`erp_row`는 절대 수정하지 않는다 → 이력을 지우면 항상 원상복구되고, 승인 계획본과의 대조 기준선이 유지된다.

---

## 4. 분석 로직 (핵심 — src/budget/)

전체 판정은 **결정적 규칙기반 + 문자열 유사도(rapidfuzz WRatio)**. 재현 가능, 감사 추적 가능.
상세 시각 문서: 루트 `알고리즘_명세.html`.

### 규칙 요약 (구현 위치)
| 규칙 | 내용 | 위치 |
|---|---|---|
| R1 | zrfm2 마지막 **합계행 제외** (계정·과목·전표번호 모두 빈 행) | erp_loader.tag_excluded |
| R2 | **타연도 전표 제외** (기간/연도 ≠ 선택연도; 해당연도 없으면 미적용+경고) | erp_loader.tag_excluded |
| R3 | 예산과목 정규화: 계정코드→마스터 표준명→별칭(개명 통일) | normalize + item_master |
| R4 | 처지사 정규화: 별칭(`"I열\|J열"` 복합키 포함)→정확→괄호제거→접두→유사도90→J열 텍스트 탐지→**본사+J열없음→플랜트기술처**(사용자 확정 규칙). 실패=미매핑 보고 | matching.normalize_erp_df |
| R5 | 매칭 후보 = **같은 (예산과목×처지사)의 계획행**만 | matching.match_actuals |
| R6 | **참조전표번호 묶음** = 한 내역, \|금액\| 최대 전표 텍스트가 대표(인지세가 본 대금을 따라감) | matching |
| R7 | 대표 텍스트 vs 계획 사업명 WRatio 최고점 귀속(동점=연예산 큰 행) | matching |
| R8 | 그룹정책: 계획행 있으면 저유사도 임의귀속 표시, 없을 때만 신규 | matching |
| R9 | 확신도 = 유사도/100 (<0.8 검토대상, 수동=1.0, 학습=0.99) | matching |
| R10 | 신규는 텍스트 유사도 ≥80 클러스터링(상쇄± 순액, 무텍스트끼리 병합) | matching |
| R11 | 클러스터 순액 ≤2,000천원 → "{지사} {과목} 집행" 소액 일괄 | matching |
| R12 | **오버라이드**: 전표묶음을 지정 사업으로(타지사 이동 = target_dept로 처지사 교체 후 매칭) | matching + db.override |
| R13 | **사업 통째 이동**: 계획행은 `biz_edit.처지사`, 귀속 전표는 `override.target_dept` — **둘 다 매칭 전에** 적용해 새 지사에서 다시 만나므로 계획집행 관계·확신도 유지 | pipeline_actual + matching |
| R14 | **사업 삭제**: `biz_delete`의 (과목,지사,사업명)과 일치하는 계획행을 매칭 전 제외(원본 보존→이력 삭제로 복구). 제외분은 검토리포트 `계획행제외`에 "관리자 사업 삭제"로 공시 | pipeline_actual |
| R15 | **개명 참조 동기화**: 사업명 변경 시 그 이름을 가리키는 `override.target_name`·`learned_match.사업명`을 함께 이동(override는 최신 run의 match_line으로 과목·지사 범위 한정) — 하지 않으면 동명 신규 사업이 따로 생겨 **중복 행**이 됨 | db.rename_biz_references |
| 연예산·과목 | `biz_edit`의 `연예산`(천원)·`예산과목`을 매칭 전 계획행에 덧씌움. 과목은 같은 예산구분 내에서만(타예산 과목으로 옮기면 양쪽 run에서 제외돼 행이 사라짐). 전표 과목은 ERP 계정코드가 정하므로 **귀속 전표는 옛 과목에 신규로 남음** | pipeline_actual |
| 학습 | (과목, 텍스트정규)→사업명 맵을 유사도보다 **우선** 적용. 재배정 저장 시 자동 축적(수동확정), 설정 탭 일괄 학습(자동확정). **전 연도 공용 1개** | db.learned_match + matching |
| 속성 | 계획 속성이 4종(일반/제조/건가/자산) 아니면 마스터로 교정, 신규행도 채움 | pipeline_actual |
| 처지사보정 | 계획행 처지사가 미등록이면 부서코드 마스터로 채움 | pipeline_actual |
| 마감 | year_lock 연도는 업로드/분석/수정 HTTP 423 차단(조회·export 허용) + 산출물 스냅샷 `output/마감/{연도}/` | server |

### 총액 보존 불변식 (모든 검증의 기준)
```
종합표 반영(계획집행+신규) + 미반영(미매핑·미선택·미분류) + 타예산 + 제외(합계행·타연도) = ERP 전체
```

### 파일별 역할
- `loaders.py` 계획 xlsx 파싱(양식1(월별), 헤더3행) / `erp_loader.py` zrfm2 파싱(+합계행·연도 태깅)
- `normalize.py` 과목·처지사·텍스트키 정규화 / `config_store.py` 구성·별칭·시드(+to_bool NaN 가드)
- `matching.py` **매칭 엔진 본체** (R5~R12, 학습 적용)
- `pipeline_actual.py` 오케스트레이션(스코프 분리·속성교정·biz_edit·manual_biz 적용·요약·Excel)
- `pipeline_db.py` DB 입출력 래퍼(오버라이드·학습·마스터 로드→실행→run 기록)
- `db.py` **SQLite 계층 전부**(스키마·ingest·학습·마감·수동데이터)
- `excel_actual_writer.py` 산출물 3종(실적.xlsx=Sheet1+종합표SUMIFS+검토리포트 / zrfm2_V1 / matched CSV)
- `pipeline_plan.py`+`excel_plan_writer.py` 1단계 계획본 생성(레거시 Streamlit 탭에서 사용)
- `spec_io.py` 팀 연계 파일 어댑터(연계계약_CONTRACT §3.4 구현 — 소비자였던 동료 앱은 사라짐, 외부 도구·감사용 유지)

---

## 5. DB (data/budget.db) — 상세는 `budget_app/docs/DB_스냅샷.md`

| 테이블 | 내용 | 성격 |
|---|---|---|
| dataset / plan_row / erp_row | 업로드 원자료(연도별, 최신 dataset 사용) | **원본 — 보존 필수** |
| override | 전표 재배정(사업명·target_dept) | **사용자 확정 — 보존 필수** |
| manual_biz | 수동 추가 사업 | **사용자 확정 — 보존 필수** |
| biz_edit | 사업 내용 수정(사업명·속성·부서·**처지사·연예산·예산과목**) | **사용자 확정 — 보존 필수** |
| biz_delete | 사업 삭제(=분석 제외) 기록 | **사용자 확정 — 보존 필수** |
| learned_match | 학습 맵(과목,텍스트정규→사업명; 수동확정>자동확정) | 확정 — 보존(자동확정은 재생성 가능) |
| item_master / dept_master | 예산과목(457)·부서코드(83) 마스터 | 기준정보 |
| year_lock | 연도 마감 | 상태 |
| run / match_line / biz_line | 분석 실행 이력·전표별·사업별 결과 | **재생성 가능** (분석 재실행) |

현재 데이터: 2023(계획 1,302행·ERP 9,850행)·2025(계획 1,700행·ERP 14,290행), 학습 10,888건, 마감 없음.
검증 기준치(재분석 시 재현되어야 함): **DB_스냅샷.md §6** 참조.

---

## 6. API 명세 (server.py)

| 메서드 | 경로 | 기능 |
|---|---|---|
| GET | `/` | 프론트(index.html) |
| POST | `/api/upload/plan?year=` · `/api/upload/erp?year=` | 계획/zrfm2 업로드(멀티파트)→DB 흡수 |
| POST | `/api/upload/master?kind=item\|dept` | 마스터 갱신 |
| POST | `/api/analyze` {year, policy} | 손익·자본 일괄 분석(**16~19초**, Excel 미생성) |
| GET | `/api/pending?year=` | **분석 미반영 변경 건수**(재배정/수정/삭제/추가) + 학습 대기 건수 |
| GET | `/api/status?year=` | 데이터셋·최신 요약·잠금·마스터·과목구성 |
| GET | `/api/overview` | 전 연도 요약(홈 다년도) |
| GET | `/api/branches?year=` | 전지사 계획/실적(+미매핑 가상지사 `"{원문} (미매핑)"`) |
| GET | `/api/branch-detail?year=&branch=` | 사업 목록+전표 트리(원 단위, 전표=과목·번호·텍스트·전기일·금액원·확신도) |
| POST/GET/DELETE | `/api/override` · `?year=` · `/{id}` | 재배정(저장 시 **자동 학습**; target_dept=타지사 이동) |
| POST/GET/DELETE | `/api/manual-biz` | 수동 사업 추가 |
| POST/GET/DELETE | `/api/biz-edit` · `/api/biz-edits?year=` · `/{id}` | 사업 내용 수정(즉시 패치+영구). 허용 필드=사업명/속성/주관부서명/부서부/**처지사/연예산/예산과목**. 개명 시 override·learned 자동 동기화 |
| POST/GET/DELETE | `/api/biz-delete` · `/api/biz-deletes?year=` · `/{id}` | 사업 삭제(분석 제외) / 이력 / **되돌리기** |
| POST/GET/DELETE | `/api/learn` {year} · `/api/learned` | 일괄 학습 / 상태 / 초기화 |
| POST/DELETE | `/api/lock` {year} · `/api/lock/{year}` | 연도 마감(+산출물 스냅샷) / 해제 |
| GET | `/api/export?...` | **없거나 오래됐으면 그때 파일 생성** 후 전송(첫 34초 → 이후 0.23초) |
| GET | `/api/stats?year=` · `/api/stats-compare?year=` | 과목·지사그룹 통계 / 전년 대비 증감 |
| GET | `/api/export?year=&budget=&kind=actual\|v1\|matched` | Excel/CSV 다운로드 |

잠금 연도에 대한 변경 API는 **HTTP 423**.

---

## 7. 프론트 (webapp/)

### 수정 방법 (rev12에서 정정)

**`webapp/index.html`을 직접 수정한다.** 서버가 `FileResponse`로 이 파일을 그대로 서빙하므로
**브라우저 새로고침만으로 반영**된다(서버 재시작 불필요 — 재시작이 필요한 건 `server.py` 변경뿐).
`body.template.html`은 `index.html`의 `<body>` 사본이므로 수정 후 아래 한 줄로 동기화한다(Git Bash):

```bash
# budget_app에서 실행 — index.html의 <body>부터 끝까지를 template로 복사(마지막 빈줄+</html> 제외)
sed -n '/<body/,$p' webapp/index.html | sed '/^<\/html>$/d' \
  | sed -e :a -e '/^\n*$/{$d;N;};/\n$/ba' > webapp/body.template.html
```

### ⚠⚠ CSS 함정 — 새 유틸리티 클래스는 동작하지 않는다

`index.html`의 `<style>`은 **프로토타입 HTML에서 미리 컴파일된 Tailwind 서브셋**이고
**런타임 Tailwind가 없다**(CDN·스크립트 없음). 따라서 **원본에 없던 유틸리티 클래스를 새로 쓰면
아무 효과 없이 조용히 무시된다.**

- 실제 사고: 삭제 버튼에 `bg-red-600 text-white` → **배경 투명 + 흰 글자 = 안 보임**
- 미컴파일 확인됨: `bg-red-*` · `border-red-200` · `text-red-700/800` · `lg:grid-cols-5` · `ml-auto` · `max-w-xl`
- 존재함: `text-red-600` · `text-white` · `btn-primary/secondary` · `text-right` · `flex-wrap` · `min-w-48` · `mb-1.5` · `lg:grid-cols-4`
- **새 스타일이 필요하면 `<style>` 안 "상세 화면 추가 스타일" 블록에 직접 CSS를 쓴다.**
  rev12에서 추가: `.btn-danger` `.btn-danger-outline` `.danger-box/-title/-text/-label` `.edit-grid` `.push-right` `.max-w-30`
- **검증법**: 브라우저에서 `getComputedStyle(el).backgroundColor` 등으로 **실제 적용 여부를 확인**한다(클래스명만 보고 판단 금지).

### 상세 표 열 폭 (실측 기준 — 임의로 줄이면 글자가 잘린다)

폰트 `.76rem`(12.16px) + 셀 좌우 패딩 11.2px 기준 필요 폭:
예산과목 150px · 전표번호 67px · 금액 85px(14자 최대) · 상태 배지 77px · 확신도 배지 50px · 헤더 '구분 ↕' 61px

| 열 | 1 구분 | 2 예산과목 | 3 속성/전표번호 | 4 사업명 | 5·6 금액 | 7 상태 | 8 확신도 | 9 수정 |
|---|---|---|---|---|---|---|---|---|
| 폭 | 4rem | **10.8rem** | 5.2rem | 나머지 | 6.2rem | 5.4rem | 4.4rem | 2.4rem |

표 `min-width:56rem`. 긴 값은 `…`로 자르지 않고 **줄바꿈**(`.cell-item`/`.cell-name` = `overflow-wrap:anywhere`),
금액·날짜(`td.text-right`)·전표번호(`.cell-doc`)는 `nowrap`.
검증 결과: 1071px·1265px 창에서 **예산과목 두 줄 0건 · 잘린 셀 0 · 가로 스크롤 없음**.

### 화면 구성

- 메뉴: 홈(다년도) / 1 예산계획(업로드) / 2 실적집계(zrfm2+분석) / 3 실적분석(전지사) / **3+ 상세** / 4 통계·내보내기(전년비교) / 5 예측(예정) / 설정(학습·마감·마스터·이력 4종)
- **3+ 상세**: 필터·정렬·사업명 검색 · 전표 트리(헤더 체크박스=그 사업 전표 전체 선택) · 재배정 바 · **✎ 사업 수정 7항목**(지사·과목·사업명·속성·주관부서명·부서(부)·연예산) · **이 사업 삭제** · ＋사업 추가 · 미시행 숨기기
- 재배정 바: `이동할 지사`를 바꾸면 **그 지사의 기존 사업 목록**을 불러옴(캐시 `state.ovBiz`), 첫 항목은 항상 `— 선택 없음 (직접 입력) —`. 입력값은 `state.det.ov*`에 보관돼 전표를 더 체크해도 유지된다.
- **주의(IME)**: 검색 입력은 `#detResults`/`#brResults`만 부분 갱신 — 전체 재렌더로 되돌리면 한글 조합이 깨짐.
- **주의(재렌더)**: `#detResults`는 전표 체크·검색마다 다시 그려진다 → 폼 입력값은 반드시 `state`에 보관할 것.

---

## 8. 검증 · 테스트

- `py -m pytest -q` → **71 passed** (약 6분. 엔진 규칙·DB 파이프라인·오버라이드·학습·biz_edit·biz_delete·manual_biz·잠금·E2E)
  - rev12 추가분: 지사 이동 즉시패치 / 사업 통째 이동(새 지사에서 계획집행·연예산·실적 동반, 구 지사 소멸, 총액 보존) / 삭제·복구 / 전표 이동 후 삭제 총액보존 / 개명 동기화 후 중복 없음 / 연예산 수정·복구 / 예산과목 변경
  - rev13 추가분: `make_files=False`가 숫자를 바꾸지 않음 / 내보내기 재생성이 run을 늘리지 않음 / 저장 시 학습되지 않고 학습 대기로 집계됨
- 실데이터 기준치: DB_스냅샷.md §6 (23년 127,984,754 / 25년 148,263,979 = 손익+자본+미반영, 천원)
- 23년 수기 분석본 대조: `output/대조_분석본vs자동분석_2023.xlsx` (손익 −0.06%)

## 9. 알려진 주의사항

1. 서버는 `--reload` 없음 — **`server.py`·`src/` 수정 후 재시작** 필요. 반면 `webapp/index.html`은 새로고침만으로 반영.
2. **프론트 CSS는 컴파일된 Tailwind 서브셋** — 새 유틸리티 클래스는 무효(§7의 CSS 함정). 반드시 `getComputedStyle`로 확인.
3. **사업 삭제(`biz_delete`)의 키는 (과목,지사,사업명)** — 동명 사업이 둘이면 둘 다 지워진다. 그래서 계획행이 없는 행(신규·미매핑)에는 삭제 기록을 남기지 않고 전표만 옮기도록 구현했다. 새 삭제 경로를 만들 때 같은 함정을 주의.
4. **사업명을 바꿀 때는 `rename_biz_references`를 반드시 함께 호출** — 안 하면 override·learned가 옛 이름을 가리켜 동명 신규 사업이 생긴다(중복 행).
5. **예산과목 변경은 같은 예산구분(손익/자본) 안에서만** — 타예산 과목으로 옮기면 양쪽 run에서 제외돼 행이 사라진다.
6. **연예산 수정은 승인 계획본과 분석 결과의 계획 총액을 달라지게 한다**(업무 리스크). 확정 연도는 설정 탭에서 **마감**해 고정할 것.
7. `manual_biz`·업로드는 **헤더 선택 연도** 기준 — 연도 확인 후 작업.
8. `config/*.json`에 NaN 저장 금지(코드가 가드하지만 수동 편집 시 주의).
9. match_line/biz_line은 run마다 누적 — 주기적으로 `scripts/db_정리.py`.
10. 학습 DB는 전 연도 공용 — 잘못 학습 시 설정 탭 초기화 후 재학습.
11. 25년 자본 원본은 속성 칸에 과목명이 들어 있음(마스터 교정으로 해결) — 새 연도 원본도 같은 문제 가능성.
12. 23년 zrfm2에는 계정 60602015(외주비-열원정기점검)가 없음 — A급정비 실적은 ERP 재추출 필요.
13. 건설공사 3과목(외주비-열원공사비 등)은 zrfm2 범위 밖 → `실적반영:false` 유지.

## 10. 다음 단계 (2026-09-21 기준)

3·4단계는 **구현 완료**(Phase 6). 남은 것은 운영·정밀화다:

- **표본 2개년의 한계** — 표준금액이 마감 연도 2개(2023·2025)로만 산출된다. 설계서 §2.4 의 계층적 후퇴(지사그룹·전사 대체)는 아직 없다 → 동료 합의 후 별도 Phase(대외 수치가 바뀜).
- **정비등급 이력** — 5번 탭 가져오기로 넣기 전까지 등급 «표준» 하나로 후퇴한다.
- **사내 이관** — 절차·스크립트 준비됨([사내이관_가이드.md](사내이관_가이드.md)), 실제 Docker 실행과 Supabase→사내 PG 이전은 일정 확정 후.
- 개인 계정 전환 · 로그인 실패 지연 · public 저장소 실데이터 정리([보안설계.md](보안설계.md) §6).

## 11. 문서 지도 (최신성)

| 문서 | 상태 |
|---|---|
| 이 문서(상단 현행화 블록) + `변경이력_CHANGELOG.md` + [팀공유_최종안내.html](팀공유_최종안내.html) + [팀원_실행가이드.md](팀원_실행가이드.md) | ★ **최신 (Phase 7, 2026-09-21)** |
| `배포가이드.md` · `사내이관_가이드.md` · `보안설계.md` · `연계계약_CONTRACT.md` | 최신 (Phase 6-8~7) |
| `budget_app/docs/DB_스냅샷.md` | 최신 — `py scripts/make_db_snapshot.py`로 언제든 재생성 |
| `알고리즘_명세.html` | R1~R12까지 시각화 — **R13~R15(이동·삭제·개명동기화)는 미반영**, 이 문서 §4 표 참조 |
| `PRD_V1.html`, [`연계계약_CONTRACT.md`](연계계약_CONTRACT.md) | 유효(계약) — 옛 4개 통합본(2026-09-20). CSV 스키마는 2026-07-22 이후 불변 |
| `HANDOFF.md` · `HANDOFF_budget_app.md` | **역사 문서**(1단계 계획본·rev13 이전) — 상단 안내 참조 |
| 개발 설계·계획 문서 | `docs/superpowers/specs/`(최신: `2026-09-12-통합웹앱-design.md`, Phase 6 계약·설계) · `docs/superpowers/plans/`(Phase 6·7 계획서) |
