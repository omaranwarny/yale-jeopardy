@echo off
rem One-command start for Windows: double-click start.bat
cd /d "%~dp0"

where python >nul 2>nul || (echo Python 3.10+ is required. Get it from https://www.python.org/downloads/ & pause & exit /b 1)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" || (echo Python 3.10 or newer is required. & pause & exit /b 1)

if not exist .venv (
  echo First run: setting up, about a minute...
  python -m venv .venv
  .venv\Scripts\python -m pip install --quiet --upgrade pip
  .venv\Scripts\python -m pip install --quiet -r requirements.txt
)

if not exist .env if not exist ..\.env echo No .env found here or one folder up: demo mode (offline AI). Add PORTKEY_API_KEY or OPENAI_API_KEY for live AI.
echo.
echo   Yale Jeopardy is running:  http://localhost:8000
echo   Close this window to stop.
echo.
start "" http://localhost:8000
.venv\Scripts\python -m uvicorn app.server:app --port 8000
