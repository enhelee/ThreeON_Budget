#!/usr/bin/env sh
# 컨테이너 기동: 볼륨 폴더 준비 → uvicorn 한 프로세스.
#
# Phase 6-8 이전에는 supervisord 가 셋(Caddy · uvicorn · Streamlit)을 돌봤다. 3·4단계
# (표준화·중장기 전망)를 앱이 흡수하면서(6-2~6-7) 전망 앱도, 그것을 붙이던 프록시도,
# 셋을 관리하던 supervisord 도 필요 없어졌다. 지금은 uvicorn 이 PID 1 이다.
#
# ⚠ 앞에 아무도 없다 — 0.0.0.0:$PORT 로 열어야 한다. 루프백에 묶으면 컨테이너는
#   «정상 기동»하고 헬스체크만 실패한다(Caddy 뒤에 있던 시절의 내부 포트가 그 값이었다).
# ⚠ TLS 는 Render·사내 프록시가 종단한다 → --proxy-headers 가 없으면 앱이 요청을 http 로
#   보고 COOKIE_SECURE=1 세션 쿠키가 붙지 않는다.
# ⚠ exec 여야 한다 — 감싸면 SIGTERM 이 sh 에서 멈추고 uvicorn 이 정리 없이 죽는다.
set -eu

mkdir -p "${DATA_DIR:-/data/budget}/output"

if [ -z "${APP_PASSWORD:-}" ]; then
  echo "[entrypoint] WARNING: APP_PASSWORD가 비어 있어 앱이 인증 없이 열립니다(사내망 전용). 공개 배포에서는 반드시 설정하세요." >&2
fi

if [ -z "${SECRET_KEY:-}" ]; then
  echo "[entrypoint] WARNING: SECRET_KEY가 없어 임시 키로 기동합니다 — 재시작마다 로그인이 풀립니다. Render/.env에 SECRET_KEY를 설정하세요." >&2
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "[entrypoint] INFO: DATABASE_URL 없음 → SQLite(${DATA_DIR:-/data/budget}/budget.db). 무료 PaaS는 디스크가 비영속이므로 Supabase PostgreSQL 사용을 권장." >&2
fi

exec python -m uvicorn server:app --app-dir /srv/app --host 0.0.0.0 --port "${PORT:-8080}" --proxy-headers --forwarded-allow-ips="*" --no-server-header
