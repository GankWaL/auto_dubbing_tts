"""컨트롤 패널 GUI (tkinter).

영역 선택, 시작/정지, 화자↔목소리 매핑표, 옵션, 로그.
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from dotenv import load_dotenv

import config
import ocr
import tts
from app_version import VERSION
from dubbing import Dubber, synthesize_preview
from player import Player, output_devices
from region_select import select_region

POLICIES = {"latest": "최신 대사만 (끊고 읽기)", "queue": "순서대로 모두 읽기"}
DEFAULT_DEVICE = "기본 장치"
ENV_FILE = os.path.join(config.BASE_DIR, ".env")
# .env 설정 창 항목: (키, 라벨, 비밀값 여부)
ENV_FIELDS = [
    ("TYPECAST_API_KEY", "Typecast API 키 (감정 목소리, 유료)", True),
    ("GOOGLE_TTS_API_KEY", "Google Cloud TTS API 키", True),
    ("MY_VOICE_ROOT", "커스텀 목소리 폴더 (my_voice 가 있는 곳)", False),
    ("CLOVA_OCR_URL", "CLOVA OCR API Invoke URL", False),
    ("CLOVA_OCR_SECRET", "CLOVA OCR API Secret Key", True),
]


def read_env() -> dict:
    values = {}
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    values[k.strip()] = v.strip()
    except OSError:
        pass
    return values


def write_env(new_values: dict) -> None:
    """기존 .env 의 주석·순서는 지키고 값만 바꾼다. 없던 키는 끝에 붙인다."""
    lines = []
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        pass
    remaining = dict(new_values)
    for i, line in enumerate(lines):
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in remaining:
                lines[i] = f"{k}={remaining.pop(k)}"
    lines += [f"{k}={v}" for k, v in remaining.items()]
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    load_dotenv(ENV_FILE, override=True)


class EnvDialog(tk.Toplevel):
    """API 키·경로 설정 (.env)."""

    def __init__(self, parent, on_saved=None):
        super().__init__(parent)
        self.title("설정 (.env)")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.on_saved = on_saved
        current = read_env()
        frame = ttk.Frame(self, padding=12)
        frame.pack()
        self.entries = {}
        for row, (key, label, secret) in enumerate(ENV_FIELDS):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=3, padx=(0, 8))
            entry = ttk.Entry(frame, width=48, show="•" if secret else "")
            entry.insert(0, current.get(key, ""))
            entry.grid(row=row, column=1, pady=3)
            self.entries[key] = entry
        ttk.Label(
            frame,
            text="※ 모두 선택 항목입니다. 비워두면 해당 엔진 목소리·OCR 이 목록에서 빠집니다.\n"
            "※ 저장하면 바로 적용됩니다 (더빙 중이면 정지 후 다시 시작).",
            foreground="#888", font=("맑은 고딕", 8), justify="left",
        ).grid(row=len(ENV_FIELDS), column=0, columnspan=2, sticky="w", pady=(10, 8))
        btns = ttk.Frame(frame)
        btns.grid(row=len(ENV_FIELDS) + 1, column=0, columnspan=2, sticky="e")
        ttk.Button(btns, text="저장", command=self._save).pack(side="right", padx=2)
        ttk.Button(btns, text="취소", command=self.destroy).pack(side="right", padx=2)

    def _save(self) -> None:
        try:
            write_env({k: e.get().strip() for k, e in self.entries.items()})
        except OSError as e:
            messagebox.showerror("설정", f".env 저장 실패: {e}", parent=self)
            return
        if self.on_saved:
            self.on_saved()
        self.destroy()


class SpeakerEditor(tk.Toplevel):
    """화자 한 명의 목소리·속도·감정 편집."""

    def __init__(self, parent, name: str, cfg: dict, voices: list[str], on_save):
        super().__init__(parent)
        self.title(f"화자 설정 — {name}")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        frame = ttk.Frame(self, padding=12)
        frame.pack()
        ttk.Label(frame, text="목소리").grid(row=0, column=0, sticky="w", pady=3)
        self.voice = ttk.Combobox(frame, values=voices, state="readonly", width=24)
        self.voice.set(cfg.get("voice") if cfg.get("voice") in voices else voices[0])
        self.voice.grid(row=0, column=1, pady=3)
        ttk.Label(frame, text="속도").grid(row=1, column=0, sticky="w", pady=3)
        self.speed = ttk.Spinbox(
            frame, from_=tts.MIN_SPEED, to=tts.MAX_SPEED, increment=0.1, width=8, format="%.1f"
        )
        self.speed.set(f"{float(cfg.get('speed', 1.0)):.1f}")
        self.speed.grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(frame, text="감정 (Typecast 전용)").grid(row=2, column=0, sticky="w", pady=3)
        self.emotion = ttk.Combobox(frame, values=list(tts.TYPECAST_EMOTIONS), state="readonly", width=12)
        self.emotion.set(cfg.get("emotion", tts.DEFAULT_EMOTION))
        self.emotion.grid(row=2, column=1, sticky="w", pady=3)
        btns = ttk.Frame(frame)
        btns.grid(row=3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="미리듣기", command=lambda: preview_voice(self.value(), self)).pack(side="left", padx=2)
        ttk.Button(btns, text="저장", command=lambda: (on_save(self.value()), self.destroy())).pack(side="left", padx=2)
        ttk.Button(btns, text="취소", command=self.destroy).pack(side="left", padx=2)

    def value(self) -> dict:
        try:
            speed = max(tts.MIN_SPEED, min(tts.MAX_SPEED, float(self.speed.get())))
        except ValueError:
            speed = 1.0
        return {"voice": self.voice.get(), "speed": speed, "emotion": self.emotion.get()}


def preview_voice(voice: dict, parent) -> None:
    """목소리 샘플을 합성해 스피커로 한 번 재생한다."""

    def work():
        try:
            path = synthesize_preview(voice)
        except Exception as e:
            parent.after(0, lambda: messagebox.showerror("미리듣기", str(e), parent=parent))
            return
        player = Player(policy="queue")
        player.start()
        player.enqueue(path)  # 재생이 끝나면 Player 가 파일을 지운다

    threading.Thread(target=work, daemon=True).start()


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(f"자동 더빙 TTS v{VERSION}")
        root.minsize(780, 680)
        try:
            root.iconbitmap(os.path.join(config.BASE_DIR, "icon", "icon.ico"))
        except tk.TclError:
            pass
        self.settings = config.load()
        self.log_q: queue.Queue = queue.Queue()
        self._installing = False  # EasyOCR 환경 설치 진행 중
        self.dubber = Dubber(self.settings, log=self.log, on_speaker_added=self._on_speaker_added)
        self.voices = list(tts.available_voices())

        outer = ttk.Frame(root, padding=10)
        outer.pack(fill="both", expand=True)

        # --- 상단: 상태·시작/정지 ---
        top = ttk.Frame(outer)
        top.pack(fill="x")
        self.status = ttk.Label(top, text="● 정지", foreground="#888", font=("맑은 고딕", 11, "bold"))
        self.status.pack(side="left")
        self.stop_btn = ttk.Button(top, text="정지", command=self.stop, state="disabled")
        self.stop_btn.pack(side="right", padx=2)
        self.start_btn = ttk.Button(top, text="시작", command=self.start)
        self.start_btn.pack(side="right", padx=2)
        ttk.Button(top, text="설정 (.env)", command=lambda: EnvDialog(root, self._reload_voices)).pack(
            side="right", padx=(2, 16)
        )

        # --- 영역 ---
        reg = ttk.LabelFrame(outer, text="화면 영역", padding=8)
        reg.pack(fill="x", pady=(8, 0))
        self.region_labels = {}
        for row, (key, title) in enumerate([("dialogue", "대사 영역 (필수)"), ("name", "이름 영역 (선택)")]):
            ttk.Label(reg, text=title, width=16).grid(row=row, column=0, sticky="w")
            lbl = ttk.Label(reg, text="", foreground="#555", width=30)
            lbl.grid(row=row, column=1, sticky="w")
            self.region_labels[key] = lbl
            ttk.Button(reg, text="선택", command=lambda k=key: self.pick_region(k)).grid(row=row, column=2, padx=2)
            ttk.Button(reg, text="지우기", command=lambda k=key: self.clear_region(k)).grid(row=row, column=3, padx=2)
        ttk.Button(reg, text="OCR 테스트 (지금 화면 읽기)", command=self.test_ocr).grid(
            row=0, column=4, rowspan=2, padx=(16, 0)
        )
        self._refresh_regions()

        # --- 옵션 ---
        opt = ttk.LabelFrame(outer, text="옵션", padding=8)
        opt.pack(fill="x", pady=(8, 0))
        # 미등록 화자·해설 목소리: 목소리·속도·감정을 SpeakerEditor 로 편집한다
        self.voice_labels = {}
        for col, (key, title) in enumerate([("default_speaker", "미등록 화자 목소리"), ("narrator", "해설(이름 없음) 목소리")]):
            ttk.Label(opt, text=title).grid(row=0, column=col * 2, sticky="w")
            cell = ttk.Frame(opt)
            cell.grid(row=0, column=col * 2 + 1, sticky="w", padx=(4, 16))
            lbl = ttk.Label(cell, text="", width=20)
            lbl.pack(side="left")
            ttk.Button(cell, text="설정", width=5, command=lambda k=key, t=title: self.edit_voice_preset(k, t)).pack(side="left")
            self.voice_labels[key] = lbl
        self._refresh_voice_presets()

        ttk.Label(opt, text="재생 정책").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.policy = ttk.Combobox(opt, values=list(POLICIES.values()), state="readonly", width=22)
        self.policy.set(POLICIES.get(self.settings["playback"]["policy"], POLICIES["latest"]))
        self.policy.grid(row=1, column=1, sticky="w", padx=(4, 16), pady=(6, 0))
        ttk.Label(opt, text="출력 장치").grid(row=1, column=2, sticky="w", pady=(6, 0))
        self.devices = output_devices()
        self.device = ttk.Combobox(
            opt, values=[DEFAULT_DEVICE] + [f"{i}: {n}" for i, n in self.devices], state="readonly", width=34
        )
        cur = self.settings["playback"].get("device")
        self.device.set(next((f"{i}: {n}" for i, n in self.devices if i == cur), DEFAULT_DEVICE))
        self.device.grid(row=1, column=3, sticky="w", padx=4, pady=(6, 0))

        ttk.Label(opt, text="OCR 엔진").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.engine = ttk.Combobox(opt, values=list(ocr.ENGINES.values()), state="readonly", width=34)
        self.engine.set(ocr.ENGINES.get(self.settings["ocr"].get("engine", "windows"), ocr.ENGINES["windows"]))
        self.engine.grid(row=2, column=1, columnspan=3, sticky="w", padx=4, pady=(6, 0))

        ttk.Label(opt, text="OCR 확대 배율").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.scale = ttk.Spinbox(opt, from_=1.0, to=4.0, increment=0.5, width=6, format="%.1f")
        self.scale.set(f"{float(self.settings['ocr']['scale']):.1f}")
        self.scale.grid(row=3, column=1, sticky="w", padx=4, pady=(6, 0))
        ttk.Label(opt, text="안정 프레임 수").grid(row=3, column=2, sticky="w", pady=(6, 0))
        self.stable = ttk.Spinbox(opt, from_=1, to=20, width=6)
        self.stable.set(int(self.settings["capture"]["stable_frames"]))
        self.stable.grid(row=3, column=3, sticky="w", padx=4, pady=(6, 0))

        ttk.Label(opt, text="판독 횟수 (다수결)").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.passes = ttk.Spinbox(opt, from_=1, to=4, width=6)
        self.passes.set(int(self.settings["ocr"].get("passes", 3)))
        self.passes.grid(row=4, column=1, sticky="w", padx=4, pady=(6, 0))
        self.deskew_var = tk.BooleanVar(value=bool(self.settings["ocr"].get("deskew", True)))
        ttk.Checkbutton(opt, text="기울기 보정 (회전·이탤릭)", variable=self.deskew_var,
                        command=self.apply_options).grid(row=4, column=2, columnspan=2, sticky="w", pady=(6, 0))
        for w in (self.policy, self.device, self.engine):
            w.bind("<<ComboboxSelected>>", lambda e: self.apply_options())
        for w in (self.scale, self.stable, self.passes):
            w.bind("<FocusOut>", lambda e: self.apply_options())
            w.bind("<Return>", lambda e: self.apply_options())

        # --- 화자 표 ---
        spk = ttk.LabelFrame(outer, text="화자 → 목소리 (더블클릭으로 편집, 새 화자는 자동 추가)", padding=8)
        spk.pack(fill="both", expand=True, pady=(8, 0))
        cols = ("name", "voice", "speed", "emotion")
        self.tree = ttk.Treeview(spk, columns=cols, show="headings", height=7)
        for c, title, w in zip(cols, ("화자", "목소리", "속도", "감정"), (200, 200, 60, 80)):
            self.tree.heading(c, text=title)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(spk, orient="vertical", command=self.tree.yview)
        sb.pack(side="left", fill="y")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Double-1>", lambda e: self.edit_speaker())
        side = ttk.Frame(spk)
        side.pack(side="left", fill="y", padx=(8, 0))
        ttk.Button(side, text="추가", command=self.add_speaker).pack(fill="x", pady=1)
        ttk.Button(side, text="편집", command=self.edit_speaker).pack(fill="x", pady=1)
        ttk.Button(side, text="삭제", command=self.delete_speaker).pack(fill="x", pady=1)
        ttk.Button(side, text="미리듣기", command=self.preview_speaker).pack(fill="x", pady=(8, 1))
        self._refresh_speakers()

        # --- 로그 ---
        logf = ttk.LabelFrame(outer, text="로그", padding=4)
        logf.pack(fill="both", expand=True, pady=(8, 0))
        self.log_text = tk.Text(logf, height=8, state="disabled", font=("맑은 고딕", 9), wrap="word")
        self.log_text.pack(fill="both", expand=True)

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self._poll_log)
        self.log(f"사용 가능한 목소리 {len(self.voices)}개 (Edge 3 + API 키 설정 시 Typecast/Google + 커스텀)")

    # ---------- 로그·상태 ----------
    def log(self, msg: str) -> None:
        self.log_q.put(msg)

    def _poll_log(self) -> None:
        try:
            while True:
                msg = self.log_q.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", msg + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        if self.dubber.running:
            self.status.configure(text="● 더빙 중", foreground="#2e7d32")
        elif not self._installing:
            self.status.configure(text="● 정지", foreground="#888")
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
        self.root.after(150, self._poll_log)

    def _reload_voices(self) -> None:
        """.env 저장 후 목소리 목록을 다시 읽는다. 사라진 목소리는 기본 목소리로 되돌린다."""
        self.voices = list(tts.available_voices())
        for key in ("default_speaker", "narrator"):
            if self.settings[key]["voice"] not in self.voices:
                self.settings[key]["voice"] = tts.DEFAULT_VOICE
        self._refresh_voice_presets()
        self.apply_options()
        self.log(f"설정 저장됨 — 사용 가능한 목소리 {len(self.voices)}개")

    # ---------- 미등록 화자·해설 목소리 ----------
    @staticmethod
    def _voice_summary(cfg: dict) -> str:
        return f"{cfg['voice']} · {float(cfg.get('speed', 1.0)):.1f}배 · {cfg.get('emotion', '기본')}"

    def _refresh_voice_presets(self) -> None:
        for key, lbl in self.voice_labels.items():
            lbl.configure(text=self._voice_summary(self.settings[key]))

    def edit_voice_preset(self, key: str, title: str) -> None:
        def save(cfg):
            self.settings[key] = cfg
            config.save(self.settings)
            self._refresh_voice_presets()

        SpeakerEditor(self.root, title, self.settings[key], self.voices, save)

    # ---------- EasyOCR 환경 ----------
    def _easyocr_needs_install(self) -> bool:
        """엔진이 EasyOCR 인데 같은 프로세스에도, ocr_env 에도, 떠 있는 서버에도 없으면 True."""
        if self.settings["ocr"].get("engine") != "easyocr":
            return False
        try:
            import easyocr  # noqa: F401
            import torch  # noqa: F401
            return False
        except ImportError:
            pass
        import ocr_easyocr

        return not os.path.isfile(ocr_easyocr.OCR_ENV_PYTHON) and ocr_easyocr.server_health() is None

    def _offer_easyocr_install(self, then) -> None:
        """설치를 제안하고, 수락하면 백그라운드로 설치한 뒤 then() 을 이어서 실행한다."""
        import ocr_setup

        gpu = ocr_setup.has_nvidia_gpu()
        size = "약 2.5GB (CUDA)" if gpu else "약 200MB (CPU 빌드, NVIDIA GPU 없음)"
        if not messagebox.askyesno(
            "EasyOCR 설치",
            "CLOVA CRAFT + EasyOCR 엔진 환경(ocr_env)이 없습니다.\n\n"
            f"지금 설치할까요? 다운로드 {size}, 수 분 걸립니다.\n"
            "시스템에 Python 3.10 이상이 있어야 합니다. 진행 상황은 로그에 표시됩니다.",
            parent=self.root,
        ):
            return
        self.start_btn.configure(state="disabled")
        self.status.configure(text="● EasyOCR 설치 중", foreground="#e65100")
        self._installing = True

        def work():
            try:
                ok = ocr_setup.install_ocr_env(self.log)
            except Exception as e:
                self.log(f"[EasyOCR 설치] 오류: {e}")
                ok = False
            finally:
                self._installing = False

            def done():
                self.start_btn.configure(state="normal")
                if ok:
                    then()
                else:
                    messagebox.showerror(
                        "EasyOCR 설치", "설치에 실패했습니다. 로그를 확인해주세요.\n"
                        "Python 이 없다면 터미널에서: winget install Python.Python.3.11",
                        parent=self.root,
                    )

            self.root.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    # ---------- 시작/정지 ----------
    def start(self) -> None:
        self.apply_options()
        if self._easyocr_needs_install():
            self._offer_easyocr_install(self.start)
            return
        try:
            self.dubber.start()
        except Exception as e:
            messagebox.showerror("시작 실패", str(e), parent=self.root)
            return
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

    def stop(self) -> None:
        threading.Thread(target=self.dubber.stop, daemon=True).start()

    def on_close(self) -> None:
        self.apply_options()
        self.dubber.stop()
        self.root.destroy()

    # ---------- 영역 ----------
    def pick_region(self, key: str) -> None:
        hint = (
            "대사 박스를 드래그해서 감싸주세요 (Esc 취소)"
            if key == "dialogue"
            else "화자 이름 박스를 드래그해서 감싸주세요 (Esc 취소)"
        )
        self.root.withdraw()
        try:
            region = select_region(self.root, hint)
        finally:
            self.root.deiconify()
        if region:
            self.settings["regions"][key] = list(region)
            config.save(self.settings)
            self._refresh_regions()

    def clear_region(self, key: str) -> None:
        self.settings["regions"][key] = None
        config.save(self.settings)
        self._refresh_regions()

    def _refresh_regions(self) -> None:
        for key, lbl in self.region_labels.items():
            r = self.settings["regions"].get(key)
            lbl.configure(text=f"x={r[0]} y={r[1]} {r[2]}×{r[3]}" if r else "미설정")

    def test_ocr(self) -> None:
        regions = self.settings["regions"]
        if not regions.get("dialogue"):
            messagebox.showinfo("OCR 테스트", "대사 영역을 먼저 선택해주세요.", parent=self.root)
            return
        self.apply_options()
        if self._easyocr_needs_install():
            self._offer_easyocr_install(self.test_ocr)
            return

        def work():
            import time

            from capture import ScreenGrabber
            from speakers import clean_dialogue, clean_name

            try:
                grabber = ScreenGrabber()
                cfg = self.settings["ocr"]
                engine = ocr.create_engine(cfg)
                scale, passes, deskew = float(cfg["scale"]), int(cfg.get("passes", 3)), bool(cfg.get("deskew", True))
                t0 = time.perf_counter()
                text = clean_dialogue(
                    engine.recognize_robust(grabber.grab(tuple(regions["dialogue"])), scale, passes, deskew).text
                )
                name = ""
                if regions.get("name"):
                    name = clean_name(
                        engine.recognize_robust(grabber.grab(tuple(regions["name"])), scale, passes, deskew).text
                    )
                elapsed = (time.perf_counter() - t0) * 1000
                grabber.close()
                self.log(f"[OCR 테스트 · {engine.label} · {elapsed:.0f}ms] 이름='{name}' 대사='{text}'")
            except Exception as e:
                self.log(f"[OCR 테스트 오류] {e}")

        threading.Thread(target=work, daemon=True).start()

    # ---------- 옵션 ----------
    def apply_options(self) -> None:
        s = self.settings
        s["playback"]["policy"] = next((k for k, v in POLICIES.items() if v == self.policy.get()), "latest")
        dev = self.device.get()
        s["playback"]["device"] = int(dev.split(":")[0]) if dev and dev != DEFAULT_DEVICE else None
        s["ocr"]["engine"] = next((k for k, v in ocr.ENGINES.items() if v == self.engine.get()), "windows")
        s["ocr"]["deskew"] = bool(self.deskew_var.get())
        try:
            s["ocr"]["scale"] = max(1.0, min(4.0, float(self.scale.get())))
            s["capture"]["stable_frames"] = max(1, int(self.stable.get()))
            s["ocr"]["passes"] = max(1, min(4, int(self.passes.get())))
        except ValueError:
            pass
        config.save(s)

    # ---------- 화자 ----------
    def _refresh_speakers(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for name, cfg in self.settings["speakers"].items():
            self.tree.insert(
                "", "end", iid=name,
                values=(name, cfg["voice"], f"{float(cfg.get('speed', 1.0)):.1f}", cfg.get("emotion", "기본")),
            )

    def _on_speaker_added(self, name: str) -> None:
        self.root.after(0, self._refresh_speakers)

    def _selected_speaker(self) -> str | None:
        sel = self.tree.selection()
        return sel[0] if sel else None

    def add_speaker(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("화자 추가")
        win.transient(self.root)
        win.grab_set()
        f = ttk.Frame(win, padding=12)
        f.pack()
        ttk.Label(f, text="화자 이름 (화면에 표시되는 이름)").pack(anchor="w")
        entry = ttk.Entry(f, width=30)
        entry.pack(pady=4)
        entry.focus_set()

        def ok(*_):
            name = entry.get().strip()
            if not name:
                return
            self.settings["speakers"].setdefault(name, dict(self.settings["default_speaker"]))
            config.save(self.settings)
            self._refresh_speakers()
            win.destroy()
            self.tree.selection_set(name)
            self.edit_speaker()

        entry.bind("<Return>", ok)
        ttk.Button(f, text="확인", command=ok).pack(anchor="e")

    def edit_speaker(self) -> None:
        name = self._selected_speaker()
        if not name:
            return

        def save(cfg):
            self.settings["speakers"][name] = cfg
            config.save(self.settings)
            self._refresh_speakers()

        SpeakerEditor(self.root, name, self.settings["speakers"][name], self.voices, save)

    def delete_speaker(self) -> None:
        name = self._selected_speaker()
        if name and messagebox.askyesno("삭제", f"'{name}' 화자를 삭제할까요?", parent=self.root):
            self.settings["speakers"].pop(name, None)
            config.save(self.settings)
            self._refresh_speakers()

    def preview_speaker(self) -> None:
        name = self._selected_speaker()
        if name:
            preview_voice(self.settings["speakers"][name], self.root)


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()
