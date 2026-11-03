@echo off
rem Installs dependencies and builds the frontend. Safe to run again.
setlocal
cd /d "%~dp0"

where python >nul 2>nul || (echo Python wasn't found. Install Python 3.11+ and Node.js 20+ first.& goto :failed)
where npm >nul 2>nul || (echo npm wasn't found. Install Python 3.11+ and Node.js 20+ first.& goto :failed)

if not exist "backend\.venv" (
    echo Creating Python environment...
    python -m venv backend\.venv || goto :failed
)
echo Installing backend packages...
"backend\.venv\Scripts\python.exe" -m pip install -q -r backend\requirements-dev.txt || goto :failed

echo Installing frontend packages...
pushd frontend
rem npm is itself a batch file, so it needs "call" or this script would stop after it.
call npm install --no-fund --no-audit || (popd & goto :failed)
call npm run build || (popd & goto :failed)
popd

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo Created .env. Add your HIBP_API_KEY there to enable breach checks.
)
echo.
echo Setup complete. Start the app with run.bat
rem Run.bat passes an argument, so only a double-clicked setup waits for a key.
if "%~1"=="" pause
exit /b 0

:failed
echo Setup failed.
if "%~1"=="" pause
exit /b 1
