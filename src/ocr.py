"""OCR 엔진 공통 인터페이스 + Windows 내장 OCR (Windows.Media.Ocr).

엔진은 recognize(img, scale) -> OcrResult 만 지키면 된다. 다른 엔진은 별도 모듈에 두고
create_engine() 에서 필요할 때만 임포트한다 (torch 같은 무거운 의존성은 선택 설치).

  windows   Windows 내장 OCR — 설치 없음, 빠름 (기본)
  easyocr   네이버 CLOVA AI 의 CRAFT 검출기 + EasyOCR 한국어 인식 (GPU 권장, bat\\setup_easyocr.bat)
  clova_api 네이버 클라우드 CLOVA OCR API (유료, .env 키 필요)
"""

import asyncio
from dataclasses import dataclass, field

from PIL import Image

ENGINES = {
    "windows": "Windows 내장 OCR (기본)",
    "easyocr": "CLOVA CRAFT + EasyOCR (GPU, 별도 설치)",
    "clova_api": "CLOVA OCR API (네이버 클라우드, 유료)",
}


@dataclass
class OcrLine:
    text: str
    # 라인 바운딩 박스 (x, y, w, h) — 원본 이미지 좌표
    box: tuple[int, int, int, int] = (0, 0, 0, 0)


@dataclass
class OcrResult:
    lines: list[OcrLine] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


class BaseOcr:
    name = "base"
    label = "OCR"

    def recognize(self, img: Image.Image, scale: float = 1.0) -> OcrResult:
        raise NotImplementedError


def prepare_image(img: Image.Image, scale: float, max_dim: int | None = None) -> Image.Image:
    """작은 글자는 확대하면 인식률이 오른다. max_dim 이 있으면 그 크기를 넘지 않게 줄인다."""
    if scale != 1.0:
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
    if max_dim:
        longest = max(img.width, img.height)
        if longest > max_dim:
            ratio = max_dim / longest
            img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
    return img


def group_lines(items: list[tuple], scale: float) -> list[OcrLine]:
    """(x, y, w, h, text) 조각들을 세로 위치로 줄 묶음 → 줄 안에서는 왼쪽부터 정렬.

    검출기가 단어·구 단위 박스를 돌려주는 엔진(EasyOCR, CLOVA API)용. 좌표는 scale 로 되돌린다.
    """
    lines: list[list[tuple]] = []
    for item in sorted(items, key=lambda it: (it[1] + it[3] / 2, it[0])):
        cy, h = item[1] + item[3] / 2, item[3]
        for line in lines:
            ly = sum(i[1] + i[3] / 2 for i in line) / len(line)
            lh = sum(i[3] for i in line) / len(line)
            if abs(cy - ly) < 0.6 * max(h, lh):
                line.append(item)
                break
        else:
            lines.append([item])
    out = []
    for line in lines:
        line.sort(key=lambda it: it[0])
        x0 = min(i[0] for i in line)
        y0 = min(i[1] for i in line)
        x1 = max(i[0] + i[2] for i in line)
        y1 = max(i[1] + i[3] for i in line)
        out.append(OcrLine(
            text=" ".join(i[4] for i in line).strip(),
            box=(int(x0 / scale), int(y0 / scale), int((x1 - x0) / scale), int((y1 - y0) / scale)),
        ))
    return out


def create_engine(cfg: dict) -> BaseOcr:
    """settings["ocr"] 로 엔진 생성. 실패하면 이유를 담은 RuntimeError."""
    name = cfg.get("engine", "windows")
    lang = cfg.get("lang", "ko")
    if name == "windows":
        return WindowsOcr(lang)
    if name == "easyocr":
        from ocr_easyocr import create_easyocr

        return create_easyocr(lang)
    if name == "clova_api":
        from ocr_clova import ClovaApiOcr

        return ClovaApiOcr(lang)
    raise RuntimeError(f"알 수 없는 OCR 엔진: {name}")


# ---------------- Windows 내장 OCR ----------------

def available_languages() -> list[str]:
    from winrt.windows.media.ocr import OcrEngine

    return [lang.language_tag for lang in OcrEngine.available_recognizer_languages]


class WindowsOcr(BaseOcr):
    """Windows.Media.Ocr. 스레드 세이프하지 않으므로 파이프라인 스레드에서만 쓴다.

    추가 설치 없이 Windows 10/11 의 OCR 엔진을 쓴다. 한국어 인식은 Windows 에
    한국어 언어 팩(OCR 포함)이 설치되어 있어야 한다 — 한국어 Windows 에는 기본 포함.
    """

    name = "windows"
    label = "Windows 내장 OCR"

    def __init__(self, lang: str = "ko"):
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine

        self.lang = lang
        self.engine = OcrEngine.try_create_from_language(Language(lang))
        if self.engine is None:
            raise RuntimeError(
                f"Windows OCR 이 '{lang}' 언어를 지원하지 않습니다. "
                f"설정 → 시간 및 언어 → 언어에서 언어 팩(OCR)을 설치해주세요. "
                f"사용 가능: {', '.join(available_languages()) or '없음'}"
            )
        self.max_dim = OcrEngine.max_image_dimension

    @staticmethod
    def _to_bitmap(img: Image.Image):
        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.storage.streams import DataWriter

        if img.mode != "RGBA":
            img = img.convert("RGBA")
        writer = DataWriter()
        writer.write_bytes(img.tobytes("raw", "BGRA"))
        return SoftwareBitmap.create_copy_from_buffer(
            writer.detach_buffer(), BitmapPixelFormat.BGRA8, img.width, img.height
        )

    async def recognize_async(self, img: Image.Image, scale: float = 1.0) -> OcrResult:
        img = prepare_image(img, scale, self.max_dim)
        result = await self.engine.recognize_async(self._to_bitmap(img))
        lines = []
        for line in result.lines:
            xs, ys, xe, ye = [], [], [], []
            for word in line.words:
                r = word.bounding_rect
                xs.append(r.x)
                ys.append(r.y)
                xe.append(r.x + r.width)
                ye.append(r.y + r.height)
            box = (0, 0, 0, 0)
            if xs:
                box = (
                    int(min(xs) / scale), int(min(ys) / scale),
                    int((max(xe) - min(xs)) / scale), int((max(ye) - min(ys)) / scale),
                )
            lines.append(OcrLine(text=line.text, box=box))
        return OcrResult(lines=lines)

    def recognize(self, img: Image.Image, scale: float = 1.0) -> OcrResult:
        """동기 호출 — 파이프라인 스레드에서 사용."""
        return asyncio.run(self.recognize_async(img, scale))


if __name__ == "__main__":
    import sys
    import time

    # 사용법: python src\ocr.py <이미지> [엔진] — 엔진별 인식 결과·소요 시간 비교
    if len(sys.argv) < 2:
        print("지원 언어(Windows):", available_languages())
        sys.exit(0)
    image = Image.open(sys.argv[1])
    names = sys.argv[2:] or ["windows"]
    for n in names:
        eng = create_engine({"engine": n, "lang": "ko"})
        t = time.perf_counter()
        res = eng.recognize(image, 2.0)
        print(f"== {eng.label} {(time.perf_counter() - t) * 1000:.0f}ms")
        for ln in res.lines:
            print("  ", ln.box, ln.text)
