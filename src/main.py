"""auto_dubbing_tts 진입점 — GUI 실행."""

import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _enable_dpi_awareness() -> None:
    """tkinter 좌표와 화면 캡처 픽셀이 일치하도록 DPI 배율을 끈다 (고해상도 모니터 대응)."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


if __name__ == "__main__":
    _enable_dpi_awareness()
    from gui import main

    main()
