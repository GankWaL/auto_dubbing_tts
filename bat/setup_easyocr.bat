@echo off
rem One-time setup for the CLOVA CRAFT + EasyOCR engine: a separate venv (ocr_env) with CUDA torch + easyocr.
rem Works for both the source checkout and the installed app (run from the install folder).
rem Large download (torch ~2.5 GB). EasyOCR downloads its Korean model (~100 MB) on first use.
cd /d "%~dp0.."
if not exist ocr_env\Scripts\python.exe (
    where python >nul 2>nul || (echo Python 3.10+ is required: winget install Python.Python.3.11& pause& exit /b 1)
    echo [1/3] python venv (ocr_env)...
    python -m venv ocr_env
)
echo [2/3] torch with CUDA 12.1 (large download, first run only)...
ocr_env\Scripts\python -m pip install --quiet torch torchvision --index-url https://download.pytorch.org/whl/cu121
echo [3/3] easyocr + pillow...
ocr_env\Scripts\python -m pip install --quiet -r requirements-easyocr.txt
ocr_env\Scripts\python -c "import torch, easyocr; print('torch', torch.__version__, 'cuda:', torch.cuda.is_available())"
echo.
echo Done. Choose "CLOVA CRAFT + EasyOCR" as the OCR engine in the control panel - the server starts automatically.
pause
