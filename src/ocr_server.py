"""EasyOCR(CLOVA CRAFT) 로컬 추론 서버.

torch·easyocr 은 무거워 exe 에 넣지 않고, 별도 가상환경(ocr_env)에서 이 서버를 돌린다.
앱(ocr_easyocr.py)은 같은 프로세스에 easyocr 이 없으면 이 서버에 HTTP 로 요청한다.

사전 준비: bat\\setup_easyocr.bat (최초 1회)
실행:      앱이 OCR 엔진을 EasyOCR 로 두면 자동으로 띄운다. 수동: bat\\start_ocr_server.bat

API:
    GET  /health               → {"status": "ok", "label": "CLOVA CRAFT + EasyOCR (GPU)"}
    POST /recognize?scale=2.0  PNG 바이트 → {"lines": [{"text": "...", "box": [x, y, w, h]}]}
"""

import io
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image  # noqa: E402

HOST = "127.0.0.1"
PORT = int(os.getenv("EASYOCR_PORT", "51771"))

engine = None
lock = threading.Lock()  # GPU 추론은 한 번에 하나씩


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path == "/health":
            self._send_json({"status": "ok", "label": engine.label})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        url = urlparse(self.path)
        if url.path != "/recognize":
            self._send_json({"error": "not found"}, 404)
            return
        try:
            scale = float(parse_qs(url.query).get("scale", ["1.0"])[0])
            length = int(self.headers.get("Content-Length", "0"))
            img = Image.open(io.BytesIO(self.rfile.read(length)))
            with lock:
                result = engine.recognize(img, scale)
            self._send_json({"lines": [{"text": ln.text, "box": list(ln.box)} for ln in result.lines]})
        except Exception as e:  # 요청 하나의 실패가 서버를 죽이지 않게
            self._send_json({"error": str(e)}, 500)

    def log_message(self, fmt, *args):
        pass  # 요청마다 로그를 남기지 않는다


def main() -> None:
    global engine
    from ocr_easyocr import EasyOcrLocal

    lang = sys.argv[1] if len(sys.argv) > 1 else "ko"
    print(f"[ocr_server] 모델 로딩 ({lang})...", flush=True)
    engine = EasyOcrLocal(lang)
    print(f"[ocr_server] {engine.label} 준비 완료 — http://{HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
