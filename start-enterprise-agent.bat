@echo off
chcp 65001 >nul

set "ROOT=E:\project\enterprise-agent"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "FRONT=%ROOT%\frontend"
set "VBS=%ROOT%\runner.vbs"

REM ---- 检查依赖 ----
if exist "%PY%" goto py_ok
goto :end_fail
:py_ok
if exist "%FRONT%\node_modules" goto npm_ok
goto :end_fail
:npm_ok

REM ---- 后端端口 8000 ----
netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 goto backend_up
wscript "%VBS%" "cmd /c %PY% -m uvicorn main:app --host 127.0.0.1 --port 8000 >> %ROOT%\backend.log 2>&1"
:backend_up

REM ---- 前端端口 5717 ----
netstat -ano | findstr ":5717 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 goto frontend_up
wscript "%VBS%" "cmd /c cd /d %FRONT% && npm run dev >> %ROOT%\frontend.log 2>&1"
:frontend_up

timeout /t 6 /nobreak >nul
start "" "http://127.0.0.1:5717"
exit /b 0

:end_fail
exit /b 1