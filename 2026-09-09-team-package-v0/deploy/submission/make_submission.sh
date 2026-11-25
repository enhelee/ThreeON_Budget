#!/usr/bin/env sh
# 공모전(공공 GitLab) 제출용 폴더를 만든다 — git 이력 없이, 실데이터가 담길 수 있는 것은 빼고.
#   sh deploy/submission/make_submission.sh <나갈 폴더>
# 빼는 것: 발표자료(실화면 녹화), 운영 점검·인수인계 문서(실제 집계 숫자), 실데이터 파일을 읽는 e2e 테스트,
#          개발 잔재(.venv·node_modules·빌드 결과·DB·산출물). 넣는 것: 앱·배포·가짜 데이터·필수 문서 두 개.
set -eu
SRC="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${1:?나갈 폴더를 지정하세요}"
[ -e "$OUT" ] && { echo "이미 있는 폴더입니다: $OUT" >&2; exit 1; }
mkdir -p "$OUT/docs"

rsync -a \
  --exclude '.venv' --exclude 'node_modules' --exclude 'static' --exclude '__pycache__' --exclude '.pytest_cache' \
  --exclude 'data' --exclude 'output' --exclude '*.db' --exclude '.env' --exclude 'test_data' \
  --exclude 'tests/test_e2e_actual.py' --exclude 'tests/test_e2e_real.py' \
  "$SRC/app" "$SRC/deploy" "$OUT/"
rm -rf "$OUT/deploy/submission"
cp "$SRC/docs/사내이관_가이드.md" "$SRC/docs/보안설계.md" "$OUT/docs/"
cp "$SRC/.env.example" "$SRC/.dockerignore" "$SRC/.gitignore" "$SRC/.gitattributes" "$OUT/"
cp "$SRC/deploy/submission/README.md" "$OUT/README.md"

echo "제출 폴더: $OUT ($(find "$OUT" -type f | wc -l | tr -d ' ')개 파일, $(du -sh "$OUT" | cut -f1))"
