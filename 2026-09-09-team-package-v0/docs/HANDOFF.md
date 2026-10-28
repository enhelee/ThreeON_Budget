# HANDOFF — 개발자 인수인계 (현행, 2026-10-28)

> **이 문서가 개발자 진입점이다.** «무엇을 왜»는 [PRD.md](PRD.md). 새 세션·새 사람이 이어받을 때 이것부터 읽고, 구조·로직·API 는 [통합_인수인계_MASTER.md](통합_인수인계_MASTER.md), 팀원용 요약은 [팀공유_최종안내.html](팀공유_최종안내.html).
> 이전에 로컬에만 두던 인수인계(2026-09-19·20·21 판)를 여기로 합쳤다. 1단계 Streamlit 시절의 옛 HANDOFF 는 [archive/](archive/) 에 있다.

---

## 0. 한 줄 상태

| 항목 | 값 |
|---|---|
| 저장소 | `enhelee/ThreeON_Budget` — 앱과 문서는 전부 `2026-09-09-team-package-v0/`(이하 «패키지»). 루트에는 `render.yaml`·`README.md`·`.gitignore` 만 |
| 앱 | FastAPI + Vanilla JS SPA **하나**. 1~5단계(계획·실적 집계·분석·통계·표준화/중장기 전망) + 설정. 프로세스 하나(uvicorn) |
| 배포 | Render 무료(Docker, **싱가포르**) + Supabase PostgreSQL(**서울** ap-northeast-2). main 병합하면 **자동 배포**(Render Events «Auto-Deploy», 빌드 40~60초 + 대기로 몇 분). **Manual Deploy 는 필요 없다.** 판별은 `/healthz` 의 `commit` |
| 테스트 | `cd app && py -m pytest -q` → **567 passed**(2026-10-28). 5~9분. PR 마다 GitHub Actions(`.github/workflows/test.yml`)도 돈다 |
| 마지막 큰 변화 | 속도 개선·CI·백업(10-15~19, #47~#50) → **종합 검토 반영(10-22, #51~#55: 보안 P1·학습 기준·PG 풀·차이 사유·이상 알림·드릴다운)** → **화면 정리(10-26, #56·#57)** → **표준화 방향 6항목·백테스트 제안·한눈에 보기(10-26, #59, rev29)** → **운영 데이터 정비(10-26, rev30: 참고 엑셀 적용·2023~2025 전표 재매핑)** → 재배정 이름 공백·학습 일괄 쓰기(10-27, rev32) → **검토 큐(10-27, rev33)** → 화면 다듬기·점진 로딩(10-27, rev34) → 질의 묶기·계산 캐시·예열(10-27, rev35) → 5번 가정 캐시(10-27, rev36) → 산점도 라벨(10-27, rev37) — [변경이력](변경이력_CHANGELOG.md) rev22~37 |
| 운영 배포 | `1caa98a`(2026-10-28, #93) — 판별은 `/healthz` 의 `commit`. 10-28 이 세션 #84·#86·#88·#90·#91·#93, 다른 세션 #85·#87·#89. 요약 [개발정리_2026-10-28.md](개발정리_2026-10-28.md)(10-27 은 [개발정리_2026-10-27.md](개발정리_2026-10-27.md)) |
| 속도(운영) | 로그인 후 화면 전환 대부분 1.2~2.7초(2026-10-27 rev36 실측, 10-15 에는 33~40초) · 5번 표준화 0.9초·전망 표 1.2초(예열) · 표는 [운영점검_2026-10-27.md](운영점검_2026-10-27.md) |
| 검증 연도 | 2023 · 2024 · 2025 모두 마감(2026-10-26 전표 재매핑 후 재마감). 2025 손익 98,554,802 · 자본 49,709,177 천원 — 재매핑 전후 동일 |
| 5번 탭 운영 상태 | 2026 기준연도: 참고 엑셀(V3_R1) 규칙 437 · 과거 등급 169 · LTSA 초안 · CRI 2 + **10-28 사용자 확정 양식** 정비등급 2026~2035(대표 187 · 설비별 90) · 고온부품 56건 502,370,807천원 · 설비용량 기본값(용량 환산 대상 양산·대구·청주·수원). 전사 10년 18,001억원. 2023 A급 정비가 ERP 원본에 없음([운영_데이터정비_2026-10-26.md](운영_데이터정비_2026-10-26.md)) |

## 1. 폴더 지도

```
2026-09-09-team-package-v0/
├─ app/
│  ├─ server.py               라우트 + 미들웨어(인증·감사·보안헤더·gzip·/assets immutable)
│  ├─ src/budget/             도메인 로직 (§4 코드 지도)
│  ├─ web/                    프론트 원본 — Vite + Tailwind 3.4 (index.html · src/ · tailwind.config.js)
│  ├─ static/                 빌드 산출물 — 커밋 안 함, Dockerfile 이 만든다
│  ├─ scripts/                운영 스크립트 — backup_pg(주간 백업·복원) · prune_history(이력 정리) · migrate_pg(DB 지역 이전)
│  │                          + 1회성(db_check · db_정리 · make_db_snapshot · make_hanan_font · restyle_sweep)
│  ├─ templates/              내장 엑셀 양식 (표준화·중장기예산 + 사용자 확정 정비등급·고온부품, 2026-10-28)
│  ├─ tests/                  pytest 567
│  └─ data/ config/ output/ .env   로컬 상태·비밀 — 커밋 안 함
├─ deploy/                    Dockerfile · entrypoint.sh · docker-compose.yml · requirements.txt · onprem/(사내 반입 스크립트)
├─ docs/                      이 문서들 (§7) · img/ (캡처) · superpowers/ (설계·계획) · archive/ (역사)
├─ .env.example · .gitignore · .dockerignore · README.md
└─ 실행_1_예산실적집계(budget_app).bat · 실행_mac.sh
```

## 2. 실행·검증 명령

```bash
cd 2026-09-09-team-package-v0/app/web && npm install && npm run build   # 프론트 수정 후 반드시 (static/ 은 커밋 안 함)
cd 2026-09-09-team-package-v0/app && py -m pytest -q                      # 567 passed
cd 2026-09-09-team-package-v0/app && DATABASE_URL=" " py -m uvicorn server:app --port 8010   # 로컬 sqlite
```

- **`DATABASE_URL` 은 공백 한 칸(`" "`)으로 비운다** — 진짜로 비우면 `.env` 의 운영 PostgreSQL 에 붙는다. `/healthz` 가 `db: sqlite` 인지 매번 확인.
- 로컬 `app/data/budget.db` 에는 마감 기록이 없다(마감은 운영 PG). 5번 탭을 실측하려면 사본에서 `POST /api/lock` 으로 2023·2025 를 마감한 뒤.
- 배포본 로그인은 팀 비밀번호가 필요하므로 Claude 가 입력하지 않는다. 운영 화면을 재야 하면 **사용자가 Aside 브라우저에서 로그인**하고 Claude 가 그 세션으로 측정한다(조회만 — 저장·업로드·분석·마감은 누르지 않는다). 측정법은 [속도개선_운영점검_2026-10.md](속도개선_운영점검_2026-10.md) §7.
- 배포 확인 순서: 병합(CI 통과 후) → 자동 배포(**몇 분 기다린다** — 1~2분 만에 보면 아직 옛 커밋이라 «안 걸렸다»고 오판하기 쉽다, 2026-10-26 실제로 그랬다) → `/healthz` 의 `commit` == 병합 커밋 → 배포 `index.html` 의 번들 해시 == 로컬 `app/static/index.html`. 배포 직후 첫 요청 한 번은 DB 스키마 확인으로 ~4초 더 걸린다.

## 3. 결정 기록 (되돌리려면 비용이 큰 것)

| 날짜 | 결정 | 근거 |
|---|---|---|
| 09-09 | 실데이터를 팀원만 접근하는 공개 URL 에 임시 운영, 최종은 사내 서버 | 검토 기간용. 공용 비밀번호 1개 + 작업자 이름 + 감사 로그 |
| 09-19 | 전망 상태 표 9종은 전부 **`base_year`(전망 기준연도) 축**, 기준연도마다 완전한 한 벌 | v2 는 2026 상수 한 벌. 27년 전망 시작 시 26년 가정을 남기려면 |
| 09-19 | 3단계 표준화 모집단 = **마감된 연도만** | 마감 = 대외 보고 확정값 |
| 09-19 | 기준연도는 5번 탭 자체 선택기, 헤더 대상연도와 독립 · 단위 **천원** | 서로 다른 축 · 앱 표준 |
| 09-20 | v2 `template_fill.py` 승계 안 함 · 양식은 기준연도로 재기준화해 내보냄 | budget_app `/api/export` 가 같은 양식 |
| 09-20 | Caddy·supervisord·Streamlit 삭제, uvicorn 하나. 보안 헤더·gzip·immutable 은 앱 미들웨어 | 옮기기 쉽고 실측 가능 |
| 09-20 | 사내 서버에서는 절대 빌드하지 않는다(이미지 tar.gz 반입, `--no-build`) | 분리망 |
| 09-20 | Render 무료 유지(Starter·Northflank·Vercel 검토 후) · `/api/export-team` 삭제 · 계층적 후퇴는 «알려진 한계» | 팀 검토 단계 |
| 09-21 | **한난 디자인 시스템 전면 적용, 사이드바 유지, 시안 브랜드 규칙(주요 버튼 = 검정+흰 글자+빨간 테두리), 제목에만 한난체, ThreeON 표기** | [UI_제작메모_한난.md](UI_제작메모_한난.md) |
| 09-21 | 대비 때문에 시안값 2개 조정: `tri #767676`(4.54:1) · `warn #8F6000`(4.99:1) | 12px 캡션에 실제 쓰임 · AA 4.5 |
| 09-21 | 저장소 루트의 초기 버전·v2 앱·실데이터 CSV 삭제(이 정리). 이력에는 남는다 — private 전환은 사용자 몫 | 공개 저장소 |
| 10-15 | 화면 구역 API 는 **동시 최대 4개**(`router.SETTLE_LIMIT`) | 요청마다 DB 새 연결 + Supabase Session pooler 동시 연결 한도 |
| 10-18 | **Render 무료 플랜 유지**, 속도는 현 수준 유지(계산 화면의 CPU 몫은 캐시로 보완) | 사용자 결정 |
| 10-18 | 연도·예산 구분 입력 검증은 **미들웨어 한 곳**(`server._bad_param`)에서 — 라우트마다 하지 않는다 | 저장 값은 API 로만 들어오므로 입구에서 막으면 출력도 안전 |
| 10-19 | 전망 결과 캐시의 데이터 버전 = **audit_log 최신 id**(+TTL 10분). 그러니 **DB 를 직접 바꾸는 스크립트도 감사 로그를 남긴다**(prune_history) | 모든 API 쓰기는 응답 전 감사 기록 |
| 10-19 | 이력 보존 규칙 = (연도, 손익\|자본)별 **최신 실행** + (계획\|ERP, 연도)별 **최신 데이터셋**만 | 화면·분석·전망이 읽는 것이 이것뿐(코드 확인) |
| 10-19 | 0원/0원 «신규» 행은 숨기지 않는다 | 상계 전표(+x/−x) — 검토 근거 |
| 10-22 | 학습 자동확정은 확신도 0.80↑ 전표만 · 차이 사유는 ±20%p · 권장 입력 · 마감 연도에도 저장 | 사용자 결정(rev23·24) |
| 10-26 | **화면 설명문은 두지 않는다** — 페이지·카드 아래 안내문 삭제, 숫자·상태 줄만. 설명은 «? 도움말»(`characters.js HELP`). 예측 입력칸만 계산 규칙 한 줄 | 사용자 결정(rev27) — 새 화면도 이 방향 |
| 10-26 | **집행률 색 = 80~120% 초록 · 80% 미만 노랑 · 120% 초과 빨강**(배지·산점도 공통, 산점도는 ▲●▼ 모양도) | 차이 사유 ±20%p 와 같은 선 · 적록 색약 대비 |
| 10-26 | 계획·집계 화면 본문의 연도 선택 칸은 **유지**(헤더와 중복이어도) | 사용자 결정 — 업로드 전 연도 재확인 |
| 10-26 | 마감 해제 안내 = 보고 있는 연도면 헤더 배지 · 다른 연도는 메인 «다음 할 일» 한 줄(큰 띠 없음) | 사용자 결정 |
| 10-26 | 설정·중장기 예측 기준정보는 **탭**으로 한 묶음씩 · 사이드바는 **마우스 올리면 펼침**(접기 버튼 없음) | 사용자 결정(rev27·28) |
| 10-26 | 표준화 모집단 = 마감 실적 + **참고 엑셀 실적(마감 안 된 연도만)**, 같은 연도는 마감 우선 | 앱 마감 연도가 2~3개뿐 — 엑셀 10년 이력으로 N개년·등급별 규칙을 재현(rev29) |
| 10-26 | 기계장치의 고온부품재생·LTSA·CRI, 정기유지보수의 LTSA 는 **표준화에서 빼고 연도별 계획**(고온부품·정기계약·CRI 규칙)으로 | 표준화방향 1·4-4 · 이중계상 방지 |
| 10-26 | 표준금액 우선순위 **수동수정 > 산정 규칙 > 사용자지정 방식 > 자동추천** · 학습 기간(기본 3)은 규칙 없는 칸만 | 엑셀 수식 재현과 백테스트 둘 다 살리려고 |
| 10-26 | 투자비는 반복하지 않는다 — 기준연도 계획본 + 투자계획만 · 기준연도 계획본이 있으면 LTSA·CRI 를 따로 더하지 않는다 | 투자비는 표준화 대상 아님 · 계획본 안에 이미 있음 |
| 10-27 | **검토 큐** — 검토 단위 = 사업 한 줄, 순서 = 검토 금액 × 위험 가중(과다 귀속·음수 1.5 · 저확신 1.2 · 차이 1.0), 한 줄의 여러 이유는 큰 값 하나 · 진행률은 **금액 기준** | 건수만 늘어놓으면(알림 171·사유 1,405) 시작점이 없고 미완성으로 읽힌다 — [설계_검토큐_2026-10-27.md](설계_검토큐_2026-10-27.md) |
| 10-27 | 승인(«이상 없음»)은 숫자를 안 바꾸므로 **마감 연도에도 저장**, 승인 때 실적을 함께 적어 **재분석으로 실적이 바뀌면 승인 무효** | 차이 사유와 같은 원칙 · 옛 판단이 새 숫자를 가리지 않게 |
| 10-27 | 추천 재배정은 **정확도 우선**(유사도 0.75 · 여유 0.15 · 설비/연도 충돌 차단) — 드물어도 된다 | 0.60 기준에서 «GT LTSA → 연료전지 LTSA» 오추천. 틀린 추천은 신뢰를 잃는다 |
| 10-27 | 메인 «다음 할 일»은 이상 알림·차이 사유 두 줄 대신 **검토 큐 한 줄** | 경진대회 전략 분석 3장 A |
| 10-27 | **점진 로딩** — 연도를 알면 nav-state 는 뒤에서(머리만 갱신), 화면 아래 구역(`router.navigate` 의 `later`)은 그린 뒤 채움, 설정은 열린 탭 자료만(`SETTINGS_JOBS`), 메인 전망 패널은 보일 때만 | 운영 실측 nav-state 2.5~10초가 모든 화면을 막았다 · 전망 첫 계산이 서버를 붙잡았다(rev34) |
| 10-27 | 선택 상자는 `select.control` 이 화살표를 직접 그린다(오른쪽 2.25rem) · 검토 큐는 요약 한 줄(머리 카드·곡선 없음) · 메인 다년도 막대 계획 파랑/실적 주황 | 사용자 화면 검토(rev34) |
| 10-27 | **계산 캐시 버전은 «숫자를 바꾸는 쓰기»만**(`viewcache.data_version` — 로그인·로그아웃·차이 사유·검토 승인·4xx 제외), 유효 6시간, 키별 잠금 · 운영은 예열 스레드(2분) · 화면 공통 API 는 질의 수 상한 테스트(nav-state 12, base-years 3) | 로그인마다 전망 28초 재계산 · nav-state 26 / base-years 41 질의(rev35) |
| 10-27 | 설정 «시스템 정보»를 Aside 에서도 보이게 하는 작업은 **하지 않는다** — Aside 가 `/healthz` 를 막을 뿐 일반 브라우저는 정상 | 사용자 결정 |
| 10-26 | 운영 전표 재매핑은 **사업 사이 이동만**(계정·지사 불변) — 기간귀속은 같은 계약의 본 사업으로, 계정대체는 원 비용과 한 사업으로 | 합계 불변을 검증 기준으로 삼으려고([운영_데이터정비_2026-10-26.md](운영_데이터정비_2026-10-26.md)) |
| 10-28 | **정비등급은 사용자 확정 양식 하나** — 화면(기준연도~10년)·올리기·내려받기가 같은 줄(지사·설비), 화면 저장도 양식에 써서 **엑셀 가져오기와 같은 파서**로 읽는다(`grade_plan_from_cells`) | 사용자 결정 · 화면과 엑셀이 다르게 보이던 일(지사당 대표 한 줄) |
| 10-28 | 정비등급 **웹 화면은 색 없음**, 엑셀 내보내기만 바뀐 칸 등급 색(안 바뀐 칸은 확정 양식 색 그대로) | 사용자 결정 |
| 10-28 | **신규 발전설비 지사(양산 2023·대구 2024·청주 2025·수원 2029)는 용량 환산 표준금액** — 기준 5개 지사(화성·파주·광교·판교·삼송)에서 «고정분 + 등급별 MW당 단가», 적용시작 전 실적 제외, 수원 2027~28 정비제외(고정분만), 수원 136MW | 사용자 요청 · LOO 25%로 후보 넷 중 최소([개발정리_2026-10-28.md](개발정리_2026-10-28.md) §1-2) |
| 10-28 | 고온부품은 사용자 양식 금액 그대로(팩터 없음), **기준연도에 그 과목 계획본이 있으면 따로 더하지 않음** | 사용자 결정 · LTSA·CRI 와 같은 이중계상 방지 |
| 10-28 | 5번 패널 설명 문장은 화면에서 빼고 ⓘ + 예측이 챗봇(표준금액 근거는 표 + 엑셀) · 긴 표는 접기·지사 묶음 · 금액 «억원» | 사용자 결정 |
| 10-28 | 학습 기간 3개년 유지(2개년이 과목 합계 오차는 작지만 지사 3년 누적 같음) | 사용자 결정 |

## 4. 코드 지도

**백엔드 `app/src/budget/`**
- 1·2단계: `pipeline_plan.py`+`excel_plan_writer.py`(계획본) · `pipeline_db.py`(zrfm2 흡수·매칭·분석 run) · `matcher*.py`·`learned_match` · `auth.py`(공용 비밀번호 세션·`audit_log`) · `dbcore.py`(sqlite↔PostgreSQL 번역, `?` 자리표시자, `REPLACE_TABLES`·`ID_TABLES`) · `db.py`(스키마) · `ml_registry.py`(분류 모델 레지스트리)
- 3·4단계(Phase 6 + rev29): `benchmark.py`(표준화 계산 + 산정 규칙 엔진 `compute_standard_amounts(rules, events, budget_lookup, window)` · 정기비용 판정 `regular_type`) · `forecast_calc.py`(중장기 — 정기계약·CRI(`cri_events`)·A급정비 일정(`overhaul_*`)·손익/자본 팩터·투자계획) · `forecast_store.py`(상태 20종 DB, base_year 축, 새 표는 `SPECS` + `load_table`/`save_table`, 설정 `forecast_setting`) · `forecast_reference.py`(참고 엑셀 파서 — 수식 → 산정 규칙) · `forecast_backtest.py`(학습 기간 백테스트) · `pipeline_forecast.py`(입력 조립·run) · `forecast_import.py`(엑셀 파서 4종) · `forecast_export.py`(양식 채우기 + `rebase_workbook_years`) · `api_forecast.py`(`/api/forecast/*`)
- `server.py`: `AuthAuditMiddleware`(인증·감사 + `_bad_param` 연도/예산 구분 검증) · `SecurityHeadersMiddleware` · `ServerTimingMiddleware`(가장 바깥, `dbcore` 의 요청별 연결·질의 집계) · `GZipMiddleware`(**BaseHTTPMiddleware 안쪽**이어야 `minimum_size` 가 산다) · `ImmutableStaticFiles`(`/assets`) · `/healthz` · `/api/nav-state`(화면 전환 공통 3종 + `locked`)
- 검토 큐(rev33): `review_queue.py`(이유·가중·상태·커버율 `build_items`/`summarize`, 추천 `suggest`/`suggest_incoming`/`conflicts`) · `db.py`(`review_ack` 표 · `basis_by_line` 줄별 전표·저확신·사람 재배정 합 · `moved_lines` 재배정 대기 줄 · `_line_resolver`) · `server.py`(`/api/review-queue` · `PUT /api/review-ack` · `/api/review-suggest`). 과다 귀속 판정은 `alerts.compute_alerts` 결과를 그대로 쓴다
- `api_forecast.py`: 조회 셋은 `base_year` 생략 시 서버 기본값 · `_cached_view`(표준화·전망 결과 캐시) · rev29: `PUT /state/<site-history|site-event|site-grade-eq|benchmark-rule|actual-tag|regular-contract|cri-rule|investment-plan>` · `POST /reference?apply=` · `GET /compare` · `GET /regular` · `GET /backtest` · `PUT /settings`
- 5번 10-28: `capacity.py`(설비 현황·용량 규칙 기본값 `DEFAULT_CAPACITY`/`DEFAULT_RULES`, `fit_model`·`standard_rows`·`apply_capacity`·`usage_events`·`excluded_grades`, 모형 과목 `MODEL_ACCOUNTS`) — `pipeline_forecast._standard` 가 `capacity_inputs` 로 붙인다(반환 다섯 번째 = cap) · `forecast_import.grade_plan_from_workbook`/`grade_plan_layout`/`is_grade_plan_sheet`(정비등급 양식, B열 지사·C열 설비·DH 둘째 표) · `hot_parts_contracts_from_workbook`/`hot_parts_notes` · `forecast_export.grade_plan_grid`/`grade_plan_from_cells`/`build_grade_plan_download`(바뀐 칸만 등급 색)/`build_hot_parts_download`(`HOT_TEMPLATE`) · `forecast_calc.HOT_PARTS_PLAN_ACCOUNT`(기준연도 계획본 겹침) · `benchmark.prepare_actuals`(표준화 모집단 공유) · 표 `site_capacity`·`capacity_rule`·`hot_parts_contract`(SPECS `default` = 비면 기본값) · API `GET/PUT /api/forecast/grade-plan` · `GET /api/forecast/capacity` · `GET /api/forecast/standard.xlsx` · 챗봇 `chat/engine.py _standard`(std_provider = `api_forecast.standard_rows`)

**프론트 `app/web/`**
- `index.html`(셸: 헤더 72px·사이드바·건너뛰기 링크·토스트·바쁨) · `src/main.js`(부팅·이벤트 위임·드로어 Escape/포커스) · `router.js`(해시 라우팅 `#/view`·딥링크 `#/detail/<지사>`·`#/forecast/bench|table`, 페이지 제목) · `data.js`·`state.js`·`api.js`
- `views/` 12개(home plan collect branches detail **review** stats forecast **forecast_viz** settings yearconfig gate) — `review.js`(검토 큐 그리기·JS 요약 `rqSummarize`) + `review_actions.js`(클릭·변경·단축키, `main.js` 가 먼저 위임 — `forecast_actions.js` 와 같은 방식) — 5번 탭 기준정보 안쪽 탭: 참고 엑셀·대조 / 정비등급(+설비별) / 학습 기간·백테스트 / 팩터·고온부품 / 지사 연혁·구조변화 / 정기계약·CRI·투자 / 본사 배분 / 돌발사업 · 표준화 탭: 표준금액 / 산정 규칙 / 정기비용 분리 · 전망 탭: 한눈에 보기 + 10개년 표(예측 범위) + CRI 일정 · `components/`(sidebar badges widgets lockbanner loaderror feedback characters) · `forecast_actions.js`
- 화면 상태 키(`state.js`): `rq`(검토 큐 — 보기 건수·거르기·펼친 줄·추천 캐시) · `rqBrief`(메인 요약) · `settingsTab`(설정 탭) · `fc.manageTab`(예측 기준정보 탭) · `brTableOpen`(지사 표 접기) · `det.guideOpen`(«? 표 보는 법») · `helpOpen`(도움말 말풍선)
- 2026-10-26 추가: `lockbanner.js`(헤더 마감 배지 `lockBadgeHtml` + 메인 줄 `openLockItems`) · `branches.js brScatterHtml`(산점도, 색·모양은 `scColor`/`scMark`) · `badges.js rateBadge`(집행률 3색) · `sidebar.js renderHeaderBrand` · `main.js` 사이드바 펼침(`html.sb-rail` 고정 + `sb-collapsed` 를 hover/focus 로 토글)
- 스타일: `tailwind.config.js`(한난 토큰 이름) · `src/styles/app.css`(`:root` 변수·`@font-face`·컴포넌트 클래스) · `custom.css`(손으로 쓴 규칙 — **det-table 열폭은 여기, 바꾸지 않는다**) · `public/assets/`(시그니처 SVG·`fonts/HananCha-v1.woff2`)
- 5번 10-28(`views/forecast.js`): `gradePlanTable`(정비등급 양식 표, `data-fc="gp-cell"`, dirty 키 `grade_plan`) · `hotPartsPanel`(`hot-cell`) · `capacityBody` · `DETAIL_GROUPS`/`detailLines`(상세 표 합친 줄, `data-fcdgrp`) · `panel()` 접기(`data-fcpanel`)·`longTable` 지사 묶음(`data-fcgrp`) · 표준금액 `benchSiteGroups`(`data-fcbopen`)·거르기(`data-fcbf`) · 재학습(`fc-relearn`). 상태: `fc.gradePlan`·`fc.capacity`·`fc.closedPanels`·`fc.groupOpen`·`fc.benchOpen`·`fc.benchFilter`·`fc.openGroups`. `router.settle` 은 실패한 구역을 1.5초 뒤 한 번 더

**표 열폭·CSS 함정**은 MASTER §7. 옛 팔레트(`blue-*`·`slate-*`)를 새 화면에 쓰면 `tests/test_ui_shell.py` 가 깨진다.

## 5. 운영 지식 — 몸으로 배운 것

**속도·관측(2026-10)**
- 운영의 느림은 대부분 **DB 왕복**이다: 연결 ~0.42초 · 질의 ~70~140ms(싱가포르 앱 ↔ 서울 DB). 질의 수가 곧 시간 — 행마다 질의하는 코드(N+1)를 넣으면 `tests/test_perf_budget.py` 상한이 깨진다.
- 모든 응답의 `Server-Timing` 헤더로 원인을 가른다: `app`(서버 전체) · `db`(질의 합, `queries=`) · `conn`(연결 수).
- 계산 무거운 API(전망 가정·전망 표·표준화·검토 큐)는 `viewcache.get_or_compute` 캐시(버전 = 숫자를 바꾸는 마지막 감사 로그 id, 유효 6시간). DB 를 API 밖에서 바꾸면 **감사 로그를 남겨야** 캐시가 갱신된다(아니면 최대 6시간 옛값). 운영은 예열 스레드가 2분마다 채운다(`CACHE_WARM=0` 끔).
- Render 무료 CPU 는 로컬보다 3~4배 느리다 — 로컬 프로파일 1초짜리 계산이 운영 3~4초.

**배포·인프라**
- Render 자동 배포는 정상이다(Events 에 #51~#57 모두 «Auto-Deploy»). 반영까지 몇 분 — 판별은 `/healthz` 의 `commit`. 이 서비스는 Blueprint 동기화가 아니라 **대시보드 설정이 기준**(운영 `APP_REV`=rev17 ≠ `render.yaml` rev20) — `render.yaml` 값을 바꿔도 운영엔 안 들어간다.
- CI(`.github/workflows/test.yml`)는 **화면 빌드 → pytest** 순서. `app/static` 이 없으면 HTTP 테스트 2개가 500 으로 깨진다.
- 운영 DB 백업: 사용자 PC 작업 스케줄러 `ThreeON_DB_주간백업`(월 09:00) → `문서\ThreeON_DB백업\`. 이력 정리·지역 이전 전에는 **새 백업 먼저**. [백업_복원.md](백업_복원.md).
- Render `/data` 는 비영속 — 앱 상태는 전부 DB 라 무관, `output/` 산출물만 재생성.
- `/assets/*` 는 immutable 1년 캐시 — 해시 없는 파일(폰트·SVG)을 바꾸면 **파일명을 올린다**(`HananCha-v2.woff2`). 같은 이름으로 덮으면 브라우저가 옛 파일을 계속 쓴다. 로컬 확인은 origin 을 `127.0.0.1` 로 바꾸면 캐시가 분리된다.
- Dockerfile 이력 주석에 «supervisord» 같은 낱말을 남기면 `test_deploy_config` 가 잡는다.
- `entrypoint.sh` 는 LF 여야 한다(Render 는 Linux 클론). `.gitattributes` 참조.
- Supabase 연결은 **Session pooler 5432** + `?sslmode=require`. `PG_TEST_URL` 에 Supabase URL 을 넣지 말 것 — 테스트가 표를 TRUNCATE 한다.

**DB·코드**
- `dbm.connect()` 는 `init_db` 를 돌려 스키마를 쓴다. 실DB 는 `sqlite3 'file:…?mode=ro'` 로 들여다본다.
- 로컬 SQLite 이관·백업 전 `py scripts/db_정리.py`(최신 run 만 남기고 VACUUM) → `py scripts/make_db_snapshot.py`. 운영 PostgreSQL 은 `scripts/prune_history.py`(미리보기 → 새 백업 → `--apply --backup`).
- `hq_master` 는 셀 단위 긴 표로 저장, 읽을 때 넓은 표 복원. 기준연도 예산 열은 `NN년예산`.
- 양식 채우기는 셀 좌표를 박지 않고 라벨 스캔. 재기준화는 시트 개명 임시 이름 경유·수식 치환 단일 패스.
- 매칭 학습은 설정 탭 [AI 학습] 버튼으로만(자동 학습 없음). 저장(즉시) · 분석(모아서 «분석 반영 N») · 학습(수동) 3분리.

**프론트·디자인(Phase 8 · 2026-10-26 정리)**
- 상세 표 행 색은 `custom.css :root --row-missing/--row-new/--row-unmapped`(+`-line` 테두리) — 범례 칸과 같은 토큰을 쓴다. 연한 `--err-bg` 등은 흰 바탕과 구별이 안 돼 바꿨다.
- 내장 브라우저 pane(미리보기)은 CSS transition 이 진행되지 않아 사이드바 폭이 288px 로 «안 바뀐» 것처럼 재진다 — `style.transition='none'` 으로 끄고 재면 76px. 실제 브라우저는 정상.
- 한난체 원본 TTF 의 글리프 9개(래·챕·챗·쳅·햅·햇·헵·헷·혭)는 빈 윤곽을 하나 더 갖고 있어 Chrome OTS 가 폰트 전체를 거부한다 → `make_hanan_font.py` 의 `repair_empty_contours()` 필수.
- `custom.css` 는 Tailwind 유틸리티 **뒤**에 로드된다 → `display` 를 주면 `.hidden` 을 이긴다(`.pending-count.hidden{display:none}` 이 그 흔적).
- 토큰 값은 `tailwind.config.js` 와 `app.css :root` **두 곳** — 함께 바꾼다. 대비표·근거는 UI 제작메모 §4-3.
- Edge 헤드리스 `--window-size` 는 ~500px 아래로 안 내려간다 → 모바일 캡처는 DevTools Protocol 디바이스 에뮬레이션.
- 해시만 바뀌는 이동은 새 번들을 안 받는다 → 빌드 후 확인은 `/?v=<시각>#/…` 로 강제 리로드.

**도구(Claude 세션)**
- Bash heredoc 은 백슬래시를 뭉갠다 → 이스케이프가 필요한 파일은 Write/Edit 도구. `.gitignore` 줄 끝 주석 금지. 콘솔 cp949 → `sys.stdout.reconfigure(encoding='utf-8')`. `subprocess` 로 Edge 를 부를 땐 `encoding='utf-8', errors='replace'`.
- 운영 숫자로 화면을 보려면 최신 주간 백업(`문서\ThreeON_DB백업\<날짜>`)을 SQLite 로 풀어(세션 scratch 의 `load_backup.py` — CSV.gz 를 `dbm.connect()` 로 만든 빈 DB 에 붓기) `run_local.py` 의 `DATA_DIR` 로 준다(2026-10-27 검토 큐 확인 `rq-local` :8141). 운영 DB 에는 손대지 않는다.
- PostgreSQL 함정: 매개변수가 있는 SQL 에 «%» 를 글자로 쓰면(`LIKE '재배정%'`) psycopg 가 자리표시자로 읽는다 — 무늬는 매개변수로. SQLite 테스트로는 안 잡히므로 `test_review_queue` 에 소스 검사를 두었다.
- 로컬 확인 서버는 `.claude/launch.json` 의 `budget-local`(:8099) — 세션 scratch 의 `run_local.py`(`DATABASE_URL=" "`·`APP_PASSWORD=" "`·`DATA_DIR`=실DB 사본). 새 세션이면 경로를 다시 쓴다.
- `gh` CLI 로 PR 생성(`--body-file`). 병합은 사용자 승인 후(CI 통과 확인).
- **같은 체크아웃(`C:\Users\User\Desktop\중장기 예산 소요 전망\ThreeON_Budget` — 2026-10-26 바탕화면에서 옮김)을 여러 Claude 세션이 동시에 고친다**(2026-10-26 세 세션). 편집 전 `git status`·파일 mtime 을 보고, 남의 미커밋 변경을 덮어쓰지 않는다. 합칠 때는 한 세션이 모아 한 PR 로.
- 운영 데이터 정비(재배정·분석·마감)는 Aside 세션의 `page.evaluate(fetch…)` 로 한다. 분석·마감은 1~2분 걸려 Aside 연결이 끊기기도 하지만 **요청은 서버에서 계속 돈다** — `/api/status?year=`(run 시각·수동지정 수)와 `/api/lock-state` 로 결과부터 확인하고 다시 보내지 않는다. Aside REPL 은 세션 폴더 밖 파일을 못 읽는다(업로드할 파일은 `~/.aside/u/0/sessions/<id>/tmp` 로 복사).
- 마감 해제는 자동 승인 분류기가 «공유 자원 변경»으로 막는다 — 사용자가 설정 화면에서 직접 해제한다.
- Aside REPL 은 한 번에 120초 — 긴 측정은 페이지 안 `window.__x` 에 백그라운드로 돌리고 나눠 읽는다. Aside 는 `/healthz` 요청을 막고(홈 «시스템 확인 불가»는 Aside 한정) 뷰포트 크기를 못 바꾼다(모바일은 다른 방법).
- 내장 브라우저 pane 이 숨겨져 있으면 프로그램 `scrollTo` 가 scroll 이벤트를 안 쏜다 — 스크롤 동작은 실제 휠(Aside `mouse.wheel`)로 확인.
- `migrate_pg.py`·`backup_pg.py` 처럼 스크립트 둘을 함께 import 할 때 `sys.stdout = TextIOWrapper(...)` 를 두 번 하면 스트림이 닫힌다 → `sys.stdout.reconfigure(encoding="utf-8")`.
- (10-28) Git Bash 긴 heredoc(따옴표·백틱 많음)은 «unexpected EOF» — 편집 스크립트는 Write 로 파일을 만들어 `py 파일`. Aside 업로드는 Aside 세션 폴더 안 파일만(복사 → `filechooser.setFiles`), 해시만 바꾸면 새 번들 안 받음(`/?r=<시각>#/…`), 배경 탭 스크린샷은 `bringToFront()` 뒤. 확정 원본 엑셀은 사용자 바탕화면 `검증자료들\`

## 6. 남은 것 (우선순위)

0-0. **(2026-10-28)** [개발정리_2026-10-28.md](개발정리_2026-10-28.md) §4 — ① [사용자] #93 배포 후 운영 «정비등급» 화면 눈 확인 ② [사용자] 2026 계획본 업로드 ③ [사용자 확인] 고온부품 수원 계약기간(양산과 같음) ④ [Claude, 선택] 용량 규칙 CI 오차 53% 개선 ⑤ [사용자 결정] 다른 세션 열린 PR(#92·#83·#81·#76·#72)

0-1. **[Claude] (2026-10-27 추가, 경진대회)** [경진대회_전략_2026-10-27.md](경진대회_전략_2026-10-27.md) 3·6장 순서 — B 근거 설명 자동 초안(검토 큐 카드·전망 칸) → C 전망 시나리오 비교 → 전표 단위 매칭 정밀도 측정(사람 확정 668건) · 더미 데이터 세트 · 발표 리허설(콜드 스타트 대비 녹화본). 검토 큐 운영 PG 응답 시간도 배포 후 잰다.
0. **[사용자 → Claude] (2026-10-26 추가)** ① 2023·2024 A급 정비 원장(건설가계정 «외주비-열원정기점검») 확보 → ERP 보충·재분석·재마감 ② 열수송관 취득·구역전기(AMI·배전) 실적을 플랜트 유지보수 범위에 넣을지 ③ LTSA 계약 금액·CRI 대상·미래 정기점검 일정 입력(A급정비 일정이 그때 켜진다) ④ 참고 엑셀 2023 동탄 LTSA 두 칸이 바뀌었는지 확인. 근거 [운영_데이터정비_2026-10-26.md](운영_데이터정비_2026-10-26.md)

1. ~~한난체 웹폰트 사내 사용 범위 확인~~ — **2026-09-21 사용자 확인: 사용 가능.** 유지. (방침이 바뀌면 `app.css` `@font-face` + `font-hanan` 제거 → Pretendard 폴백, 테스트 2개도 삭제.)
2. **[사용자]** 저장소 private 전환 — 루트 실데이터 파일은 2026-09-21 삭제했지만 **이력(`4be2452` 등)에는 남아 있다**. private 전환 + 백업 저장소(`wnghcjswo12-cpu`) 점검. 이력 재작성은 협업자와 상의.
3. **[사용자]** Supabase 계정 2단계 인증 · Docker 있는 PC 에서 `deploy/onprem` 첫 실행 → [사내이관_가이드.md](사내이관_가이드.md) §9 에 기록.
4. **[동료 합의 → Claude]** 표준금액 계층적 후퇴(표본 2개년 한계, `specs/2026-09-19-표준화-기준선.md` §5) — 대외 수치가 바뀌므로 합의 후 별도 Phase.
5. **[일정 확정 후]** Supabase → 사내 PG 이전 · `.env` 재작성 · 개인 계정 전환 · 외부 자원 삭제.
6. **[사용자 업무 판단 → Claude]** Aside 검토 미해결 3건 — 본사 일괄 계획 vs 지사 실적 집행률 왜곡 · 학습 매칭 오분류 사례(강남 HRSG 1.33억) · 2025 계획 템플릿본. [속도개선_운영점검_2026-10.md](속도개선_운영점검_2026-10.md) §5.
7. **[사용자 시간 날 때 + Claude]** DB 지역 이전(서울 → 싱가포르) — [DB_지역이전_절차.md](DB_지역이전_절차.md). 백업 복원 리허설도 이때.
8. **[사용자]** 외부 장애 감시(UptimeRobot 등, `/healthz` 5분 간격 — 콜드 스타트도 사라짐).
9. 선택: 로그인 실패 레이트 리밋 · 로그아웃 후 쿠키 무효화 · CSP/HSTS(QA P2, 보안설계 §6) · 모바일 폭 재검증.

## 7. 문서 지도

| 문서 | 언제 보나 |
|---|---|
| **이 문서** | 이어받을 때 첫 30분 |
| [PRD.md](PRD.md) | 무엇을 왜 만드나 — 문제·목표·사용자·단계별 요구사항·한계 |
| [설계_표준화방향_반영.md](설계_표준화방향_반영.md) | 5번 탭 표준화·전망(rev29) — 방향 6항목, 계산 순서, 엑셀 수식 해석 범위, 쓰는 법 |
| [개발정리_2026-10-28.md](개발정리_2026-10-28.md) | 2026-10-28 하루 — 정비등급·고온부품 확정 양식, 설비용량 환산(규칙·수치), 5번 화면 정리, 사용자 결정·함정·남은 일 |
| [개발정리_2026-10-27.md](개발정리_2026-10-27.md) | 2026-10-27 하루(rev33~37) 한 장 요약 — 무엇이 바뀌었나·운영 실측·사용자 결정·남은 일 |
| [운영점검_2026-10-27.md](운영점검_2026-10-27.md) | rev34~36 배포 후 Aside 점검·실측 기록, 추가 개선 목록과 처리 |
| [설계_검토큐_2026-10-27.md](설계_검토큐_2026-10-27.md) | 검토 큐(rev33) — 이유·가중·상태 규칙, 추천 기준과 그 근거, API·표, 검증 수치 |
| [경진대회_전략_2026-10-27.md](경진대회_전략_2026-10-27.md) | 심사위원 관점 분석 — 경쟁 서비스·약점·반드시 구현 3개·데모 흐름·로드맵 |
| [운영_데이터정비_2026-10-26.md](운영_데이터정비_2026-10-26.md) | 참고 엑셀 적용 · 2023~2025 전표 재매핑 원칙·결과 · 2023 실적 차이 원인 |
| [통합_인수인계_MASTER.md](통합_인수인계_MASTER.md) | 구조·분석 로직 R1~R15·API·CSS 함정·표 열폭 (상단 현행화 블록부터) |
| [DB_스냅샷.md](DB_스냅샷.md) | 스키마·현재 데이터·검증 기준치 (`make_db_snapshot.py` 로 재생성) |
| [변경이력_CHANGELOG.md](변경이력_CHANGELOG.md) | 왜 이렇게 만들었나 — rev1~ (2026-10-28 항목까지) |
| [속도개선_운영점검_2026-10.md](속도개선_운영점검_2026-10.md) | 2026-10 속도 진단·개선 실측, Aside 검토 미해결 건, 다시 재는 법 |
| [백업_복원.md](백업_복원.md) · [DB_지역이전_절차.md](DB_지역이전_절차.md) | 주간 백업·복원·이력 정리 · DB 를 싱가포르로 옮기는 절차 |
| [연계계약_CONTRACT.md](연계계약_CONTRACT.md) | 앱이 받고 내는 파일의 스키마·단위·명명 |
| [배포가이드.md](배포가이드.md) · [사내이관_가이드.md](사내이관_가이드.md) · [보안설계.md](보안설계.md) | 운영·이관·보안 |
| [학습데이터_모델_관리.md](학습데이터_모델_관리.md) | 분류 모델 레지스트리·학습데이터 |
| [UI_제작메모_한난.md](UI_제작메모_한난.md) | 화면 디자인 — 토큰·CI 근거·대비표·폰트 함정 (+ `img/ui/` 캡처) |
| [설계_3-4단계_소요전망_파이프라인.md](설계_3-4단계_소요전망_파이프라인.md) · [알고리즘_명세.html](알고리즘_명세.html) | 표준화·전망 설계 근거 · 매칭 규칙 시각 문서 |
| [다음_할_일_체크리스트.md](다음_할_일_체크리스트.md) | 누가 무엇을 — 살아 있는 항목 |
| **팀원용** [팀공유_최종안내.html](팀공유_최종안내.html) · [팀원_실행가이드.md](팀원_실행가이드.md) | 무엇을 하는 앱이고 어떻게 쓰나 (+ `img/share/`) |
| `superpowers/specs/`·`plans/` | 각 Phase 의 설계서·계획서(체크 표기 포함) |
| [archive/](archive/) | 역사 문서 — 현행이 아니다 |
