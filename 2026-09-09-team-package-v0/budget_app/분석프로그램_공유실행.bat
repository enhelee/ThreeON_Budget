@echo off
cd /d "%~dp0"

for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /R "IPv4"') do (
    for /f "tokens=1" %%b in ("%%a") do set MYIP=%%b
)

echo ============================================================
echo   예산·실적 분석 웹서버 (공유 모드)
echo.
echo   ** 같은 네트워크의 동료에게 아래 주소를 알려주세요 **
echo   http://%MYIP%:8010
echo ============================================================
echo.
start "" http://localhost:8010
py -m uvicorn server:app --host 0.0.0.0 --port 8010
