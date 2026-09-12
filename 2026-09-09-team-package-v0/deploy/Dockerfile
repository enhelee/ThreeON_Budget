# ThreeON 예산 프로젝트 — 단일 이미지(한 주소) 배포
#   Caddy(:$PORT, 리버스 프록시·정적 사이트·/forecast 기본인증)
#   ├─ /            소개 사이트 (site/)
#   ├─ /app, /api   budget_app  FastAPI  (127.0.0.1:8010)
#   └─ /forecast    forecast_app Streamlit (127.0.0.1:8501, baseUrlPath=forecast)
# 무료 PaaS(Render·HF Spaces)는 컨테이너 1개·포트 1개만 열어주므로 세 프로세스를 supervisord로 한 이미지에 담는다.
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

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl supervisor \
 && rm -rf /var/lib/apt/lists/*

# Caddy 정적 바이너리 (HTTPS 종단은 PaaS/사내 프록시가 담당하므로 auto_https off)
ARG CADDY_VERSION=2.8.4
RUN curl -fsSL "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_amd64.tar.gz" \
      -o /tmp/caddy.tgz \
 && tar -xzf /tmp/caddy.tgz -C /usr/local/bin caddy && rm /tmp/caddy.tgz && caddy version

WORKDIR /srv

# 의존성 먼저(레이어 캐시) — 두 앱을 한 파이썬 환경에 설치(버전 충돌은 deploy/requirements.txt에서 조정)
COPY deploy/requirements.txt /srv/deploy/requirements.txt
RUN pip install -r /srv/deploy/requirements.txt

# 앱 코드
COPY app/ /srv/app/
COPY --from=web /static/ /srv/app/static/
COPY forecast/ /srv/forecast/
# 소개 사이트 = site/index.html + docs/ 의 문서들.
# index.html 이 「문서 지도」에서 형제 파일(통합_인수인계_MASTER.md 등 12개)을
# 상대경로로 링크하므로, 둘을 같은 폴더에 놓지 않으면 그 링크가 전부 404 가 된다.
COPY site/ /srv/site/
COPY docs/ /srv/site/
COPY deploy/Caddyfile deploy/supervisord.conf deploy/entrypoint.sh /srv/deploy/
RUN chmod +x /srv/deploy/entrypoint.sh \
 && mkdir -p /data/budget/config /data/budget/output /data/forecast \
 && rm -rf /srv/app/data /srv/app/output /srv/app/.env

# 실행 시 덮어쓸 수 있는 기본값 (.env / PaaS 환경변수)
ENV PORT=8080 \
    DATA_DIR=/data/budget \
    CONFIG_DIR=/data/budget/config \
    OUT_DIR=/data/budget/output \
    SITE_DIR=/srv/site \
    FORECAST_DATA_DIR=/data/forecast \
    BASIC_USER=team \
    COOKIE_SECURE=1

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD curl -fsS "http://127.0.0.1:${PORT}/healthz" || exit 1
CMD ["/srv/deploy/entrypoint.sh"]
