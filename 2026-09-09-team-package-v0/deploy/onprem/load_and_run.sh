#!/usr/bin/env bash
# [사내 서버 · Linux] 반입한 이미지를 적재하고 띄운다. 업데이트도 같은 명령이다.
#
#   bash deploy/onprem/load_and_run.sh <threeon-budget_<커밋>.tar.gz> [--pg]
#
#   --pg  : PostgreSQL 컨테이너까지 함께(.env 의 PG_PASSWORD 필요, DATABASE_URL 을 postgres 로).
#           없으면 SQLite(볼륨 budget_data) 모드.
#
# 이 서버에는 인터넷이 없다는 전제다 — 절대 빌드하지 않는다(--no-build).
# 빌드가 걸리면 pip·npm 이 밖으로 나가려다 조용히 오래 실패한다.
set -euo pipefail
cd "$(dirname "$0")/../.."        # 패키지 루트: 여기 .env 와 deploy/ 가 있어야 한다

TAR=${1:?사용법: load_and_run.sh <threeon-budget_<커밋>.tar.gz> [--pg]}
COMPOSE="docker compose -f deploy/docker-compose.yml"

[ -f "$TAR" ] || { echo "파일이 없습니다: $TAR" >&2; exit 1; }
command -v docker >/dev/null || { echo "docker 가 없습니다." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "docker compose(v2) 가 없습니다 — Docker Engine 에 compose 플러그인을 설치하세요." >&2; exit 1; }

# ── 1. 반입 파일 무결성 ─────────────────────────────────────────────
if [ -f "$TAR.sha256" ]; then
  echo "[1/5] 체크섬 확인"
  ( cd "$(dirname "$TAR")" && sha256sum -c "$(basename "$TAR").sha256" )
else
  echo "[1/5] 체크섬 파일(.sha256) 없음 — 건너뜀"
fi

# ── 2. .env ───────────────────────────────────────────────────────────
echo "[2/5] .env 확인"
[ -f .env ] || { echo ".env 가 없습니다 — .env.example 을 .env 로 복사해 APP_PASSWORD · SECRET_KEY 를 채우세요." >&2; exit 1; }
for k in APP_PASSWORD SECRET_KEY; do
  grep -Eq "^${k}=.+" .env || { echo ".env 의 ${k} 가 비어 있습니다." >&2; exit 1; }
done
PROFILE=""
if [ "${2:-}" = "--pg" ]; then
  grep -Eq "^PG_PASSWORD=.+" .env || { echo "--pg 를 쓰려면 .env 의 PG_PASSWORD 가 필요합니다." >&2; exit 1; }
  PROFILE="--profile pg"
fi
HOST_PORT=$(grep -E '^HOST_PORT=' .env | cut -d= -f2- || true)
HOST_PORT=${HOST_PORT:-8080}

# ── 3. 이미지 적재 → latest 태그 ─────────────────────────────────────
echo "[3/5] 이미지 적재  $TAR"
LOADED=$(docker load -i "$TAR" | sed -n 's/^Loaded image: //p' | tail -n1)
[ -n "$LOADED" ] || { echo "docker load 가 이미지 이름을 돌려주지 않았습니다 — 파일이 손상됐을 수 있습니다." >&2; exit 1; }
echo "      적재됨: $LOADED"
docker tag "$LOADED" threeon-budget:latest      # compose 는 latest 를 본다. 롤백 = 이전 태그를 다시 latest 로

# ── 4. 기동 (빌드 금지) ───────────────────────────────────────────────
echo "[4/5] 기동  ($COMPOSE $PROFILE up -d --no-build)"
$COMPOSE $PROFILE up -d --no-build

# ── 5. 헬스체크 대기 ─────────────────────────────────────────────────
echo "[5/5] /healthz 대기 (최대 90초)"
for i in $(seq 1 30); do
  if BODY=$(curl -fsS "http://127.0.0.1:${HOST_PORT}/healthz" 2>/dev/null); then
    echo "      $BODY"
    echo
    echo "기동 완료 → http://<서버IP>:${HOST_PORT}/   (점검: bash deploy/onprem/check.sh)"
    exit 0
  fi
  sleep 3
done
echo "90초 안에 /healthz 가 응답하지 않았습니다. 최근 로그:" >&2
$COMPOSE logs --tail=40 app >&2 || true
echo "포트 ${HOST_PORT} 충돌이면 .env 의 HOST_PORT 를 바꾸세요." >&2
exit 1
