@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
rem Liberar puerto 5000 si habia un proceso anterior colgado
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1
start "" http://localhost:5000
python app.py
pause
