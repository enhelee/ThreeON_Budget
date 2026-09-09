# ThreeON 예산 프로젝트 — 단일 이미지(한 주소) 배포
#   Caddy(:$PORT, 리버스 프록시·정적 사이트·/forecast 기본인증)
#   ├─ /            소개·문서 사이트 (docs/)
#   ├─ /app, /api   budget_app  FastAPI  (127.0.0.1:8010)
#   └─ /forecast    forecast_app Streamlit (127.0.0.1:8501, baseUrlPath=forecast)
# 무료 PaaS(Render·HF Spaces)는 컨테이너 1개·포트 1개만 열어주므로 세 프로세스를 supervisord로 한 이미지에 담는다.
# 사내 서버에서는 docker-compose.yml이 같은 이미지를 볼륨·PostgreSQL과 함께 띄운다.
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
COPY budget_app/ /srv/budget_app/
COPY forecast_app/ /srv/forecast_app/
COPY docs/ /srv/site/
COPY deploy/Caddyfile deploy/supervisord.conf deploy/entrypoint.sh /srv/deploy/
RUN chmod +x /srv/deploy/entrypoint.sh \
 && mkdir -p /data/budget/config /data/budget/output /data/forecast \
 && rm -rf /srv/budget_app/data /srv/budget_app/output /srv/budget_app/.env

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
