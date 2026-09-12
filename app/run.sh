#!/usr/bin/env bash
# 예산 실적 집계 프로그램 실행 (macOS / Linux)
cd "$(dirname "$0")" || exit 1

echo "=================================================="
echo "  예산 실적 집계 프로그램 (Streamlit 웹앱)"
echo "=================================================="
echo

if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "[오류] Python이 설치되어 있지 않습니다."
    echo "       https://www.python.org/downloads/ 에서 Python 3.10 이상 설치 후 다시 실행하세요."
    exit 1
fi

echo "[1/2] 필요한 패키지 확인/설치 중... (최초 1회는 다소 걸립니다)"
"$PY" -m pip install --disable-pip-version-check -r requirements.txt \
    || echo "[경고] 패키지 설치 실패(오프라인일 수 있음). 기존 설치로 계속 진행합니다."

echo
echo "[2/2] 웹앱을 시작합니다. 브라우저에서 http://localhost:8501 로 접속하세요."
echo "       종료하려면 이 터미널에서 Ctrl+C 를 누르세요."
echo
exec "$PY" -m streamlit run app.py
