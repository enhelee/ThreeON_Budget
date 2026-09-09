#!/usr/bin/env sh
# 컨테이너 기동: 볼륨 폴더 준비 → 공용 비밀번호를 Caddy basic_auth 해시로 → 세 프로세스(supervisord)
set -eu

mkdir -p "${DATA_DIR:-/data/budget}/config" "${DATA_DIR:-/data/budget}/output" "${FORECAST_DATA_DIR:-/data/forecast}"

# forecast_app(v2)이 첫 실행에 필요한 내장 양식·매칭 HTML은 코드 폴더에서 읽으므로 복사 불필요.
# 팀 v2 앱은 상대경로 파일을 CWD에 만든다 → supervisord가 FORECAST_DATA_DIR에서 실행.

if [ -n "${APP_PASSWORD:-}" ]; then
  # Caddy는 평문 비밀번호를 받지 않는다 → bcrypt 해시를 기동 시 계산해 환경변수로 전달
  BASIC_HASH="$(caddy hash-password --plaintext "$APP_PASSWORD")"
  export BASIC_HASH
  export BASIC_USER="${BASIC_USER:-team}"
else
  echo "[entrypoint] WARNING: APP_PASSWORD가 비어 있어 인증 없이 기동합니다(사내망 전용). 공개 배포에서는 반드시 설정하세요." >&2
  # basic_auth 블록 제거(비밀번호 없음 = 열림)
  sed -i '/basic_auth {/,/}/d' /srv/deploy/Caddyfile
fi

if [ -z "${SECRET_KEY:-}" ]; then
  echo "[entrypoint] WARNING: SECRET_KEY가 없어 임시 키로 기동합니다 — 재시작마다 로그인이 풀립니다. Render/.env에 SECRET_KEY를 설정하세요." >&2
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "[entrypoint] INFO: DATABASE_URL 없음 → SQLite(${DATA_DIR:-/data/budget}/budget.db). 무료 PaaS는 디스크가 비영속이므로 Supabase PostgreSQL 사용을 권장." >&2
fi

exec supervisord -c /srv/deploy/supervisord.conf
