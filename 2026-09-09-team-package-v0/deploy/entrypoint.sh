#!/usr/bin/env sh
# 컨테이너 기동: 볼륨 폴더 준비 → 세 프로세스(supervisord). /forecast 인증은 Caddy forward_auth.
set -eu

mkdir -p "${DATA_DIR:-/data/budget}/config" "${DATA_DIR:-/data/budget}/output" "${FORECAST_DATA_DIR:-/data/forecast}"

# forecast_app(v2)이 첫 실행에 필요한 내장 양식·매칭 HTML은 코드 폴더에서 읽으므로 복사 불필요.
# 팀 v2 앱은 상대경로 파일을 CWD에 만든다 → supervisord가 FORECAST_DATA_DIR에서 실행.

# /forecast 인증은 이제 Caddy forward_auth 가 앱(/api/auth/verify)에 물어본다.
# 기동 시 bcrypt 해시를 만들던 basic_auth 조각은 필요 없어졌다 - 로그인은 앱에서 1회뿐이다.
if [ -z "${APP_PASSWORD:-}" ]; then
  echo "[entrypoint] WARNING: APP_PASSWORD가 비어 있어 앱과 /forecast가 인증 없이 열립니다(사내망 전용). 공개 배포에서는 반드시 설정하세요." >&2
fi

if [ -z "${SECRET_KEY:-}" ]; then
  echo "[entrypoint] WARNING: SECRET_KEY가 없어 임시 키로 기동합니다 — 재시작마다 로그인이 풀립니다. Render/.env에 SECRET_KEY를 설정하세요." >&2
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "[entrypoint] INFO: DATABASE_URL 없음 → SQLite(${DATA_DIR:-/data/budget}/budget.db). 무료 PaaS는 디스크가 비영속이므로 Supabase PostgreSQL 사용을 권장." >&2
fi

exec supervisord -c /srv/deploy/supervisord.conf
