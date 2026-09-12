@echo off
chcp 65001 >nul
cd /d "%~dp0app"
echo [ThreeON] 예산 실적 집계(budget_app, FastAPI) - http://localhost:8010
if not exist .env echo [안내] app\.env 가 없습니다. ..\.env.example 을 복사해 APP_PASSWORD 를 설정하면 로그인이 켜집니다.
py -m pip install -r requirements.txt -q
if not exist static\index.html (
  echo [안내] 프론트가 빌드되지 않았습니다. web 폴더에서 npm install ^&^& npm run build 를 먼저 실행하세요.
  pause
  exit /b 1
)
start "" http://localhost:8010
py -m uvicorn server:app --port 8010
pause
