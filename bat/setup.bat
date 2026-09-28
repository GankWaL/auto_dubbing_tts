@echo off
rem First-time setup: create venv and install requirements.
cd /d "%~dp0.."
where python >nul 2>nul || (echo Python 3.11+ is required: winget install Python.Python.3.11& pause& exit /b 1)
if not exist .venv\Scripts\python.exe python -m venv .venv
.venv\Scripts\python -m pip install --quiet --upgrade pip
.venv\Scripts\python -m pip install --quiet -r requirements.txt
if not exist .env copy .env.example .env >nul
echo Setup complete. Run bat\start.bat
pause
