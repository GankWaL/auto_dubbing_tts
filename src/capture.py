"""화면 영역 캡처와 변화 감지."""

import numpy as np
from mss import MSS
from PIL import Image

Region = tuple[int, int, int, int]  # x, y, w, h (가상 화면 절대 좌표)


class ScreenGrabber:
    """mss 는 스레드마다 인스턴스를 따로 만들어야 하므로 사용하는 스레드 안에서 생성한다."""

    def __init__(self):
        self.sct = MSS()

    def grab(self, region: Region) -> Image.Image:
        x, y, w, h = region
        shot = self.sct.grab({"left": x, "top": y, "width": w, "height": h})
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    def close(self) -> None:
        self.sct.close()


def virtual_screen() -> Region:
    """모든 모니터를 합친 가상 화면 영역."""
    with MSS() as sct:
        m = sct.monitors[0]
    return (m["left"], m["top"], m["width"], m["height"])


def fingerprint(img: Image.Image, size: tuple[int, int] = (96, 24)) -> np.ndarray:
    """변화 감지용 저해상 그레이스케일 지문. 셀 하나가 글자 한 개 정도 크기다."""
    return np.asarray(img.convert("L").resize(size, Image.BILINEAR), dtype=np.float32)


def changed(a: np.ndarray | None, b: np.ndarray, threshold: float) -> bool:
    """어느 셀이든 밝기(0~255)가 threshold 이상 바뀌면 '바뀜'.

    글자 한 개가 추가되는 작은 변화도 잡아야 하므로 평균이 아니라 최대 차이를 본다.
    (글자가 바뀌었는지 최종 판단은 OCR 텍스트 비교로 한다 — dubbing.py)
    """
    if a is None:
        return True
    return float(np.abs(a - b).max()) > threshold
