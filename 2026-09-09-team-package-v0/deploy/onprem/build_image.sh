#!/usr/bin/env bash
# [인터넷 PC] 이미지를 만들어 파일로 저장한다 — 이 파일을 사내 서버로 반입한다.
#
#   bash deploy/onprem/build_image.sh [출력폴더=dist]
#
# 결과: dist/threeon-budget_<커밋>.tar.gz + .sha256
# 반입할 것: 위 두 파일 · deploy/ 폴더 · .env(.env.example 을 복사해 작성)
#
# 커밋 해시를 --build-arg 로 넣는 이유: /healthz 의 "commit" 이 사내에서도 찍혀야
# «지금 떠 있는 게 어느 버전인가»를 판별할 수 있다(Render 는 자동으로 넣어 주지만 사내는 아니다).
set -euo pipefail
cd "$(dirname "$0")/../.."        # 패키지 루트(2026-09-09-team-package-v0)

IMG=threeon-budget
OUT=${1:-dist}
SHA=$(git rev-parse --short HEAD 2>/dev/null || echo manual)

command -v docker >/dev/null || { echo "docker 가 없습니다. Docker Engine 또는 Docker Desktop 을 설치하세요." >&2; exit 1; }

echo "[1/3] 빌드  $IMG:$SHA  (프론트 빌드 + pip 설치, 처음은 5~10분)"
docker build -f deploy/Dockerfile --build-arg APP_COMMIT="$SHA" -t "$IMG:$SHA" -t "$IMG:latest" .

echo "[2/3] 저장  $OUT/${IMG}_${SHA}.tar.gz"
mkdir -p "$OUT"
docker save "$IMG:$SHA" | gzip > "$OUT/${IMG}_${SHA}.tar.gz"

echo "[3/3] 체크섬"
( cd "$OUT" && sha256sum "${IMG}_${SHA}.tar.gz" > "${IMG}_${SHA}.tar.gz.sha256" && cat "${IMG}_${SHA}.tar.gz.sha256" )

echo
echo "완료. 반입할 것:"
echo "  $OUT/${IMG}_${SHA}.tar.gz  (+ .sha256)"
echo "  deploy/            (docker-compose.yml · onprem/)"
echo "  .env               (.env.example 복사 후 APP_PASSWORD · SECRET_KEY 작성)"
echo "서버에서:  bash deploy/onprem/load_and_run.sh <tar.gz 경로>"
