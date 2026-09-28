@echo off
rem Start the auto dubbing control panel.
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (echo Run bat\setup.bat first.& pause& exit /b 1)
start "" .venv\Scripts\pythonw.exe src\main.py
