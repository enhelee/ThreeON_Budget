#!/usr/bin/env bash
# Mac/Linux: 두 앱을 각자 터미널에서 실행
cd "$(dirname "$0")"
case "${1:-}" in
  budget)   cd app && python3 -m pip install -r requirements.txt -q && python3 -m uvicorn server:app --port 8010 ;;
  forecast) cd forecast && python3 -m pip install -r requirements.txt -q && python3 -m streamlit run app.py --server.address=127.0.0.1 --browser.gatherUsageStats=false ;;
  *) echo "사용법: bash 실행_mac.sh budget | forecast" ;;
esac
