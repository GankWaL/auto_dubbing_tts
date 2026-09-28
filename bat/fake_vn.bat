@echo off
rem Test window that mimics a visual novel dialogue box.
cd /d "%~dp0.."
.venv\Scripts\python tests\fake_vn.py %*
