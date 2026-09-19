# ThreeON 예산 프로젝트 — 단일 이미지·단일 프로세스 배포
#   uvicorn(:$PORT)  FastAPI + Vite 빌드 SPA  ← 이것 하나뿐이다
# Phase 6-8 이전에는 프록시·Streamlit 전망 앱·프로세스 관리자까지 셋이 한 이미지에 있었다.
# 3·4단계(표준화·중장기 전망)를 앱이 흡수하면서(6-2~6-7) 나머지 둘이 필요 없어졌다.
# 사내 서버에서는 docker-compose.yml이 같은 이미지를 볼륨·PostgreSQL과 함께 띄운다.
# ── 1단계: 프론트 빌드 (Vite) ─────────────────────────────────────────
# Node 는 빌드에만 쓰고 런타임 이미지에는 넣지 않는다 — 사내 오프라인 서버에는
# 빌드된 정적 파일만 들어가므로 Node 설치가 필요 없다.
FROM node:24-alpine AS web
WORKDIR /build
COPY app/web/package.json app/web/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY app/web/ ./
RUN npm run build          # → /build/../static 이 아니라 vite.config 의 outDir 기준

# ── 2단계: 실행 이미지 ────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# curl 은 아래 HEALTHCHECK 가 쓴다.
# (6-8: 여기서 받던 프록시 정적 바이너리가 사라지면서, 사내 TLS 프록시 환경에서
#  GitHub 릴리스 자산을 못 내려받아 빌드가 깨지던 위험도 함께 사라졌다.)
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# 의존성 먼저(레이어 캐시)
COPY deploy/requirements.txt /srv/deploy/requirements.txt
RUN pip install -r /srv/deploy/requirements.txt

# 앱 코드
COPY app/ /srv/app/
COPY --from=web /static/ /srv/app/static/
COPY deploy/entrypoint.sh /srv/deploy/
RUN chmod +x /srv/deploy/entrypoint.sh \
 && mkdir -p /data/budget/output \
 && rm -rf /srv/app/data /srv/app/output /srv/app/.env

# 실행 시 덮어쓸 수 있는 기본값 (.env / PaaS 환경변수)
ENV PORT=8080 \
    DATA_DIR=/data/budget \
    OUT_DIR=/data/budget/output \
    COOKIE_SECURE=1

# supervisord 가 `directory=/srv/app` 으로 잡아 주던 작업 폴더를 그대로 유지한다.
# 앱 코드는 경로를 전부 __file__ 과 환경변수(DATA_DIR·OUT_DIR)로 푸므로 지금은 CWD 에
# 의존하지 않지만, 흡수한 v2 계산부는 CWD 상대경로로 파일을 읽던 이력이 있다
# (내장 양식 FileNotFoundError, 2026-09-15). 실행 폴더를 예전과 같게 두는 편이 싸다.
WORKDIR /srv/app

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD curl -fsS "http://127.0.0.1:${PORT}/healthz" || exit 1
CMD ["/srv/deploy/entrypoint.sh"]
