"""화면 위에 드래그해서 영역(x, y, w, h)을 고르는 반투명 오버레이."""

import tkinter as tk

from capture import virtual_screen


def select_region(parent: tk.Tk, hint: str = "드래그해서 영역을 선택하세요 (Esc 취소)") -> tuple | None:
    left, top, width, height = virtual_screen()
    result: dict = {"region": None}

    win = tk.Toplevel(parent)
    win.overrideredirect(True)
    win.geometry(f"{width}x{height}+{left}+{top}")
    win.attributes("-alpha", 0.35)
    win.attributes("-topmost", True)
    win.configure(bg="black", cursor="crosshair")
    canvas = tk.Canvas(win, bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    canvas.create_text(width // 2, 60, text=hint, fill="white", font=("맑은 고딕", 20))
    state = {"x0": 0, "y0": 0, "rect": None}

    def on_press(e):
        state["x0"], state["y0"] = e.x, e.y
        state["rect"] = canvas.create_rectangle(
            e.x, e.y, e.x, e.y, outline="#4fc3f7", width=3, fill="#4fc3f7"
        )

    def on_drag(e):
        if state["rect"] is not None:
            canvas.coords(state["rect"], state["x0"], state["y0"], e.x, e.y)

    def on_release(e):
        x0, y0 = min(state["x0"], e.x), min(state["y0"], e.y)
        x1, y1 = max(state["x0"], e.x), max(state["y0"], e.y)
        if x1 - x0 >= 8 and y1 - y0 >= 8:
            result["region"] = (left + x0, top + y0, x1 - x0, y1 - y0)
        win.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    win.bind("<Escape>", lambda e: win.destroy())
    win.focus_force()
    canvas.focus_set()
    parent.wait_window(win)
    return result["region"]
