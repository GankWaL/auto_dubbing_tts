"""설정 파일(config/settings.json) 로드·저장.

영역 좌표, OCR·캡처 옵션, 재생 정책, 화자별 목소리 매핑을 한 파일에 둔다.
"""

import json
import os
import sys

BASE_DIR = (
    os.path.dirname(sys.executable)
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
CONFIG_DIR = os.path.join(BASE_DIR, "config")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

DEFAULTS: dict = {
    # 화면 영역 (x, y, w, h) — 가상 화면 절대 좌표. None 이면 미설정.
    "regions": {"dialogue": None, "name": None},
    # engine: "windows" | "easyocr" | "clova_api" (ocr.ENGINES). scale: OCR 전 확대 배율
    "ocr": {"engine": "windows", "lang": "ko", "scale": 2.0},
    # interval_ms: 캡처 주기, stable_frames: OCR 텍스트가 이만큼 연속으로 같아야(타자 효과 종료) 읽기 시작
    # change_threshold: 프레임 간 어느 셀이든 밝기 차이(0~255)가 이보다 크면 화면이 '바뀜' → OCR 실행
    "capture": {"interval_ms": 150, "stable_frames": 3, "change_threshold": 24.0},
    # policy: "queue"(순서대로 모두 읽기) | "latest"(새 대사가 오면 대기·재생 중인 것을 끊고 최신만)
    "playback": {"device": None, "policy": "latest", "volume": 1.0},
    # 미등록 화자 / 이름 없는 대사(해설) 에 쓰는 목소리
    "default_voice": "선히",
    "narrator_voice": "인준",
    # 화자 이름 -> {"voice", "speed", "emotion"}
    "speakers": {},
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict:
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    return _merge(DEFAULTS, data)


def save(settings: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_FILE)
