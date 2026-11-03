@echo off
rem Starts the app at http://127.0.0.1:8000. Loopback only: it isn't reachable from your network.
rem Closing this window stops the app and the LLM runtime it started.
setlocal
cd /d "%~dp0"
title Security Modeler

set "NEEDS_SETUP="
if not exist "backend\.venv\Scripts\python.exe" set "NEEDS_SETUP=1"
if not exist "frontend\dist\index.html" set "NEEDS_SETUP=1"
if defined NEEDS_SETUP (
    call "%~dp0setup.bat" from-run || (pause & exit /b 1)
)

echo Security Modeler: http://127.0.0.1:8000
echo Close this window or press Ctrl+C to stop.
start "" "http://127.0.0.1:8000"
cd backend
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
