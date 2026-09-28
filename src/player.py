"""로컬 스피커 재생 큐 (sounddevice).

policy="queue": 들어온 순서대로 모두 재생.
policy="latest": 새 항목이 오면 대기 중인 것을 버리고 재생 중인 것도 끊는다 — 대사 전환이 빠른 콘텐츠용.
"""

import os
import queue
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf


class Player(threading.Thread):
    def __init__(self, device=None, policy: str = "latest", volume: float = 1.0, log=print):
        super().__init__(daemon=True, name="player")
        self.device = device
        self.policy = policy
        self.volume = volume
        self.log = log
        self.q: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._interrupt = threading.Event()
        self.on_state = None  # callback(speaking: bool, label: str)

    def enqueue(self, path: str, label: str = "") -> None:
        if self.policy == "latest":
            self.clear()
            self._interrupt.set()
        self.q.put((path, label))

    def clear(self) -> None:
        while True:
            try:
                path, _ = self.q.get_nowait()
            except queue.Empty:
                return
            _remove(path)

    def stop(self) -> None:
        self._stop_event.set()
        self._interrupt.set()
        self.clear()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                path, label = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            self._interrupt.clear()
            try:
                self._play(path, label)
            except Exception as e:  # 재생 실패는 로그만 남기고 다음 항목으로
                self.log(f"[재생 오류] {e}")
            finally:
                _remove(path)

    def _play(self, path: str, label: str) -> None:
        data, sr = sf.read(path, dtype="float32", always_2d=True)
        if self.volume != 1.0:
            data = np.clip(data * self.volume, -1.0, 1.0)
        if self.on_state:
            self.on_state(True, label)
        sd.play(data, sr, device=self.device)
        try:
            while sd.get_stream().active:
                if self._interrupt.is_set() or self._stop_event.is_set():
                    sd.stop()
                    break
                time.sleep(0.03)
        finally:
            if self.on_state:
                self.on_state(False, label)


def output_devices() -> list[tuple[int, str]]:
    """(index, name) 목록 — GUI 출력 장치 선택용."""
    devices = []
    default_api = sd.query_hostapis(sd.default.hostapi)
    for i in default_api["devices"]:
        d = sd.query_devices(i)
        if d["max_output_channels"] > 0:
            devices.append((i, d["name"]))
    return devices


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
