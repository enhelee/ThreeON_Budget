@echo off
chcp 65001 >nul
cd /d "%~dp0budget_app"
echo [ThreeON] 예산 실적 집계(budget_app, FastAPI) - http://localhost:8010
if not exist .env echo [안내] budget_app\.env 가 없습니다. ..\.env.example 을 복사해 APP_PASSWORD 를 설정하면 로그인이 켜집니다.
py -m pip install -r requirements.txt -q
start "" http://localhost:8010
py -m uvicorn server:app --port 8010
pause
