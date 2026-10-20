@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto native
where docker >nul 2>nul
if not errorlevel 1 goto docker
where python >nul 2>nul
if errorlevel 1 goto missing
python -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
:native
.venv\Scripts\python.exe -B tools\start_full_demo.py --open-browser
if errorlevel 1 goto failed
exit /b 0
:docker
docker compose up --build
if errorlevel 1 goto failed
exit /b 0
:missing
echo Install Docker Desktop, or Python 3.12+ and a local MySQL 8 server.
:failed
echo Full application startup failed. See README.md for database configuration.
pause
exit /b 1
