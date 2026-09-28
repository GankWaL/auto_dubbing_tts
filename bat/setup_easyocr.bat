@echo off
rem One-time setup for the CLOVA CRAFT + EasyOCR engine: a separate venv (ocr_env) with torch + easyocr.
rem Same logic as the "install now" button in the control panel (src\ocr_setup.py).
rem CUDA torch if an NVIDIA GPU is present (~2.5 GB), otherwise the CPU build (~200 MB).
cd /d "%~dp0.."
where python >nul 2>nul || where py >nul 2>nul || (echo Python 3.10+ is required: winget install Python.Python.3.11& pause& exit /b 1)
python src\ocr_setup.py || py -3 src\ocr_setup.py
pause
