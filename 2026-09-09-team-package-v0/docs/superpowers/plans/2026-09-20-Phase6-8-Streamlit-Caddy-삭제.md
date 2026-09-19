# Phase 6-8 구현 계획 — Streamlit·Caddy·supervisord 삭제 (uvicorn 단일 프로세스)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 컨테이너에서 프로세스 셋(Caddy · uvicorn · Streamlit)을 **uvicorn 하나**로 줄이고, 흡수가 끝난 v2 앱(`forecast/`)을 저장소에서 들어낸다.

**전제:** 6-1 Step 3(동료분 확인, 계약 [§7](../specs/2026-09-19-전망포팅-계약.md)) **완료** — 사용자 확인 2026-09-20. 이 확인 전에는 이 계획을 시작하지 않는다.

**Spec:** [2026-09-12-통합웹앱-design.md §3.2](../specs/2026-09-12-통합웹앱-design.md) — 최종 상태는 `uvicorn :$PORT` 하나. `Caddyfile`·`supervisord.conf`·`forecast/` 삭제.

**Tech Stack:** Python 3.12(이미지)/3.14(개발) · FastAPI · uvicorn · Docker · pytest

---

## 이 작업의 진짜 위험 — 삭제가 아니라 «인계»다

6-8 을 「파일 지우기」로 보면 틀린다. Caddy 는 프록시만 한 게 아니라 **네 가지 일**을 하고 있었고, 그 중 셋은 FastAPI 에 인계해야 한다.

| Caddyfile 이 하던 일 | 6-8 이후 |
|---|---|
| `reverse_proxy 127.0.0.1:8010` (전 경로) | **소멸** — uvicorn 이 `$PORT` 를 직접 연다 |
| `handle /forecast*` + `forward_auth` → :8501 | **소멸** — 5번 탭이 앱 안으로 들어왔다(6-6) |
| `encode gzip` | **인계** — `GZipMiddleware` |
| 보안 헤더 3종(`X-Content-Type-Options`·`X-Frame-Options`·`Referrer-Policy`) | **인계** — 미들웨어 |
| `/assets/*` → `Cache-Control: public, max-age=31536000, immutable` | **인계** — `StaticFiles` 응답 헤더 |

⚠ 이 인계를 빼먹으면 배포 후에도 **화면은 멀쩡히 뜬다**. 보안 헤더가 사라지고 자산 캐시가 죽는 것은 눈에 안 보인다 — 그래서 Task 1 을 먼저, 테스트로 고정한 뒤에 삭제한다.

⚠ **이 PC 는 Docker 가 없다.** `Dockerfile`·`entrypoint.sh` 는 실행해 볼 수 없고 **배포로만** 검증된다. 병합 전에 Dockerfile 을 눈으로 두 번 본다.

## Global Constraints

- 작업 폴더 `2026-09-09-team-package-v0`. 테스트 `cd app && py -m pytest -q`.
- **기준선 256 passed**(`608ab78`). 삭제로 줄어드는 테스트 수는 계획에 적힌 것만이어야 한다.
- 프론트 수정 후 `cd app/web && npm run build`.
- 커밋 메시지는 한국어, 본문에 «왜». 끝에 `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

## Task 1: FastAPI 가 Caddy 의 남은 역할을 흡수한다

**Files:** Modify `app/server.py` · Create `app/tests/test_http_hardening.py`

- [x] **Step 1: 테스트를 먼저 쓴다** — `tests/test_http_hardening.py`
  - 임의 응답(`/healthz`)에 `x-content-type-options: nosniff` · `x-frame-options: SAMEORIGIN` · `referrer-policy: strict-origin-when-cross-origin`
  - `/assets/<번들>` 응답에 `cache-control: public, max-age=31536000, immutable`
  - `index.html`(`/`)은 여전히 `no-cache` — 기존 규칙을 덮어쓰지 않았는지 고정한다(이 한 줄이 무너지면 프론트 수정이 사용자에게 영원히 안 닿는다)
  - `GZipMiddleware` 가 붙어 있는지: 큰 JSON 응답에 `Accept-Encoding: gzip` → `content-encoding: gzip`

- [x] **Step 2: 실패 확인** — `py -m pytest tests/test_http_hardening.py -q`

- [x] **Step 3: `server.py` 구현**
  - `SecurityHeadersMiddleware`(BaseHTTPMiddleware) — 헤더 3종. **이미 있는 값은 덮지 않는다.**
  - `app.add_middleware(GZipMiddleware, minimum_size=1024)`
  - `/assets` 마운트를 `immutable` 헤더를 붙이는 `StaticFiles` 서브클래스로 교체
  - ⚠ 미들웨어 등록 순서: 인증·감사(`AuthAuditMiddleware`) 동작을 건드리지 않는 위치에 넣는다

- [x] **Step 4: 통과 확인** — 새 테스트 + 전체 회귀(256 유지)

- [x] **Step 5: 커밋**

---

## Task 2: 배포 구성에서 Caddy·supervisord·Streamlit 을 들어낸다

**Files:** Delete `deploy/Caddyfile` · `deploy/supervisord.conf` · Modify `deploy/Dockerfile` · `deploy/entrypoint.sh` · `deploy/docker-compose.yml` · `deploy/requirements.txt` · Rewrite `app/tests/test_deploy_config.py`

- [x] **Step 1: `test_deploy_config.py` 를 먼저 고친다**

지금 12개 중 **Caddy·forecast 전제 6개는 삭제**한다(대상이 사라지므로 의미가 없다):
`test_caddyfile_braces_are_balanced` · `test_forecast_is_guarded_by_forward_auth_not_basic_auth` · `test_forward_auth_target_is_verify_not_status` · `test_caddy_upstreams_match_processes_supervisord_starts` · `test_forward_auth_strips_websocket_upgrade_headers` · `test_entrypoint_copies_builtin_templates_into_forecast_workdir`

**남기고 고칠 것**: `test_no_dangling_import_of_removed_snippet`(entrypoint 부분만) · `test_intro_site_is_gone`(Caddyfile 참조 제거) · `test_config_dir_is_gone` · `test_dead_env_vars_are_removed`

**새로 넣을 것** — 이번 삭제가 되돌아오지 않게 고정한다:
  - `test_deploy_dir_has_no_caddy_or_supervisor`: `deploy/` 에 `Caddyfile`·`supervisord.conf` 부재
  - `test_entrypoint_execs_uvicorn_directly`: `entrypoint.sh` 마지막 줄이 `exec ... uvicorn`, `supervisord` 문자열 부재
  - `test_uvicorn_binds_public_port`: `--host 0.0.0.0` 과 `${PORT}` 사용 (127.0.0.1 로 묶으면 배포가 통째로 죽는다 — Caddy 가 없으니 앞에 아무도 없다)
  - `test_uvicorn_trusts_proxy_headers`: `--proxy-headers` — TLS 는 Render/사내 프록시가 종단하므로 없으면 `COOKIE_SECURE=1` 쿠키가 안 붙는다
  - `test_dockerfile_has_no_caddy_supervisor_forecast`: `Dockerfile` 에 `caddy`·`supervisor`·`COPY forecast/`·`FORECAST_DATA_DIR` 부재
  - `test_requirements_has_no_streamlit`: `deploy/requirements.txt` 에 `streamlit` 부재
  - `test_compose_has_no_forecast_volume`: `docker-compose.yml` 에 `forecast_data` 부재

- [x] **Step 2: 실패 확인**

- [x] **Step 3: 삭제·수정 실행**
  - `git rm deploy/Caddyfile deploy/supervisord.conf`
  - `entrypoint.sh`: 양식 복사 루프 삭제 · `FORECAST_DATA_DIR` mkdir 삭제 · 마지막 줄을
    `exec python -m uvicorn server:app --app-dir /srv/app --host 0.0.0.0 --port "${PORT:-8080}" --proxy-headers --forwarded-allow-ips="*"`
    (환경변수 경고 3개는 그대로 — 여전히 유효하다)
  - `Dockerfile`: 머리말 주석 갱신 · `supervisor` apt 패키지 제거 · Caddy 내려받기 `RUN` 통째 삭제(**사내 TLS 프록시에서 이 줄이 빌드를 깨뜨리던 위험도 함께 사라진다**) · `COPY forecast/` 삭제 · `COPY deploy/...` 를 `entrypoint.sh` 만으로 · `mkdir /data/forecast` 삭제 · `ENV FORECAST_DATA_DIR` 삭제 · `CMD` 유지
  - `docker-compose.yml`: `forecast_data` 볼륨과 마운트 삭제
  - `deploy/requirements.txt`: `streamlit==1.59.0` 삭제, 머리말 주석 갱신. **`pandas==2.2.3` 고정은 남긴다** — 고정 이유가 Streamlit 이었지만 budget_app 이 그 조합에서 검증됐다. 푸는 것은 별건이다.
  - `render.yaml`: 주석의 «/forecast (v2 앱)» 문구 갱신(설정 값은 바뀌지 않는다)

- [x] **Step 4: 통과 확인** — 전체 회귀. 실측 **266 passed** = 256 − 11(옛 deploy 테스트) + 15(새 deploy 테스트) + 6(Task 1)

- [x] **Step 5: 커밋**

---

## Task 3: `forecast/` 폴더와 v2 잔재를 삭제한다

**Files:** Delete `forecast/`(git 추적 80 파일) · `실행_2_예산예측프로그램(v2).bat` · Modify `app/web/src/views/forecast.js`

- [x] **Step 1: 승계 누락이 없는지 마지막 확인**
  - `app/templates/` 에 `builtin_template_표준화.xlsx`·`builtin_template_중장기예산.xlsx` 존재(6-7 에서 옮김)
  - `forecast/builtin_template_손익.xlsx`·`builtin_template_자본.xlsx` 는 `template_fill.py` 용 — **승계 안 함**(사용자 결정 2026-09-20, budget_app `/api/export` 가 같은 양식)
  - `forecast_store.import_v2_csv_dir` 는 **남는다** — 동료 PC 의 CSV 를 읽는 함수이지 v2 코드에 의존하지 않는다. docstring 의 «Streamlit 삭제(6-8) 전에» 문구만 사실에 맞게 고친다
  - `forecast/tests/` 183개 중 승계분(표준화 15 · 중장기 18)은 `app/tests/` 에 있다 — 나머지는 승계 대상이 아니었던 v2 전용
- [x] **Step 2: `views/forecast.js` 하단 «(구) 전망 앱을 새 탭에서 열기» 링크 삭제** → `cd app/web && npm run build`
- [x] **Step 3: `git rm -r forecast/` · `git rm "실행_2_예산예측프로그램(v2).bat"`**
- [x] **Step 4: `README.md`(팀패키지)·`.dockerignore` 에서 v2 전용 줄 정리** · `실행_mac.sh` 의 forecast 분기도(실측에서 발견)
- [x] **Step 5: 전체 회귀 + `grep -rn "forecast/" --include=*.py --include=*.js` 로 끊긴 참조 확인**
- [x] **Step 6: 커밋**

---

## Task 4: 배포 검증

- [x] **Step 1: PR 생성** — #28 (병합 `5dfd7fb`), 이어서 레거시 UI #29 (병합 `449ad38`) (`gh pr create --body-file`) — 병합은 사용자가
- [x] **Step 2: 병합 후 Render Manual Deploy** (Auto-Deploy 가 동작하지 않는다) — 사용자
- [x] **Step 3: `/healthz` 의 `commit` == 병합 커밋 · 배포 `index.html` 번들 해시 == 로컬 `app/static/index.html`**
- [x] **Step 4: 보안 헤더 3종과 `/assets` 캐시 헤더를 배포 응답에서 실측** — Caddy 가 내던 것을 FastAPI 가 정말 내는지는 여기서만 증명된다
- [x] **Step 5: 계획서 `2026-09-19-Phase6-전망기능-흡수.md` 의 6-8 행을 ✅ 로**

---

## 범위 밖 (헷갈리기 쉬운 것)

- **`app/app.py`·`app/run.bat`·`app/run.sh`** — budget_app 의 **레거시 Streamlit UI** 다. 6-8 이 지우는 Streamlit 은 «전망 앱(v2)»이지 이것이 아니다. 컨테이너에서 돌지도 않는다. 별건으로 판단한다.
- **`app/requirements.txt` 의 `streamlit>=1.30`** — 위 레거시 UI 용. `deploy/requirements.txt` 쪽만 지운다.
- **`/api/auth/verify`** — forward_auth 가 사라져도 남긴다(무해하고 테스트가 고정하고 있다).

## 배포 실측 (2026-09-20 밤, `449ad38`)

`/healthz` commit 일치 · 번들 `index-BIPyzdEF.js` 일치 · 보안 헤더 3종 · `/assets` `immutable` + gzip 39.6KB · `index.html` `no-cache` · `/forecast/` 404 · `/app/` 301. 첫 Manual Deploy 는 옛 커밋(`608ab78`)이 떴고 두 번째에 반영됐다 — 배포 뒤에는 반드시 `/healthz` commit 으로 판별할 것.

## 완료 기준

| 항목 | 확인 방법 |
|---|---|
| 프로세스 하나 | 배포 로그에 uvicorn 만 · `Caddyfile`·`supervisord.conf`·`forecast/` 부재 |
| 인계 누락 없음 | 배포 응답에 보안 헤더 3종 + `/assets` immutable |
| 회귀 | budget_app 전체 통과 |
| 화면 | 5번 탭에 «(구) 전망 앱» 링크 없음 |
