@echo off
rem Start the EasyOCR server manually (the app starts it automatically when needed).
cd /d "%~dp0.."
if not exist ocr_env\Scripts\python.exe (echo ocr_env not found. Run bat\setup_easyocr.bat first.& pause& exit /b 1)
ocr_env\Scripts\python src\ocr_server.py ko
pause
