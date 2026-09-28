"""GUI 없이 파이프라인을 N초 돌려 로그를 출력한다 (fake_vn.py 와 함께 사용).

    .venv\Scripts\python tests\run_headless.py '{"dialogue": [...], "name": [...]}' [--seconds 20]
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import config  # noqa: E402
from dubbing import Dubber  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("regions", help="JSON: {dialogue: [x,y,w,h], name: [x,y,w,h]}")
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--policy", default="latest")
    args = ap.parse_args()

    settings = config.load()
    settings["regions"].update(json.loads(args.regions))
    settings["playback"]["policy"] = args.policy
    # 테스트용 화자 매핑 — 저장하지 않는다
    settings["speakers"] = {"유이": {"voice": "선히", "speed": 1.0, "emotion": "기본"},
                            "민준": {"voice": "현수", "speed": 1.0, "emotion": "기본"}}
    config.save = lambda s: None  # 테스트 중 설정 파일 오염 방지

    t0 = time.perf_counter()
    dub = Dubber(settings, log=lambda m: print(f"{time.perf_counter() - t0:6.2f}s {m}", flush=True))
    dub.start()
    try:
        time.sleep(args.seconds)
    finally:
        dub.stop()


if __name__ == "__main__":
    main()
