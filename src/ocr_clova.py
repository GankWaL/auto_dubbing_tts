"""네이버 클라우드 CLOVA OCR API 엔진 (General OCR, 유료).

네이버 클라우드 플랫폼 → CLOVA OCR → 도메인 생성 → API Gateway 연동 후
.env 에 CLOVA_OCR_URL(Invoke URL), CLOVA_OCR_SECRET(Secret Key) 을 넣는다.
호출당 과금되므로 대사가 바뀔 때만 호출된다 (dubbing.py 의 변화 감지).
"""

import base64
import io
import json
import os
import time
import urllib.request
import uuid

from PIL import Image

from ocr import BaseOcr, OcrResult, group_lines, prepare_image


class ClovaApiOcr(BaseOcr):
    name = "clova_api"
    label = "CLOVA OCR API (네이버 클라우드)"

    def __init__(self, lang: str = "ko", url: str | None = None, secret: str | None = None):
        self.url = url or os.getenv("CLOVA_OCR_URL", "").strip()
        self.secret = secret or os.getenv("CLOVA_OCR_SECRET", "").strip()
        self.lang = lang
        if not self.url or not self.secret:
            raise RuntimeError(
                ".env 에 CLOVA_OCR_URL 과 CLOVA_OCR_SECRET 을 설정해주세요 "
                "(네이버 클라우드 플랫폼 → CLOVA OCR → 도메인 → API Gateway 연동)."
            )

    def recognize(self, img: Image.Image, scale: float = 1.0) -> OcrResult:
        img = prepare_image(img, scale)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG")
        payload = {
            "version": "V2",
            "requestId": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000),
            "lang": self.lang,
            "images": [{"format": "png", "name": "frame", "data": base64.b64encode(buf.getvalue()).decode()}],
        }
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-OCR-SECRET": self.secret},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
        image = data["images"][0]
        if image.get("inferResult") == "ERROR":
            raise RuntimeError(f"CLOVA OCR 오류: {image.get('message', '')}")
        items = []
        for field in image.get("fields", []):
            verts = field["boundingPoly"]["vertices"]
            xs = [v["x"] for v in verts]
            ys = [v["y"] for v in verts]
            items.append((min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys), field["inferText"]))
        return OcrResult(group_lines(items, scale))
