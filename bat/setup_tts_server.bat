@echo off
rem One-time setup for the custom TTS (GPT-SoVITS) inference server.
cd /d "%~dp0.."

rem python creates tts_env, git clones GPT-SoVITS (only needed on the first run)
if not exist tts_env\Scripts\python.exe (
    where python >nul 2>nul || (echo Python 3.10+ is required: winget install Python.Python.3.11& pause& exit /b 1)
)
if not exist GPT-SoVITS (
    where git >nul 2>nul || (echo Git is required: winget install Git.Git& pause& exit /b 1)
)

echo [1/5] python venv (tts_env)...
if not exist tts_env\Scripts\python.exe python -m venv tts_env

echo [2/5] installing torch with CUDA (large download, first run only)...
tts_env\Scripts\python -m pip install --quiet torch torchaudio --index-url https://download.pytorch.org/whl/cu121

echo [3/5] installing inference dependencies...
tts_env\Scripts\python -m pip install --quiet transformers huggingface_hub soundfile numpy aiohttp x_transformers einops jamo g2pk2 ko_pron ffmpeg-python fast_langdetect split-lang peft pytorch-lightning matplotlib jieba pypinyin cn2an wordsegment nltk python-mecab-ko safetensors pyyaml

echo [4/5] cloning GPT-SoVITS...
if not exist GPT-SoVITS git clone --depth 1 -q https://github.com/RVC-Boss/GPT-SoVITS.git

echo [5/5] pretrained models, safetensors conversion, compat shims...
tts_env\Scripts\python src\setup_custom_tts.py

echo.
echo Setup complete. Run bat\start_tts_server.bat to start the server.
pause
