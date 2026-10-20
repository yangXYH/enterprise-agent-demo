@echo off
chcp 65001 >nul
REM Stop backend (8000) and frontend (5717) if running
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /F /PID %%p >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5717 " ^| findstr "LISTENING"') do taskkill /F /PID %%p >nul 2>&1
exit /b 0