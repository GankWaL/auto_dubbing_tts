"""테스트용 가짜 비주얼노벨 창.

이름 박스 + 대사 박스를 그리고, 타자 효과로 대사를 순환 표시한다.
게임 없이 파이프라인을 확인할 때 쓴다. 창이 뜨면 대사/이름 영역 좌표를 stdout 에 JSON 으로 출력한다.

    .venv\Scripts\python tests\fake_vn.py [--interval 6] [--pos +100+100]
"""

import argparse
import json
import sys
import tkinter as tk

SCRIPT = [
    ("유이", "오늘은 날씨가 정말 좋네요. 같이 산책할까요?"),
    ("민준", "좋아. 근데 그 전에 편의점 좀 들렀다 가자."),
    ("", "두 사람은 나란히 언덕길을 내려갔다."),
    ("유이", "아, 맞다. 어제 말한 책 가져왔어?"),
    ("민준", "……깜빡했다. 내일 꼭 가져올게."),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=6.0, help="대사 전환 간격(초)")
    ap.add_argument("--pos", default="+120+120", help="창 위치 (+x+y)")
    ap.add_argument("--typing-ms", type=int, default=40, help="글자당 타자 지연(ms)")
    args = ap.parse_args()

    root = tk.Tk()
    root.title("fake VN")
    root.geometry(f"900x260{args.pos}")
    root.configure(bg="#1b1b2f")
    root.attributes("-topmost", True)
    name_lbl = tk.Label(root, text="", font=("맑은 고딕", 20, "bold"), fg="#ffdc78", bg="#2b2b4f", anchor="w", padx=12)
    name_lbl.place(x=30, y=25, width=260, height=44)
    dlg_lbl = tk.Label(root, text="", font=("맑은 고딕", 22), fg="white", bg="#22223b", anchor="nw", justify="left",
                       padx=16, pady=12, wraplength=800)
    dlg_lbl.place(x=30, y=85, width=840, height=150)
    arrow = tk.Label(root, text="▼", font=("맑은 고딕", 14), fg="#aaa", bg="#22223b")
    arrow.place(x=830, y=200)

    state = {"i": 0, "pos": 0}

    def blink():
        arrow.configure(fg="#aaa" if arrow.cget("fg") == "#22223b" else "#22223b")
        root.after(500, blink)

    def type_step(text: str):
        state["pos"] += 1
        dlg_lbl.configure(text=text[: state["pos"]])
        if state["pos"] < len(text):
            root.after(args.typing_ms, type_step, text)

    def next_line():
        name, text = SCRIPT[state["i"] % len(SCRIPT)]
        name_lbl.configure(text=name)
        state["pos"] = 0
        type_step(text)
        state["i"] += 1
        root.after(int(args.interval * 1000), next_line)

    def report():
        root.update_idletasks()
        rx, ry = root.winfo_rootx(), root.winfo_rooty()
        regions = {
            "name": [rx + 30, ry + 25, 260, 44],
            "dialogue": [rx + 30, ry + 85, 840, 150],
        }
        print(json.dumps(regions), flush=True)

    root.after(300, report)
    root.after(500, next_line)
    blink()
    root.mainloop()


if __name__ == "__main__":
    main()
