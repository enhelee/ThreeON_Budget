# ThreeON 예산 — 발전플랜트 유지보수 예산 통합 웹앱

지사 19곳이 엑셀로 올리는 **예산계획**과 SAP 실적 전표(**zrfm2**)를 자동으로 맞춰 보고,
그 결과를 정비등급별 **표준금액**과 **2026~2035년 예산 전망**의 근거로 넘기는 팀 프로젝트.

```
① 예산 계획 수립  →  ② 실적 집계·사업 매칭  →  ③ 예산 표준화  →  ④ 중장기 예산 전망
   └────────────────────────  app (FastAPI)  ───────────────────────┘
                     ※ 3·4단계는 원래 별도 Streamlit 앱이었고 Phase 6 에서 흡수했다
```

| | 값 |
|---|---|
| 단위 | 천원(집계) · 원(전표·계약 파일) |
| 검증 연도 | 2023 · 2025 — ERP 전체 = 종합표, 미배정 0 |
| 테스트 | `app` 전체 1통 (`cd app && py -m pytest -q`) |
| 배포 | Render + Supabase(검토·실증용) → 최종 사내 서버 |

---

## 폴더 구조

```
threeon-budget/
├─ app/          FastAPI + SPA — 1·2단계 (계획·실적)      ★ 주 애플리케이션
│  ├─ server.py          라우트 51개
│  ├─ src/budget/        도메인 로직 18모듈
│  ├─ web/               프론트 원본 (Vite + Tailwind)
│  ├─ static/            빌드 산출물 — 커밋하지 않음
│  ├─ templates/ tests/ scripts/
│  ├─ data/ config/ output/    로컬 상태 — 커밋하지 않음
│  └─ .env                     비밀값 — 커밋하지 않음
├─ site/         소개 사이트 — Phase 5에서 앱으로 흡수 후 삭제
├─ deploy/       Dockerfile · entrypoint.sh · docker-compose · requirements
├─ docs/         문서 (설계·인수인계·계약·변경이력)
├─ render.yaml   Render Blueprint
└─ .env.example  환경변수 예시 → app/.env 로 복사해 사용
```

---

## 로컬 실행

```bash
# 1) 환경변수
cp .env.example app/.env      # APP_PASSWORD, SECRET_KEY 채우기

# 2) 백엔드 의존성
pip install -r app/requirements.txt

# 3) 프론트 빌드 (최초 1회, 프론트 수정 시마다)
cd app/web && npm install && npm run build && cd ../..

# 4) 실행  →  http://localhost:8010
cd app && python -m uvicorn server:app --port 8010
```

**3번을 건너뛰면 `/` 가 500 을 냅니다.** 프론트 원본은 `app/web/src/` 이고,
빌드 산출물 `app/web/../static/` 은 커밋하지 않습니다(`.gitignore`).
프론트만 고칠 때는 `cd app/web && npm run dev` 가 편합니다.

Windows는 `app/분석프로그램_실행.bat` 더블클릭으로도 됩니다(빌드는 별도).

**테스트**

```bash
cd app && python -m pytest -q      # 약 6~7분
```

---

## 배포

한 컨테이너에 **프로세스 하나(uvicorn)**. Phase 6-8 에서 프록시·Streamlit·supervisord 를 걷어냈습니다.

| 경로 | 내용 |
|---|---|
| **`/`** | **로그인 게이트 → 작업공간** ★ 팀원에게 알려줄 주소는 이것 하나 |
| `/app/` | `/` 로 301 (예전 북마크 보호) |
| `/api/*` `/assets/*` `/healthz` | API · 프론트 자산 · 헬스체크 |
| `/site/` | 소개·문서 사이트 — *Phase 5에서 앱으로 흡수 후 삭제* |
| `/forecast` | 전망 앱 — *Phase 6에서 앱 5번 탭으로 흡수 후 삭제* |

Render는 저장소 루트의 `render.yaml`을 자동 인식합니다. 대시보드에서 `APP_PASSWORD`·`DATABASE_URL`을 입력하면 됩니다.
자세한 절차는 [docs/배포가이드.md](docs/배포가이드.md).

> 무료 플랜은 15분 미사용 시 슬립되어 첫 접속이 30~60초 걸립니다. `/healthz`로 미리 깨울 수 있습니다.

---

## 어디부터 읽나

| 순서 | 문서 | 내용 |
|---|---|---|
| 1 | [docs/superpowers/specs/2026-09-12-통합웹앱-design.md](docs/superpowers/specs/2026-09-12-통합웹앱-design.md) | **현재 진행 중인 설계** — Phase 0~6 전 구간 |
| 2 | [docs/통합_인수인계_MASTER.md](docs/통합_인수인계_MASTER.md) | 구조·아키텍처·분석 로직 R1~R15·API 명세 |
| 3 | [docs/DB_스냅샷.md](docs/DB_스냅샷.md) | DB 스키마·현재 데이터·검증 기준치 |
| 4 | [docs/변경이력_CHANGELOG.md](docs/변경이력_CHANGELOG.md) | rev1~rev15 의사결정 이력 |
| 5 | [docs/연계계약_CONTRACT.md](docs/연계계약_CONTRACT.md) | 앱이 받고 내는 파일·인터페이스 계약(옛 계약 4개 통합본) |
| 6 | [docs/설계_3-4단계_소요전망_파이프라인.md](docs/설계_3-4단계_소요전망_파이프라인.md) | 표준화·중장기 전망 설계 (Phase 6 근거) |

---

## 보안

- **이 저장소는 public 입니다.** 따라서 사내 실데이터·비밀값은 어떤 경우에도 커밋하지 않습니다.
  실적 데이터는 전부 DB(Supabase/사내 PostgreSQL)에 있고, 앱은 로그인 뒤에서만 보여 줍니다.
- 실데이터(`*.csv` 마스터·연도별 자료)·DB·`.env`는 `.gitignore`로 차단됩니다. 커밋 전 `git status`로 확인하세요.
- 외부 반출·외부 서비스 업로드는 사내 정보보호 규정을 따릅니다. [docs/보안설계.md](docs/보안설계.md)
