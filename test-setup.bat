@echo off
REM RegWatch local test: runs checklist steps A1-A8, C11-C12, then B9-B10.
REM C runs before B because "npm run build" and "npm run dev" must not share the .next folder at the same time.
REM Double-click it, or run it from a terminal in this folder. A log of every step goes to test-logs\.
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if not exist test-logs mkdir test-logs
set "SUMMARY=test-logs\summary.txt"
echo RegWatch test run %DATE% %TIME% > "%SUMMARY%"
set "PY=.venv\Scripts\python.exe"

call :step "A1 git pull" "git pull --ff-only" A1
call :step "A2 make .venv" "if not exist .venv\Scripts\python.exe python -m venv .venv" A2
call :step "A3 pip install backend requirements" "%PY% -m pip install -q -r backend\requirements.txt" A3
call :step "A4 npm install in frontend" "cd frontend && npm install --no-fund --no-audit && cd .." A4

echo.
echo === A5 create .env ===
if exist .env (
  echo .env already exists, left as it is.
  echo [OK]   A5 .env already existed, not changed >> "%SUMMARY%"
) else (
  > .env (
    echo ENVIRONMENT=development
    echo DATABASE_URL=sqlite+aiosqlite:///./data/regwatch.db
    echo SYNC_DATABASE_URL=sqlite:///./data/regwatch.db
    echo STORAGE_DRIVER=local
    echo STORAGE_LOCAL_ROOT=./storage
    echo SEED_ON_STARTUP=false
    echo SCHEDULER_ENABLED=false
    echo VISION_WORKER_ENABLED=true
    echo ANALYSIS_PROVIDER=gemini
    echo ALERTS_KICK_AFTER_COMMIT=true
  )
  echo Created .env
  echo [OK]   A5 created .env >> "%SUMMARY%"
)
if not exist data mkdir data

call :step "A6 alembic upgrade head" "%PY% -m alembic upgrade head" A6
call :step "A7 seed admin + bank + test logins" "%PY% -m backend.scripts.seed && %PY% -m backend.scripts.seed_test_users" A7

echo.
echo === A8 copy test PDFs to F:\regwatch-test-pdfs ===
if not exist "F:\regwatch-test-pdfs" mkdir "F:\regwatch-test-pdfs"
set A8OK=1
for %%F in (
  backend\app\tests\fixtures\corpus\bb_brpd_2024_15.pdf
  backend\app\tests\fixtures\corpus\bb_brpd_2024_16.pdf
  backend\app\tests\fixtures\genuine_corpus\bb_smespd_2026_05_udyog.pdf
  backend\app\tests\fixtures\corpus\gold_scanned_english.pdf
) do (
  copy /Y "%%F" "F:\regwatch-test-pdfs\" >nul || set A8OK=0
)
if "!A8OK!"=="1" (echo [OK]   A8 4 PDFs copied >> "%SUMMARY%") else (echo [FAIL] A8 a PDF did not copy >> "%SUMMARY%")

echo.
echo === C11 backend tests (takes about 5 minutes) ===
set VISION_WORKER_ENABLED=false
%PY% -m pytest -q -p no:cacheprovider > test-logs\C11.log 2>&1
set VISION_WORKER_ENABLED=
git checkout -- backend/app/tests/fixtures
for /f "delims=" %%L in ('findstr /R /C:"passed" test-logs\C11.log') do set "C11LINE=%%L"
echo !C11LINE!
echo [INFO] C11 pytest: !C11LINE! >> "%SUMMARY%"
echo        Known old failures (7): 6 failed + 1 error in test_phase3_6/3_8/3_9/4_0_1/4_experience/test_storage. See test-logs\C11.log >> "%SUMMARY%"

call :step "C12 frontend build" "cd frontend && npm run build && cd .." C12a
call :step "C12 frontend lint" "cd frontend && npm run lint && cd .." C12b

echo.
echo === B9 start backend (new window) ===
start "RegWatch backend" cmd /k "%PY% -m uvicorn backend.app.main:app --reload --port 8000"
set B9OK=0
for /L %%i in (1,1,60) do (
  if "!B9OK!"=="0" (
    curl -s http://localhost:8000/api/v1/health | findstr /I "ok" >nul && set B9OK=1
    if "!B9OK!"=="0" ping -n 3 127.0.0.1 >nul
  )
)
if "!B9OK!"=="1" (echo [OK]   B9 backend health says ok >> "%SUMMARY%") else (echo [FAIL] B9 backend did not answer in 2 minutes, see its window >> "%SUMMARY%")

echo.
echo === B10 start frontend (new window) ===
start "RegWatch frontend" cmd /k "cd frontend && npm run dev"
set B10OK=0
for /L %%i in (1,1,60) do (
  if "!B10OK!"=="0" (
    curl -s -o nul -w "%%{http_code}" http://localhost:3000 | findstr "200" >nul && set B10OK=1
    if "!B10OK!"=="0" ping -n 3 127.0.0.1 >nul
  )
)
if "!B10OK!"=="1" (
  echo [OK]   B10 frontend is up at http://localhost:3000 >> "%SUMMARY%"
  start "" http://localhost:3000
) else (
  echo [FAIL] B10 frontend did not answer in 2 minutes, see its window >> "%SUMMARY%"
)

echo.
echo ================= RESULT =================
type "%SUMMARY%"
echo ==========================================
echo Logs for each step are in test-logs\. Test logins are in TickTick ("RegWatch build test").
echo Leave the two server windows open while you test. Close them to stop.
pause
exit /b 0

:step
REM %1 = label, %2 = command, %3 = log name
echo.
echo === %~1 ===
cmd /c "%~2" > "test-logs\%~3.log" 2>&1
if errorlevel 1 (
  echo [FAIL] %~1  ^(see test-logs\%~3.log^)
  echo [FAIL] %~1  ^(see test-logs\%~3.log^) >> "%SUMMARY%"
) else (
  echo [OK]   %~1
  echo [OK]   %~1 >> "%SUMMARY%"
)
exit /b 0
