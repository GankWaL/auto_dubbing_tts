"""EasyOCR 엔진 — 네이버 CLOVA AI 가 공개한 CRAFT 텍스트 검출기 + 한국어 인식 모델.

CLOVA 의 오픈소스 인식기(deep-text-recognition-benchmark)에는 공개 한국어 가중치가 없어,
같은 CRAFT 검출기 위에 한국어 인식 가중치를 제공하는 EasyOCR 로 묶는다.

두 가지 실행 방식:
  EasyOcrLocal   같은 프로세스에 easyocr/torch 가 설치돼 있을 때 (개발용 .venv 에 직접 설치한 경우)
  EasyOcrRemote  별도 환경(ocr_env)의 ocr_server.py 에 HTTP 요청 — exe 설치본은 이 방식.
                 서버가 안 떠 있으면 ocr_env 가 있을 때 자동으로 띄운다.
설치: bat\\setup_easyocr.bat (CUDA torch + easyocr, 첫 실행 때 모델 약 100MB 다운로드)
"""

import io
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import numpy as np
from PIL import Image

from ocr import BaseOcr, OcrLine, OcrResult, group_lines, prepare_image

BASE_DIR = (
    os.path.dirname(sys.executable)
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
OCR_ENV_PYTHON = os.path.join(BASE_DIR, "ocr_env", "Scripts", "python.exe")
OCR_SERVER_SCRIPT = os.path.join(BASE_DIR, "src", "ocr_server.py")
OCR_SERVER_LOG = os.path.join(BASE_DIR, "ocr_server.log")
SERVER_URL = os.getenv("EASYOCR_URL", f"http://127.0.0.1:{os.getenv('EASYOCR_PORT', '51771')}")
SERVER_START_TIMEOUT = 120  # 모델 로딩 포함


def create_easyocr(lang: str = "ko") -> BaseOcr:
    try:
        import easyocr  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        return EasyOcrRemote(lang)
    return EasyOcrLocal(lang)


class EasyOcrLocal(BaseOcr):
    name = "easyocr"
    label = "CLOVA CRAFT + EasyOCR"

    def __init__(self, lang: str = "ko", gpu: bool | None = None):
        import easyocr
        import torch

        if gpu is None:
            gpu = torch.cuda.is_available()
        langs = [lang] if lang == "en" else [lang, "en"]
        self.reader = easyocr.Reader(langs, gpu=gpu, verbose=False)
        self.label = f"CLOVA CRAFT + EasyOCR ({'GPU' if gpu else 'CPU'})"

    def recognize(self, img: Image.Image, scale: float = 1.0) -> OcrResult:
        img = prepare_image(img, scale)
        results = self.reader.readtext(np.asarray(img.convert("RGB")), detail=1, paragraph=False)
        items = []
        for bbox, text, _conf in results:
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            items.append((min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys), text))
        return OcrResult(group_lines(items, scale))


class EasyOcrRemote(BaseOcr):
    """ocr_server.py 클라이언트. 확대(scale)는 서버에서 한다."""

    name = "easyocr"
    label = "CLOVA CRAFT + EasyOCR (서버)"

    def __init__(self, lang: str = "ko"):
        self.lang = lang
        self.url = SERVER_URL
        label = ensure_server(lang)
        if label:
            self.label = f"{label} · 서버"

    def recognize(self, img: Image.Image, scale: float = 1.0) -> OcrResult:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG")
        req = urllib.request.Request(
            f"{self.url}/recognize?scale={scale}", data=buf.getvalue(),
            headers={"Content-Type": "image/png"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        if "error" in data:
            raise RuntimeError(f"EasyOCR 서버 오류: {data['error']}")
        return OcrResult([OcrLine(text=ln["text"], box=tuple(ln["box"])) for ln in data["lines"]])


def server_health() -> str | None:
    """서버가 떠 있으면 label, 아니면 None."""
    try:
        with urllib.request.urlopen(f"{SERVER_URL}/health", timeout=1) as resp:
            return json.load(resp).get("label", "EasyOCR")
    except Exception:
        return None


def _port_open() -> bool:
    host, port = SERVER_URL.split("//", 1)[1].rsplit(":", 1)
    try:
        with socket.create_connection((host, int(port)), timeout=0.5):
            return True
    except OSError:
        return False


def ensure_server(lang: str) -> str:
    """서버가 없으면 ocr_env 로 띄우고 준비될 때까지 기다린다. 못 띄우면 RuntimeError."""
    label = server_health()
    if label:
        return label
    if not os.path.isfile(OCR_ENV_PYTHON):
        raise RuntimeError(
            "EasyOCR 환경(ocr_env)이 없습니다. bat\\setup_easyocr.bat 을 먼저 실행해주세요 "
            "(Python 3.10 이상 필요, torch 약 2.5GB 다운로드)."
        )
    if not _port_open():
        log = open(OCR_SERVER_LOG, "a", encoding="utf-8")
        subprocess.Popen(
            [OCR_ENV_PYTHON, OCR_SERVER_SCRIPT, lang],
            stdout=log, stderr=subprocess.STDOUT, cwd=BASE_DIR,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    deadline = time.time() + SERVER_START_TIMEOUT
    while time.time() < deadline:
        label = server_health()
        if label:
            return label
        time.sleep(1)
    raise RuntimeError(f"EasyOCR 서버가 {SERVER_START_TIMEOUT}초 안에 준비되지 않았습니다. 로그: {OCR_SERVER_LOG}")
