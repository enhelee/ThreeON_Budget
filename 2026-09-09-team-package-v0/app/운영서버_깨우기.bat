@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 운영 서버를 깨웁니다 (발표 10분 전에 실행)
py scripts\wake_prod.py
pause
