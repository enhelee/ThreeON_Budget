@echo off
cd /d "%~dp0"
echo 예산·실적 분석 웹서버를 시작합니다... (http://localhost:8010)
start "" http://localhost:8010
py -m uvicorn server:app --port 8010
