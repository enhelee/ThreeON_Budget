@echo off
chcp 65001 >nul
cd /d "%~dp0forecast_app"
echo [ThreeON] 예산예측프로그램(팀공유 v2, Streamlit) - http://127.0.0.1:8501
py -m pip install -r requirements.txt -q
py -m streamlit run app.py --server.address=127.0.0.1 --browser.gatherUsageStats=false
pause
