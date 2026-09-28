"""EasyOCR(CLOVA CRAFT) 환경(ocr_env) 설치.

GUI 의 "지금 설치" 와 bat\\setup_easyocr.bat 이 같은 코드를 쓴다.
시스템 Python(3.10+) 으로 venv 를 만들고 torch(NVIDIA GPU 가 있으면 CUDA, 없으면 CPU 빌드) 와
easyocr 을 설치한다. 진행 출력은 log 콜백으로 한 줄씩 넘긴다.

    python src\\ocr_setup.py          # 콘솔에서 직접 실행
"""

import os
import shutil
import subprocess
import sys

from ocr_easyocr import BASE_DIR, OCR_ENV_PYTHON

# pip 에 -r 파일로 넘기지 않고 직접 나열한다 — 한국어 로캘(cp949)에서 UTF-8 파일 읽기에 실패한다
EASYOCR_PACKAGES = ["easyocr>=1.7", "pillow>=10.0", "numpy>=1.26"]
MIN_PYTHON = (3, 10)
TORCH_INDEX_CUDA = "https://download.pytorch.org/whl/cu121"
TORCH_INDEX_CPU = "https://download.pytorch.org/whl/cpu"
PYTHON_INSTALL_HINT = "winget install Python.Python.3.11"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _probe(cmd: list[str]) -> tuple[int, int] | None:
    """해당 파이썬의 (major, minor). 실행이 안 되면 None (Microsoft Store 스텁 포함)."""
    try:
        out = subprocess.run(
            cmd + ["-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
            capture_output=True, text=True, timeout=15, creationflags=_NO_WINDOW,
        )
        if out.returncode != 0:
            return None
        major, minor = out.stdout.split()
        return int(major), int(minor)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def find_system_python() -> list[str] | None:
    """3.10 이상 시스템 파이썬 실행 명령. 없으면 None.

    exe(PyInstaller)나 이 앱의 venv 가 아닌 파이썬을 찾는다. 'py' 런처를 먼저 본다.
    """
    candidates: list[list[str]] = []
    if shutil.which("py"):
        candidates.append(["py", "-3"])
    for name in ("python", "python3"):
        path = shutil.which(name)
        if path and "WindowsApps" not in path:
            candidates.append([path])
    if not getattr(sys, "frozen", False) and sys.prefix == sys.base_prefix:
        candidates.append([sys.executable])
    for cmd in candidates:
        ver = _probe(cmd)
        if ver and ver >= MIN_PYTHON:
            return cmd
    return None


def has_nvidia_gpu() -> bool:
    return bool(shutil.which("nvidia-smi")) or os.path.isfile(
        os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe")
    )


def ocr_env_ready() -> bool:
    if not os.path.isfile(OCR_ENV_PYTHON):
        return False
    return subprocess.run(
        [OCR_ENV_PYTHON, "-c", "import torch, easyocr"],
        capture_output=True, creationflags=_NO_WINDOW,
    ).returncode == 0


def _run(cmd: list[str], log) -> int:
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", cwd=BASE_DIR, creationflags=_NO_WINDOW,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            log(f"    {line}")
    return proc.wait()


def install_ocr_env(log=print) -> bool:
    """ocr_env 를 만들고 torch + easyocr 을 설치한다. 성공 여부 반환."""
    python = find_system_python()
    if not python:
        log(f"[EasyOCR 설치] Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 이상이 필요합니다. "
            f"관리자 권한 없이 설치: {PYTHON_INSTALL_HINT}  (설치 후 다시 시도)")
        return False
    log(f"[EasyOCR 설치] 시스템 Python: {' '.join(python)}")

    if not os.path.isfile(OCR_ENV_PYTHON):
        log("[EasyOCR 설치] 1/3 가상환경(ocr_env) 생성...")
        if _run(python + ["-m", "venv", os.path.join(BASE_DIR, "ocr_env")], log) != 0:
            log("[EasyOCR 설치] 가상환경 생성 실패")
            return False

    gpu = has_nvidia_gpu()
    index = TORCH_INDEX_CUDA if gpu else TORCH_INDEX_CPU
    log(f"[EasyOCR 설치] 2/3 torch 설치 ({'CUDA 12.1, 약 2.5GB' if gpu else 'CPU 빌드, 약 200MB — NVIDIA GPU 없음'})... 수 분 걸립니다")
    pip = [OCR_ENV_PYTHON, "-m", "pip", "install", "--progress-bar", "off", "--disable-pip-version-check"]
    if _run(pip + ["torch", "torchvision", "--index-url", index], log) != 0:
        log("[EasyOCR 설치] torch 설치 실패")
        return False

    log("[EasyOCR 설치] 3/3 easyocr 설치...")
    if _run(pip + EASYOCR_PACKAGES, log) != 0:
        log("[EasyOCR 설치] easyocr 설치 실패")
        return False

    if not ocr_env_ready():
        log("[EasyOCR 설치] 설치는 끝났지만 import 확인에 실패했습니다. ocr_server.log 를 확인해주세요.")
        return False
    log("[EasyOCR 설치] 완료. 첫 실행 때 한국어 모델(약 100MB)을 내려받아 시작이 1~2분 걸릴 수 있습니다.")
    return True


if __name__ == "__main__":
    ok = install_ocr_env()
    sys.exit(0 if ok else 1)
