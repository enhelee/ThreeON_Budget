# ThreeON 발전플랜트 유지보수 예산 분석 — 팀 공유(최종) 2026-09-09

두 앱과 팀 문서, 배포 구성을 한 폴더에 모은 **팀 공유·배포용 패키지**입니다. 실데이터·DB·비밀(.env)은 들어 있지 않고 `.gitignore`/`.dockerignore`가 계속 막습니다.

```
 ① 예산 계획 ─ ② 실적 매칭·검토·학습 ─▶ [결과 JSON] ─▶ ③ 예산 표준화 ─ ④ 중장기 예산(26~35년)
 └──── budget_app (FastAPI, /app) ────┘             └─── forecast_app (Streamlit, /forecast) ───┘
                    한 주소(Caddy) · 한 DB(SQLite 또는 PostgreSQL/Supabase) · 팀 공용 비밀번호 + 작업자 이름
```

| 폴더/파일 | 내용 |
|---|---|
| `budget_app/` | 계획본 생성 · zrfm2 실적 매칭(총액 보존) · 검토/수정/학습 웹 · 통계 · **팀 연계 내보내기** · 로그인·감사로그 · 모델 레지스트리 · DB 전환(`DATABASE_URL`) |
| `forecast_app/` | 실적 업로드·투자유형 분류·대시보드·리포트 · **예산 표준화 · 중장기 예산 26~35년** · 사업 실적 연결 (GitHub `2026-09-08_팀공유_v2` 그대로) |
| `docs/` | **`index.html` 소개 사이트**(GitHub Pages용) + 팀 진입점 README·배포가이드·보안설계·학습데이터_모델_관리·팀원_실행가이드·인수인계·연동규격·PRD |
| `deploy/` | `Dockerfile`(단일 이미지) · `Caddyfile` · `supervisord.conf` · `entrypoint.sh` · `docker-compose.yml`(사내) · `render.yaml`(무료) · `.env.example` · `requirements.txt` |
| `matching_tool_src/` | forecast_app에 내장된 브라우저 매칭 HTML의 소스(`node build.mjs`) |
| `Dockerfile` `render.yaml` `.dockerignore` `.env.example` | 저장소 루트에서 바로 쓰기 위한 사본(Render·Docker 컨텍스트 = 이 폴더) |
| `실행_1_…bat` `실행_2_…bat` `실행_mac.sh` | 각자 PC 실행기(현재 PC의 Python 사용) |

## 빠른 시작
- **각자 PC**: `.env.example` → `budget_app/.env`(APP_PASSWORD·SECRET_KEY) → `실행_1_예산실적집계(budget_app).bat`(http://localhost:8010) · `실행_2_예산예측프로그램(v2).bat`(http://127.0.0.1:8501)
- **무료 공개(팀 전용)**: Supabase 프로젝트 → Render Blueprint(`render.yaml`) → 환경변수 `APP_PASSWORD`·`DATABASE_URL` → `/app/`·`/forecast`. 절차: `docs/배포가이드.md` §1
- **사내 서버(최종)**: `cp .env.example .env` → `docker compose -f deploy/docker-compose.yml up -d --build` → `http://서버:8080/`. 절차: `docs/배포가이드.md` §3
- **소개 사이트**: `docs/index.html` → GitHub Pages(Settings → Pages → `/docs`) 또는 서버 `/`

먼저 읽을 문서: **`docs/팀프로젝트_통합_README_2026-09-08.md`**(팀 진입점) → `docs/팀원_실행가이드.md` → `docs/배포가이드.md` → `docs/보안설계.md` → `docs/학습데이터_모델_관리.md`.

## 보안 원칙(요약)
- 비밀은 `.env`·Render 환경변수·Supabase 대시보드에만. 코드·문서·이미지에 없음. `.env`는 커밋 금지(`.env.example`만).
- 실데이터(`*.db`, `data_*.csv`, `matched_*.csv`, 모델 파일, `checkpoint_data/`, `config/*.json`) 커밋 금지 — `.gitignore` 등록.
- 공개 URL에서는 반드시 `APP_PASSWORD` 설정. 작업자 이름은 실명(또는 고정 별명)으로 — 변경 이력의 근거.
- 외부 클라우드의 실데이터는 팀 검토 기간의 **임시** 보관. 사내 이관 후 삭제.

## 테스트
```bash
cd budget_app     && py -m pytest -q          # 87 passed (인증·감사로그·DB전환 번역·모델 레지스트리 포함)
cd forecast_app   && py -m pytest tests/ -q   # 183 passed
```
