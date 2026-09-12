@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 예산 실적 집계 프로그램
echo ==================================================
echo   예산 실적 집계 프로그램 (Streamlit 웹앱)
echo ==================================================
echo.

set "PYCMD="
py --version >nul 2>&1
if not errorlevel 1 set "PYCMD=py"
if not defined PYCMD (
    python --version >nul 2>&1
    if not errorlevel 1 set "PYCMD=python"
)
if not defined PYCMD (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo        https://www.python.org/downloads/ 에서 Python 3.10 이상을 설치한 뒤
    echo        (설치 시 "Add Python to PATH" 체크^) 다시 실행하세요.
    echo.
    pause
    exit /b 1
)

echo [1/2] 필요한 패키지 확인/설치 중... (최초 1회는 다소 걸립니다)
%PYCMD% -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 echo [경고] 패키지 설치 실패(오프라인일 수 있음). 기존 설치로 계속 진행합니다.

echo.
echo [2/2] 웹앱을 시작합니다. 잠시 후 브라우저가 자동으로 열립니다.
echo        (열리지 않으면 브라우저에서 http://localhost:8501 접속)
echo        종료하려면 이 창에서 Ctrl+C 를 누르세요.
echo.
%PYCMD% -m streamlit run app.py

echo.
echo 프로그램이 종료되었습니다.
pause
