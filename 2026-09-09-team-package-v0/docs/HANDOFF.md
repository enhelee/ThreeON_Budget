# HANDOFF — 개발자 인수인계 (현행, 2026-10-19)

> **이 문서가 개발자 진입점이다.** 새 세션·새 사람이 이어받을 때 이것부터 읽고, 구조·로직·API 는 [통합_인수인계_MASTER.md](통합_인수인계_MASTER.md), 팀원용 요약은 [팀공유_최종안내.html](팀공유_최종안내.html).
> 이전에 로컬에만 두던 인수인계(2026-09-19·20·21 판)를 여기로 합쳤다. 1단계 Streamlit 시절의 옛 HANDOFF 는 [archive/](archive/) 에 있다.

---

## 0. 한 줄 상태

| 항목 | 값 |
|---|---|
| 저장소 | `enhelee/ThreeON_Budget` — 앱과 문서는 전부 `2026-09-09-team-package-v0/`(이하 «패키지»). 루트에는 `render.yaml`·`README.md`·`.gitignore` 만 |
| 앱 | FastAPI + Vanilla JS SPA **하나**. 1~5단계(계획·실적 집계·분석·통계·표준화/중장기 전망) + 설정. 프로세스 하나(uvicorn) |
| 배포 | Render 무료(Docker, **싱가포르**) + Supabase PostgreSQL(**서울** ap-northeast-2). 병합하면 **자동 배포 ~1분**(2026-10 확인 — 예전엔 Manual Deploy 필요했다). 판별은 `/healthz` 의 `commit` |
| 테스트 | `cd app && py -m pytest -q` → **335 passed**(2026-10-19). 4~8분. PR 마다 GitHub Actions(`.github/workflows/test.yml`)도 돈다 |
| 마지막 큰 변화 | Phase 8 한난 디자인(09-21) → **속도 개선·보안 P1·CI·백업·이력 정리(10-15~19, #47·#48·#49)** — [속도개선_운영점검_2026-10.md](속도개선_운영점검_2026-10.md) |
| 속도(운영) | 로그인 후 화면 전환 2.9~5.5초(10-15 에는 33~40초) · 전망 표 탭 7.4초, 재방문 3.0초 |
| 검증 연도 | 2023 · 2024 · 2025 모두 마감. 2025 손익 98,554,802 · 자본 49,709,177 천원 |

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
│  ├─ templates/              내장 엑셀 양식 (표준화·중장기예산)
│  ├─ tests/                  pytest 335
│  └─ data/ config/ output/ .env   로컬 상태·비밀 — 커밋 안 함
├─ deploy/                    Dockerfile · entrypoint.sh · docker-compose.yml · requirements.txt · onprem/(사내 반입 스크립트)
├─ docs/                      이 문서들 (§7) · img/ (캡처) · superpowers/ (설계·계획) · archive/ (역사)
├─ .env.example · .gitignore · .dockerignore · README.md
└─ 실행_1_예산실적집계(budget_app).bat · 실행_mac.sh
```

## 2. 실행·검증 명령

```bash
cd 2026-09-09-team-package-v0/app/web && npm install && npm run build   # 프론트 수정 후 반드시 (static/ 은 커밋 안 함)
cd 2026-09-09-team-package-v0/app && py -m pytest -q                      # 335 passed
cd 2026-09-09-team-package-v0/app && DATABASE_URL=" " py -m uvicorn server:app --port 8010   # 로컬 sqlite
```

- **`DATABASE_URL` 은 공백 한 칸(`" "`)으로 비운다** — 진짜로 비우면 `.env` 의 운영 PostgreSQL 에 붙는다. `/healthz` 가 `db: sqlite` 인지 매번 확인.
- 로컬 `app/data/budget.db` 에는 마감 기록이 없다(마감은 운영 PG). 5번 탭을 실측하려면 사본에서 `POST /api/lock` 으로 2023·2025 를 마감한 뒤.
- 배포본 로그인은 팀 비밀번호가 필요하므로 Claude 가 입력하지 않는다. 운영 화면을 재야 하면 **사용자가 Aside 브라우저에서 로그인**하고 Claude 가 그 세션으로 측정한다(조회만 — 저장·업로드·분석·마감은 누르지 않는다). 측정법은 [속도개선_운영점검_2026-10.md](속도개선_운영점검_2026-10.md) §7.
- 배포 확인 순서: 병합(CI 통과 후) → 자동 배포 ~1분(안 걸리면 Render Manual Deploy) → `/healthz` 의 `commit` == 병합 커밋 → 배포 `index.html` 의 번들 해시 == 로컬 `app/static/index.html`. 배포 직후 첫 요청 한 번은 DB 스키마 확인으로 ~4초 더 걸린다.

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

## 4. 코드 지도

**백엔드 `app/src/budget/`**
- 1·2단계: `pipeline_plan.py`+`excel_plan_writer.py`(계획본) · `pipeline_db.py`(zrfm2 흡수·매칭·분석 run) · `matcher*.py`·`learned_match` · `auth.py`(공용 비밀번호 세션·`audit_log`) · `dbcore.py`(sqlite↔PostgreSQL 번역, `?` 자리표시자, `REPLACE_TABLES`·`ID_TABLES`) · `db.py`(스키마) · `ml_registry.py`(분류 모델 레지스트리)
- 3·4단계(Phase 6): `benchmark.py`(표준화 계산, v2 승계) · `forecast_calc.py`(중장기, 등급 없는 지사 → «표준» 후퇴) · `forecast_store.py`(상태 9종 DB, base_year 축, 지사 해석기) · `pipeline_forecast.py`(입력 조립·run) · `forecast_import.py`(엑셀 파서 4종) · `forecast_export.py`(양식 채우기 + `rebase_workbook_years`) · `api_forecast.py`(`/api/forecast/*`)
- `server.py`: `AuthAuditMiddleware`(인증·감사 + `_bad_param` 연도/예산 구분 검증) · `SecurityHeadersMiddleware` · `ServerTimingMiddleware`(가장 바깥, `dbcore` 의 요청별 연결·질의 집계) · `GZipMiddleware`(**BaseHTTPMiddleware 안쪽**이어야 `minimum_size` 가 산다) · `ImmutableStaticFiles`(`/assets`) · `/healthz` · `/api/nav-state`(화면 전환 공통 3종 + `locked`)
- `api_forecast.py`: 조회 셋은 `base_year` 생략 시 서버 기본값 · `_cached_view`(표준화·전망 결과 캐시)

**프론트 `app/web/`**
- `index.html`(셸: 헤더 72px·사이드바·건너뛰기 링크·토스트·바쁨) · `src/main.js`(부팅·이벤트 위임·드로어 Escape/포커스) · `router.js`(해시 라우팅 `#/view`·딥링크 `#/detail/<지사>`·`#/forecast/bench|table`, 페이지 제목) · `data.js`·`state.js`·`api.js`
- `views/` 10개(home plan collect branches detail stats forecast settings yearconfig gate) · `components/`(sidebar badges widgets lockbanner loaderror feedback) · `forecast_actions.js`
- 스타일: `tailwind.config.js`(한난 토큰 이름) · `src/styles/app.css`(`:root` 변수·`@font-face`·컴포넌트 클래스) · `custom.css`(손으로 쓴 규칙 — **det-table 열폭은 여기, 바꾸지 않는다**) · `public/assets/`(시그니처 SVG·`fonts/HananCha-v1.woff2`)

**표 열폭·CSS 함정**은 MASTER §7. 옛 팔레트(`blue-*`·`slate-*`)를 새 화면에 쓰면 `tests/test_ui_shell.py` 가 깨진다.

## 5. 운영 지식 — 몸으로 배운 것

**속도·관측(2026-10)**
- 운영의 느림은 대부분 **DB 왕복**이다: 연결 ~0.42초 · 질의 ~70~140ms(싱가포르 앱 ↔ 서울 DB). 질의 수가 곧 시간 — 행마다 질의하는 코드(N+1)를 넣으면 `tests/test_perf_budget.py` 상한이 깨진다.
- 모든 응답의 `Server-Timing` 헤더로 원인을 가른다: `app`(서버 전체) · `db`(질의 합, `queries=`) · `conn`(연결 수).
- 계산 무거운 API(전망 표·표준화)는 `api_forecast._cached_view` 캐시. DB 를 API 밖에서 바꾸면 감사 로그를 남겨야 캐시가 바로 갱신된다(아니면 최대 10분 옛값).
- Render 무료 CPU 는 로컬보다 3~4배 느리다 — 로컬 프로파일 1초짜리 계산이 운영 3~4초.

**배포·인프라**
- Render 자동 배포는 2026-10 부터 걸린다(병합 후 ~1분). 그래도 판별은 `/healthz` 의 `commit` — 예전에 Manual Deploy 가 옛 커밋을 띄운 적이 있다.
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

**프론트·디자인(Phase 8)**
- 한난체 원본 TTF 의 글리프 9개(래·챕·챗·쳅·햅·햇·헵·헷·혭)는 빈 윤곽을 하나 더 갖고 있어 Chrome OTS 가 폰트 전체를 거부한다 → `make_hanan_font.py` 의 `repair_empty_contours()` 필수.
- `custom.css` 는 Tailwind 유틸리티 **뒤**에 로드된다 → `display` 를 주면 `.hidden` 을 이긴다(`.pending-count.hidden{display:none}` 이 그 흔적).
- 토큰 값은 `tailwind.config.js` 와 `app.css :root` **두 곳** — 함께 바꾼다. 대비표·근거는 UI 제작메모 §4-3.
- Edge 헤드리스 `--window-size` 는 ~500px 아래로 안 내려간다 → 모바일 캡처는 DevTools Protocol 디바이스 에뮬레이션.
- 해시만 바뀌는 이동은 새 번들을 안 받는다 → 빌드 후 확인은 `/?v=<시각>#/…` 로 강제 리로드.

**도구(Claude 세션)**
- Bash heredoc 은 백슬래시를 뭉갠다 → 이스케이프가 필요한 파일은 Write/Edit 도구. `.gitignore` 줄 끝 주석 금지. 콘솔 cp949 → `sys.stdout.reconfigure(encoding='utf-8')`. `subprocess` 로 Edge 를 부를 땐 `encoding='utf-8', errors='replace'`.
- 로컬 확인 서버는 `.claude/launch.json` 의 `budget-local`(:8099) — 세션 scratch 의 `run_local.py`(`DATABASE_URL=" "`·`APP_PASSWORD=" "`·`DATA_DIR`=실DB 사본). 새 세션이면 경로를 다시 쓴다.
- `gh` CLI 로 PR 생성(`--body-file`). 병합은 사용자 승인 후(CI 통과 확인).
- Aside REPL 은 한 번에 120초 — 긴 측정은 페이지 안 `window.__x` 에 백그라운드로 돌리고 나눠 읽는다. Aside 는 `/healthz` 요청을 막고(홈 «시스템 확인 불가»는 Aside 한정) 뷰포트 크기를 못 바꾼다(모바일은 다른 방법).
- 내장 브라우저 pane 이 숨겨져 있으면 프로그램 `scrollTo` 가 scroll 이벤트를 안 쏜다 — 스크롤 동작은 실제 휠(Aside `mouse.wheel`)로 확인.
- `migrate_pg.py`·`backup_pg.py` 처럼 스크립트 둘을 함께 import 할 때 `sys.stdout = TextIOWrapper(...)` 를 두 번 하면 스트림이 닫힌다 → `sys.stdout.reconfigure(encoding="utf-8")`.

## 6. 남은 것 (우선순위)

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
| [통합_인수인계_MASTER.md](통합_인수인계_MASTER.md) | 구조·분석 로직 R1~R15·API·CSS 함정·표 열폭 (상단 현행화 블록부터) |
| [DB_스냅샷.md](DB_스냅샷.md) | 스키마·현재 데이터·검증 기준치 (`make_db_snapshot.py` 로 재생성) |
| [변경이력_CHANGELOG.md](변경이력_CHANGELOG.md) | 왜 이렇게 만들었나 — rev1~rev21 |
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
