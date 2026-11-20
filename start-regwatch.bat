@echo off
REM Quick start for demos: starts the backend and the frontend and opens the app. No pull, install or tests.
REM First time on a new PC, or after big changes: run test-setup.bat instead.
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo The Python setup is missing. Run test-setup.bat once first.
  pause
  exit /b 1
)
if not exist frontend\node_modules (
  echo The frontend packages are missing. Run test-setup.bat once first.
  pause
  exit /b 1
)

echo Starting the backend...
curl -s http://localhost:8000/api/v1/health | findstr /I "ok" >nul && (echo Backend already running.) || start "RegWatch backend" cmd /k "%PY% -m uvicorn backend.app.main:app --port 8000"

echo Starting the frontend...
curl -s -o nul -w "%%{http_code}" http://localhost:3000 | findstr "200" >nul && (echo Frontend already running.) || start "RegWatch frontend" cmd /k "cd frontend && npm run dev"

echo Waiting for the app to answer (up to 2 minutes)...
set UP=0
for /L %%i in (1,1,60) do (
  if "!UP!"=="0" (
    curl -s -o nul -w "%%{http_code}" http://localhost:3000 | findstr "200" >nul && set UP=1
    if "!UP!"=="0" ping -n 3 127.0.0.1 >nul
  )
)
if "!UP!"=="1" (
  start "" http://localhost:3000
  echo RegWatch is open at http://localhost:3000. Keep the two windows open while you use it.
) else (
  echo The app did not answer in 2 minutes. Look at the two RegWatch windows for the error.
)
timeout /t 8 >nul
