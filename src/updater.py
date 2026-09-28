"""GitHub 릴리스 기반 업데이트 확인·설치.

설치본(exe): 최신 릴리스의 설치 파일(AutoDubbingTTS-Setup-*.exe)을 내려받아 조용히 재설치한다.
           설치 파일은 실행 중인 앱을 끄고 덮어쓴 뒤 앱을 다시 띄운다 (installer/auto_dubbing.iss).
소스 실행:  릴리스가 더 새로우면 git pull --ff-only 로 받아온다 (재시작은 사용자가).
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from app_version import VERSION

REPO = "GankWaL/auto_dubbing_tts"
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases"
INSTALLED = bool(getattr(sys, "frozen", False))
BASE_DIR = (
    os.path.dirname(sys.executable) if INSTALLED
    else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def parse_version(text: str) -> tuple:
    """'release-0.0.2' / 'v0.0.2' / '0.0.2' → (0, 0, 2)"""
    return tuple(int(n) for n in re.findall(r"\d+", text))


def fetch_latest_release() -> dict | None:
    """GitHub 최신 릴리스 정보. 릴리스가 없으면 None, 네트워크 오류는 예외로 올린다."""
    req = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "auto-dubbing-tts"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def is_newer(release: dict) -> bool:
    return parse_version(release.get("tag_name", "")) > parse_version(VERSION)


def installer_asset(release: dict) -> dict | None:
    return next(
        (a for a in release.get("assets", []) if a.get("name", "").lower().endswith(".exe")),
        None,
    )


def release_notes(release: dict, limit: int = 600) -> str:
    notes = (release.get("body") or "").strip()
    return notes[:limit] + " ..." if len(notes) > limit else notes


def download_asset(asset: dict, progress=None) -> str:
    """설치 파일을 임시 폴더에 내려받고 경로를 반환한다. progress(받은 바이트, 전체 바이트) 콜백."""
    path = os.path.join(tempfile.gettempdir(), asset["name"])
    total = int(asset.get("size") or 0)

    def hook(blocks, block_size, _total):
        if progress:
            progress(min(blocks * block_size, total) if total else blocks * block_size, total)

    urllib.request.urlretrieve(asset["browser_download_url"], path, reporthook=hook)
    return path


def run_installer(setup_path: str) -> None:
    """설치 파일을 조용히 실행한다. 호출한 쪽은 바로 종료해야 exe 를 덮어쓸 수 있다."""
    subprocess.Popen([setup_path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])


def git_pull() -> tuple[bool, str]:
    """소스 실행용. (성공 여부, 출력)."""
    try:
        out = subprocess.run(
            ["git", "pull", "--ff-only"], cwd=BASE_DIR, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120, creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    return out.returncode == 0, (out.stdout + out.stderr).strip()
