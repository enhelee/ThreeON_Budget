#!/usr/bin/env sh
# 컨테이너 기동: 볼륨 폴더 준비 → 공용 비밀번호를 Caddy basic_auth 해시로 → 세 프로세스(supervisord)
set -eu

mkdir -p "${DATA_DIR:-/data/budget}/config" "${DATA_DIR:-/data/budget}/output" "${FORECAST_DATA_DIR:-/data/forecast}"

# forecast_app(v2)이 첫 실행에 필요한 내장 양식·매칭 HTML은 코드 폴더에서 읽으므로 복사 불필요.
# 팀 v2 앱은 상대경로 파일을 CWD에 만든다 → supervisord가 FORECAST_DATA_DIR에서 실행.

# /forecast 인증 조각을 만든다. Caddyfile은 이 파일을 import만 하므로,
# 비밀번호가 있든 없든 Caddyfile 자체는 절대 손대지 않는다(문법 깨짐 방지).
AUTH_SNIPPET=/srv/deploy/forecast_auth.caddy
if [ -n "${APP_PASSWORD:-}" ]; then
  # Caddy는 평문 비밀번호를 받지 않는다 → bcrypt 해시를 기동 시 계산해 조각 파일에 기록.
  # 해시에 `$`가 들어가지만 Caddy가 확장하는 형태는 `{$VAR}`뿐이라 그대로 써도 안전하다.
  BASIC_HASH="$(caddy hash-password --plaintext "$APP_PASSWORD")"
  printf 'basic_auth {\n\t%s %s\n}\n' "${BASIC_USER:-team}" "$BASIC_HASH" > "$AUTH_SNIPPET"
  echo "[entrypoint] /forecast basic_auth 활성 (사용자: ${BASIC_USER:-team})" >&2
else
  : > "$AUTH_SNIPPET"   # 빈 파일 = 인증 지시어 없음(열림)
  echo "[entrypoint] WARNING: APP_PASSWORD가 비어 있어 /forecast가 인증 없이 열립니다(사내망 전용). 공개 배포에서는 반드시 설정하세요." >&2
fi

if [ -z "${SECRET_KEY:-}" ]; then
  echo "[entrypoint] WARNING: SECRET_KEY가 없어 임시 키로 기동합니다 — 재시작마다 로그인이 풀립니다. Render/.env에 SECRET_KEY를 설정하세요." >&2
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo "[entrypoint] INFO: DATABASE_URL 없음 → SQLite(${DATA_DIR:-/data/budget}/budget.db). 무료 PaaS는 디스크가 비영속이므로 Supabase PostgreSQL 사용을 권장." >&2
fi

exec supervisord -c /srv/deploy/supervisord.conf
