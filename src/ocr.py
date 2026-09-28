"""OCR 엔진 공통 인터페이스 + Windows 내장 OCR (Windows.Media.Ocr).

엔진은 recognize(img, scale) -> OcrResult 만 지키면 된다. 다른 엔진은 별도 모듈에 두고
create_engine() 에서 필요할 때만 임포트한다 (torch 같은 무거운 의존성은 선택 설치).

  windows   Windows 내장 OCR — 설치 없음, 빠름 (기본)
  easyocr   네이버 CLOVA AI 의 CRAFT 검출기 + EasyOCR 한국어 인식 (GPU 권장, bat\\setup_easyocr.bat)
  clova_api 네이버 클라우드 CLOVA OCR API (유료, .env 키 필요)

recognize_robust() 는 같은 영역을 여러 전처리·배율로 읽어 다수결(medoid)로 고른다.
게임 화면은 반투명 상자·스캔라인·장식 폰트 때문에 한 번 읽기로는 글자가 흔들리는데,
변형마다 틀리는 글자가 달라서 합의를 취하면 안정된다 (docs/CLAUDE.md 벤치마크 참고).
"""

import asyncio
import difflib
import re
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageFilter, ImageOps

ENGINES = {
    "windows": "Windows 내장 OCR (기본)",
    "easyocr": "CLOVA CRAFT + EasyOCR (GPU, 별도 설치)",
    "clova_api": "CLOVA OCR API (네이버 클라우드, 유료)",
}
PAD_PX = 16  # 원본 픽셀 기준 여백 — 상자를 타이트하게 잘라도 첫 글자가 안 잘리게
_LETTER = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣA-Za-z]")


Box = tuple[int, int, int, int]  # x, y, w, h


@dataclass
class OcrLine:
    text: str
    # 라인 바운딩 박스 (x, y, w, h) — 원본 이미지 좌표
    box: Box = (0, 0, 0, 0)
    # 단어 박스들 — 기울기 추정에 쓴다 (엔진이 주지 않으면 비어 있음)
    words: list[Box] = field(default_factory=list)


@dataclass
class OcrResult:
    lines: list[OcrLine] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


# ---------------- 전처리 ----------------

def _median_color(img: Image.Image):
    arr = np.asarray(img)
    if arr.ndim == 2:
        return int(np.median(arr))
    return tuple(int(v) for v in np.median(arr.reshape(-1, arr.shape[-1]), axis=0))


def to_dark_text_gray(img: Image.Image) -> Image.Image:
    """그레이스케일로 바꾸고, 배경이 어두우면 반전해 글씨가 어둡게(문서처럼) 되도록 한다."""
    g = img.convert("L")
    if np.median(np.asarray(g)) < 128:
        g = ImageOps.invert(g)
    return g


def _otsu(a: np.ndarray) -> int:
    hist = np.bincount(a.ravel(), minlength=256).astype(np.float64)
    total, sum_all = a.size, float(np.dot(np.arange(256), hist))
    best, thr, sum_b, w_b = 0.0, 0, 0.0, 0.0
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        var = w_b * w_f * (sum_b / w_b - (sum_all - sum_b) / w_f) ** 2
        if var > best:
            best, thr = var, t
    return thr


def text_mask(gray: Image.Image, target_h: int = 48) -> Image.Image:
    """기울기 추정용 글씨 픽셀 마스크 (Otsu 이진화, 높이 target_h 로 축소해 빠르게)."""
    if gray.height > target_h:
        gray = gray.resize((max(1, int(gray.width * target_h / gray.height)), target_h), Image.BILINEAR)
    a = np.asarray(gray)
    return Image.fromarray(((a < _otsu(a)) * 255).astype(np.uint8))


def _profile_var(mask: Image.Image, axis: int) -> float:
    return float((np.asarray(mask).astype(np.float32) / 255).sum(axis=axis).var())


def estimate_shear(gray: Image.Image, max_k: float = 0.4, step: float = 0.05,
                   min_gain: float = 1.15) -> float:
    """이탤릭(전단) 보정 계수 k. x' = x + k*y 로 세웠을 때 세로 투영 분산이 최대인 k.

    확신이 없으면 0. 회전 보정 뒤에 적용한다.
    """
    mask = text_mask(gray)
    base = _profile_var(mask, axis=0)
    best_k, best_var = 0.0, base
    h = mask.height
    for k in np.arange(-max_k, max_k + step / 2, step):
        if abs(k) < step / 2:
            continue
        sheared = mask.transform(mask.size, Image.AFFINE, (1, k, -k * h / 2, 0, 1, 0), resample=Image.BILINEAR)
        var = _profile_var(sheared, axis=0)
        if var > best_var:
            best_k, best_var = float(k), var
    return best_k if base > 0 and best_var >= base * min_gain else 0.0


def normalize_skew(img: Image.Image, angle: float, shear: float, fill) -> Image.Image:
    """추정된 회전각·전단으로 글씨를 똑바로 세운다 (angle: PIL rotate 값, shear: x' = x + k*y)."""
    if angle:
        img = img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=fill)
    if shear:
        w, h = img.size
        extra = int(abs(shear) * h)
        # 출력 픽셀 (x, y) 가 입력의 (x + k*y + c, y) 를 읽는다. 잘리지 않게 폭을 늘리고 c 로 맞춘다.
        c = -shear * h if shear > 0 else 0.0
        img = img.transform((w + extra, h), Image.AFFINE, (1, shear, c, 0, 1, 0),
                            resample=Image.BICUBIC, fillcolor=fill)
    return img


def preprocess(img: Image.Image, mode: str, scale: float,
               angle: float = 0.0, shear: float = 0.0) -> tuple[Image.Image, int]:
    """(전처리된 이미지, 여백 px) 반환. 좌표 복원은 box → (box - pad) / scale (기울기 보정 시 근사).

    pad   : 배율 조정 + 배경 중간색 여백만 (색 정보 유지)
    gray  : 그레이스케일 → 어두운 배경이면 반전(밝은 글씨 → 검은 글씨) → 여백.
            색 글씨(보라색 이름 등)와 반투명 상자에 두루 무난하다.
    auto  : gray + 중앙값 필터(스캔라인·압축 노이즈 제거) + 자동 대비. 반투명 대사 상자용.
    angle/shear 가 있으면 모든 모드에서 기울기를 먼저 편다 (angle_from_words / estimate_shear).
    """
    if scale != 1.0:
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
    pad = int(PAD_PX * scale)
    if mode in ("gray", "auto"):
        g = to_dark_text_gray(img)
        g = normalize_skew(g, angle, shear, _median_color(g))
        if mode == "auto":
            g = g.filter(ImageFilter.MedianFilter(3))
            g = ImageOps.autocontrast(g, cutoff=1)
        return ImageOps.expand(g, border=pad, fill=_median_color(g)), pad
    img = normalize_skew(img, angle, shear, _median_color(img))
    return ImageOps.expand(img, border=pad, fill=_median_color(img)), pad


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


def _shift_box(box: Box, pad: int, scale: float) -> Box:
    x, y, w, h = box
    return (int((x - pad) / scale), int((y - pad) / scale), int(w / scale), int(h / scale))


def _shift(result: OcrResult, pad: int, scale: float) -> OcrResult:
    """여백·배율이 적용된 이미지의 좌표를 원본 좌표로 되돌린다."""
    return OcrResult([
        OcrLine(ln.text, _shift_box(ln.box, pad, scale), [_shift_box(b, pad, scale) for b in ln.words])
        for ln in result.lines
    ])


def angle_from_words(result: OcrResult, min_words: int = 3, max_deg: float = 10.0) -> float:
    """단어 박스 중심들을 직선으로 맞춰 줄의 기울기(도)를 구한다. PIL rotate 에 그대로 넣는 값.

    OCR 이 실제로 글씨라고 본 상자만 쓰므로 대사 상자 테두리 같은 것에 속지 않는다.
    단어가 min_words 미만인 줄(이름 상자 등)은 추정하지 않는다(0).
    Windows OCR 은 회전을 스스로 보정하고 보정된 좌표의 상자를 주므로 항상 0 이 나온다 —
    대신 ±7° 정도는 엔진이 알아서 읽는다. 실제 좌표를 주는 EasyOCR·CLOVA API 에서 동작한다.
    """
    angles, weights = [], []
    for ln in result.lines:
        if len(ln.words) < min_words:
            continue
        xs = np.array([b[0] + b[2] / 2 for b in ln.words], dtype=np.float64)
        ys = np.array([b[1] + b[3] / 2 for b in ln.words], dtype=np.float64)
        span = float(np.ptp(xs))
        if span < 1:
            continue
        slope = np.polyfit(xs, ys, 1)[0]
        angles.append(float(np.degrees(np.arctan(slope))))
        weights.append(span)
    if not angles:
        return 0.0
    angle = float(np.average(angles, weights=weights))
    if abs(angle) < 0.75 or abs(angle) > max_deg:
        return 0.0
    return round(angle, 1)


def text_region(result: OcrResult, img_size: tuple[int, int], margin: float = 0.4) -> Box | None:
    """OCR 이 글씨라고 본 줄들의 합집합 영역 (세로로 margin 만큼 여유). 전단 추정을 이 안에서만 한다."""
    boxes = [ln.box for ln in result.lines if ln.box[2] > 0 and ln.box[3] > 0]
    if not boxes:
        return None
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    h = y1 - y0
    w, hh = img_size
    return (max(0, x0), max(0, int(y0 - h * margin)), min(w, x1) - max(0, x0),
            min(hh, int(y1 + h * margin)) - max(0, int(y0 - h * margin)))


def _letter_ratio(text: str) -> float:
    s = text.replace(" ", "")
    return len(_LETTER.findall(s)) / len(s) if s else 0.0


def pick_consensus(results: list[OcrResult]) -> OcrResult:
    """여러 판독 중 다른 판독들과 가장 비슷한 것(medoid)을 고른다. 비어 있는 판독은 제외.

    동점이면 글자(한글·영문) 비율이 높은 쪽 — 기호·숫자 쓰레기가 섞인 판독을 피한다.
    """
    texts = [" ".join(r.text.split()) for r in results]
    cands = [i for i, t in enumerate(texts) if t]
    if not cands:
        return OcrResult()
    if len(cands) == 1:
        return results[cands[0]]
    best, best_key = cands[0], None
    for i in cands:
        agreement = sum(difflib.SequenceMatcher(None, texts[i], texts[j]).ratio() for j in cands if j != i)
        key = (round(agreement, 3), _letter_ratio(texts[i]))
        if best_key is None or key > best_key:
            best, best_key = i, key
    return results[best]


def pass_plan(scale: float, passes: int) -> list[tuple[str, float]]:
    """passes 개의 (전처리 모드, 배율). 1개면 여백만 추가한 원본 색상.

    조합은 실제 게임 스크린샷(반투명 대사 상자, 보라색 굵은 이름, 타이트/느슨한 영역)으로
    탐색해 고른 것 — 여백 원본 + 그레이 1배 + 그레이 2배가 네 조건 모두에서 정답이었다.
    같은 (모드, 배율) 이 겹치면 다음 후보로 채운다.
    """
    candidates = [("pad", scale), ("gray", 1.0), ("gray", 2.0), ("auto", 1.5), ("auto", 2.0), ("gray", 3.0)]
    plan: list[tuple[str, float]] = []
    for entry in candidates:
        if entry not in plan:
            plan.append(entry)
        if len(plan) >= max(1, passes):
            break
    return plan


class BaseOcr:
    name = "base"
    label = "OCR"
    # 전처리(그레이스케일 반전 등)를 받아도 되는 엔진인지. 색으로 검출하는 엔진은 pad 만 쓴다.
    grayscale_ok = True

    def recognize(self, img: Image.Image, scale: float = 1.0) -> OcrResult:
        raise NotImplementedError

    def recognize_robust(self, img: Image.Image, scale: float = 1.0, passes: int = 3,
                         deskew: bool = True) -> OcrResult:
        """여러 전처리·배율로 읽어 다수결(pick_consensus).

        deskew 면 첫 판독의 단어 상자로 회전각을, 글씨 줄 영역의 투영으로 이탤릭 전단을 추정해
        기울기가 있을 때만 모든 판독을 편 이미지로 다시 한다. 똑바른 글씨는 비용이 거의 없다.
        """
        plan = pass_plan(scale, passes)
        if not self.grayscale_ok:
            plan = [("pad", s) for _, s in plan]
        first_mode, first_scale = plan[0]
        pre, pad = preprocess(img, first_mode, first_scale)
        first = _shift(self.recognize(pre, 1.0), pad, first_scale)

        angle = shear = 0.0
        if deskew and first.lines:
            angle = angle_from_words(first)
            gray = to_dark_text_gray(img)
            if angle:
                gray = gray.rotate(angle, resample=Image.BILINEAR, expand=True, fillcolor=_median_color(gray))
                region = None  # 회전 뒤에는 좌표가 달라져 줄 영역을 다시 잡기 어렵다 → 전체로 추정
            else:
                region = text_region(first, img.size)
            if region:
                x, y, w, h = region
                gray = gray.crop((x, y, x + w, y + h))
            shear = estimate_shear(gray)

        results = [] if (angle or shear) else [first]
        for i, (mode, s) in enumerate(plan):
            if i == 0 and not (angle or shear):
                continue
            pre, pad = preprocess(img, mode, s, angle, shear)
            results.append(_shift(self.recognize(pre, 1.0), pad, s))
        return pick_consensus(results)


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
            words=[(int(i[0] / scale), int(i[1] / scale), int(i[2] / scale), int(i[3] / scale)) for i in line],
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
            words = []
            for word in line.words:
                r = word.bounding_rect
                words.append((int(r.x / scale), int(r.y / scale), int(r.width / scale), int(r.height / scale)))
            box = (0, 0, 0, 0)
            if words:
                x0 = min(w[0] for w in words)
                y0 = min(w[1] for w in words)
                box = (x0, y0, max(w[0] + w[2] for w in words) - x0, max(w[1] + w[3] for w in words) - y0)
            lines.append(OcrLine(text=line.text, box=box, words=words))
        return OcrResult(lines=lines)

    def recognize(self, img: Image.Image, scale: float = 1.0) -> OcrResult:
        """동기 호출 — 파이프라인 스레드에서 사용."""
        return asyncio.run(self.recognize_async(img, scale))


if __name__ == "__main__":
    import sys
    import time

    # 사용법: python src\ocr.py <이미지> [엔진...] — 엔진별 단일 판독 / 다중 판독 비교
    if len(sys.argv) < 2:
        print("지원 언어(Windows):", available_languages())
        sys.exit(0)
    image = Image.open(sys.argv[1])
    names = sys.argv[2:] or ["windows"]
    for n in names:
        eng = create_engine({"engine": n, "lang": "ko"})
        t = time.perf_counter()
        single = eng.recognize(image, 2.0)
        t1 = time.perf_counter()
        robust = eng.recognize_robust(image, 2.0, 3)
        t2 = time.perf_counter()
        print(f"== {eng.label}")
        print(f"  단일 {(t1 - t) * 1000:.0f}ms: {single.text!r}")
        print(f"  다중 {(t2 - t1) * 1000:.0f}ms: {robust.text!r}")
