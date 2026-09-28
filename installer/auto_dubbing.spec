# -*- mode: python ; coding: utf-8 -*-
# 설치 파일용 빌드: auto_dubbing_tts.exe(컨트롤 패널) + _internal 폴더.
# installer\build.ps1 이 실행한다. torch/easyocr 은 별도 환경(ocr_env)에서 돌리므로 넣지 않는다.
import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.dirname(SPECPATH)
SRC = os.path.join(ROOT, "src")
ICON = os.path.join(ROOT, "icon", "icon.ico")

datas, binaries, hiddenimports = [], [], []
# Windows OCR(winrt) 는 네임스페이스 패키지 + pyd 여서 자동 탐지가 안 된다
d, b, h = collect_all("winrt")
datas += d
binaries += b
hiddenimports += h

app = Analysis(
    [os.path.join(SRC, "main.py")],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["torch", "torchvision", "easyocr", "cv2", "scipy", "matplotlib"],
)

exe = EXE(PYZ(app.pure), app.scripts, [], exclude_binaries=True, name="auto_dubbing_tts",
          console=False, icon=ICON)

coll = COLLECT(exe, app.binaries, app.datas, name="AutoDubbingTTS")
