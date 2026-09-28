@echo off
rem Start the custom TTS inference server (GPT-SoVITS) in tts_env.
cd /d "%~dp0.."
if not exist tts_env\Scripts\python.exe (
    echo tts_env not found. Create it first - see README "custom voice" section.
    pause
    exit /b 1
)
tts_env\Scripts\python src\custom_tts_server.py
pause
