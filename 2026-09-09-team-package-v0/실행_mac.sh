#!/usr/bin/env bash
# Mac/Linux: 앱 실행. (전망 앱은 Phase 6 에서 이 앱의 5번 탭으로 흡수되어 별도 실행이 없다.)
cd "$(dirname "$0")/app"
python3 -m pip install -r requirements.txt -q && python3 -m uvicorn server:app --port 8010
