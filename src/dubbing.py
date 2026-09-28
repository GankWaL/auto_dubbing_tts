"""자동 더빙 파이프라인.

watcher 스레드: 대사 영역 캡처 → 변화 감지 → 화면이 안정되면 OCR(대사·이름) → 화자 매핑 → 합성 큐
synth 스레드:   tts.synthesize() 로 오디오 파일 생성 → 재생 큐
player 스레드:  PC 스피커 재생 (player.Player) — 디스코드가 아니라 이 프로그램이 직접 출력한다
"""

import asyncio
import queue
import threading
import time

import config
import tts
from capture import ScreenGrabber, changed, fingerprint
from ocr import create_engine
from player import Player
from speakers import SpeakerBook, clean_dialogue

# OCR 텍스트가 계속 바뀌어(움직이는 배경 위 글자 등) 안정되지 않을 때 이 시간이 지나면 그냥 읽는다
MAX_UNSTABLE_SEC = 2.0


class Dubber:
    def __init__(self, settings: dict, log=print, on_speaker_added=None, on_line=None):
        self.settings = settings
        self.log = log
        self.on_speaker_added = on_speaker_added  # callback(name)
        self.on_line = on_line  # callback(name, text)
        self.book = SpeakerBook(settings)
        self.player: Player | None = None
        self._threads: list[threading.Thread] = []
        self._running = threading.Event()
        self._synth_q: queue.Queue = queue.Queue()
        self.last_text = ""

    @property
    def running(self) -> bool:
        return self._running.is_set()

    # ---------- 수명 ----------
    def start(self) -> None:
        if self.running:
            return
        regions = self.settings["regions"]
        if not regions.get("dialogue"):
            raise RuntimeError("대사 영역이 설정되지 않았습니다.")
        pb = self.settings["playback"]
        self.player = Player(
            device=pb.get("device"),
            policy=pb.get("policy", "latest"),
            volume=float(pb.get("volume", 1.0)),
            log=self.log,
        )
        self._running.set()
        self.last_text = ""
        self._threads = [
            self.player,
            threading.Thread(target=self._synth_loop, daemon=True, name="synth"),
            threading.Thread(target=self._watch_loop, daemon=True, name="watcher"),
        ]
        for t in self._threads:
            t.start()
        self.log("더빙 시작")

    def stop(self) -> None:
        if not self.running:
            return
        self._running.clear()
        self._clear_synth_queue()
        if self.player:
            self.player.stop()
        for t in self._threads:
            if t is not threading.current_thread():
                t.join(timeout=3)
        self._threads = []
        self.log("더빙 정지")

    # ---------- watcher ----------
    def _watch_loop(self) -> None:
        cap = self.settings["capture"]
        interval = cap["interval_ms"] / 1000
        stable_needed = int(cap["stable_frames"])
        threshold = float(cap["change_threshold"])
        ocr_cfg = self.settings["ocr"]
        scale = float(ocr_cfg["scale"])
        try:
            grabber = ScreenGrabber()
            engine = create_engine(ocr_cfg)
            self.log(f"OCR 엔진: {engine.label}")
        except Exception as e:
            self.log(f"[초기화 오류] {e}")
            self._running.clear()
            return
        prev_fp = None
        pending = ""  # 마지막으로 OCR 한 대사 (아직 읽지 않음)
        pending_since = 0.0
        stable = 0
        try:
            while self.running:
                t0 = time.perf_counter()
                dialogue_region = tuple(self.settings["regions"]["dialogue"])
                name_region = self.settings["regions"].get("name")
                img = grabber.grab(dialogue_region)
                fp = fingerprint(img)
                if changed(prev_fp, fp, threshold):
                    # 화면이 바뀐 프레임만 OCR — 글자가 실제로 바뀌었는지는 텍스트로 판단한다.
                    # 깜빡이는 화살표처럼 글자와 무관한 변화는 텍스트가 같으므로 안정으로 친다.
                    try:
                        text = clean_dialogue(engine.recognize(img, scale).text)
                    except Exception as e:
                        self.log(f"[OCR 오류] {e}")
                        prev_fp = fp
                        continue
                    if text != pending:
                        pending, stable = text, 0
                        pending_since = time.perf_counter()
                    else:
                        stable += 1
                else:
                    stable += 1
                prev_fp = fp

                ready = stable >= stable_needed or (time.perf_counter() - pending_since) > MAX_UNSTABLE_SEC
                if pending and pending != self.last_text and ready:
                    name_text = ""
                    if name_region:
                        try:
                            name_text = engine.recognize(grabber.grab(tuple(name_region)), scale).text
                        except Exception as e:
                            self.log(f"[OCR 오류] 이름: {e}")
                    self._handle_text(name_text, pending)
                time.sleep(max(0.0, interval - (time.perf_counter() - t0)))
        finally:
            grabber.close()

    def _handle_text(self, name_text: str, text: str) -> None:
        if not text or text == self.last_text:
            return
        speak = text
        # 타자 효과 중간에 한 번 읽었다면 이어지는 부분만 읽는다
        if self.last_text and text.startswith(self.last_text):
            speak = text[len(self.last_text):].strip()
        self.last_text = text
        if not speak:
            return
        name, is_new = self.book.resolve(name_text)
        if is_new:
            self.log(f"[새 화자] '{name}' → 기본 목소리({self.settings['default_voice']})로 등록")
            config.save(self.settings)
            if self.on_speaker_added:
                self.on_speaker_added(name)
        voice = self.book.voice_for(name)
        if self.on_line:
            self.on_line(name, speak)
        self.log(f"[{name or '해설'}] {speak}")
        if self.settings["playback"].get("policy") == "latest":
            self._clear_synth_queue()
        self._synth_q.put((name, speak, voice))

    def _clear_synth_queue(self) -> None:
        while True:
            try:
                self._synth_q.get_nowait()
            except queue.Empty:
                return

    # ---------- synth ----------
    def _synth_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            while self.running:
                try:
                    name, text, voice = self._synth_q.get(timeout=0.2)
                except queue.Empty:
                    continue
                try:
                    t0 = time.perf_counter()
                    path = loop.run_until_complete(
                        tts.synthesize(text, voice["voice"], voice["speed"], voice["emotion"])
                    )
                    self.log(f"  합성 {voice['voice']} {(time.perf_counter() - t0) * 1000:.0f}ms")
                except Exception as e:
                    self.log(f"[합성 오류] {voice['voice']}: {e}")
                    continue
                if self.running and self.player:
                    self.player.enqueue(path, label=name or "해설")
        finally:
            loop.close()


def synthesize_preview(voice: dict, text: str = "안녕하세요. 이 목소리로 대사를 읽습니다.") -> str:
    """GUI 미리듣기용 — 오디오 파일 경로 반환."""
    return asyncio.run(tts.synthesize(text, voice["voice"], voice["speed"], voice["emotion"]))
