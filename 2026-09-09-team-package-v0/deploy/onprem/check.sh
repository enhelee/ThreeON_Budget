#!/usr/bin/env bash
# [사내 서버 · Linux] 운영 점검 — 언제든 실행. 아무것도 바꾸지 않는다.
#
#   bash deploy/onprem/check.sh
#
# 보는 것: 컨테이너 상태·헬스 · /healthz(버전·DB 종류) · 보안 헤더 · 볼륨 · 디스크 · 최근 로그
set -euo pipefail
cd "$(dirname "$0")/../.."
COMPOSE="docker compose -f deploy/docker-compose.yml"
HOST_PORT=$(grep -E '^HOST_PORT=' .env 2>/dev/null | cut -d= -f2- || true)
HOST_PORT=${HOST_PORT:-8080}
FAIL=0

echo "── 컨테이너 ──────────────────────────────────────────────"
$COMPOSE ps
HEALTH=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' threeon-budget 2>/dev/null || echo "not-running")
echo "헬스: $HEALTH"
[ "$HEALTH" = "healthy" ] || FAIL=1

echo
echo "── /healthz ──────────────────────────────────────────────"
if BODY=$(curl -fsS "http://127.0.0.1:${HOST_PORT}/healthz" 2>/dev/null); then
  echo "$BODY"
  echo "$BODY" | grep -q '"commit":"[0-9a-f]\{7\}"' || { echo "⚠ commit 이 비어 있습니다 — build_image 로 만든 이미지가 아닙니다"; FAIL=1; }
else
  echo "⚠ 응답 없음 (포트 ${HOST_PORT})"; FAIL=1
fi

echo
echo "── 보안 헤더 (Caddy 없이 앱이 직접 낸다 — 6-8) ──────────"
HDR=$(curl -sSI "http://127.0.0.1:${HOST_PORT}/healthz" 2>/dev/null || true)
for h in x-content-type-options x-frame-options referrer-policy; do
  if echo "$HDR" | grep -qi "^$h:"; then echo "  ✓ $h"; else echo "  ✗ $h 없음"; FAIL=1; fi
done

echo
echo "── 볼륨·디스크 ───────────────────────────────────────────"
docker volume ls --format '  {{.Name}}' | grep -E 'budget_data|pg_data' || echo "  ⚠ budget_data 볼륨이 없습니다"
docker system df | sed 's/^/  /'

echo
echo "── 최근 로그 20줄 ────────────────────────────────────────"
$COMPOSE logs --tail=20 app 2>/dev/null | sed 's/^/  /' || true

echo
if [ "$FAIL" = 0 ]; then echo "점검 결과: 정상"; else echo "점검 결과: 이상 있음 (위 ⚠/✗ 항목)"; exit 1; fi
