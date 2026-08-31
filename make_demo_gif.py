"""
make_demo_gif.py - renders the guard's warning screen and records it as
demo.gif for the README (no webcam, alarm, or input blocking involved).

Run from the laptop-guard folder:  python make_demo_gif.py
Requires Pillow. The capture grabs the primary monitor while a tkinter
window replays the real warning message with a typewriter effect.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import tkinter as tk

from PIL import ImageGrab

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from laptop_guard import MESSAGE_TEMPLATE  # noqa: E402

FPS = 6
HOLD_FRAMES = FPS * 2          # hold the full message for 2 s at the end
CHARS_PER_FRAME = 4
OUT_WIDTH = 960                # gif width in pixels (keeps file size sane)
OUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo.gif")

MESSAGE = MESSAGE_TEMPLATE.format(phone="555-1234567")

frames: list = []
done_typing = threading.Event()
stop_capture = threading.Event()


def capture_loop() -> None:
    """Grabs the screen at FPS until told to stop."""
    while not stop_capture.is_set():
        start = time.time()
        frames.append(ImageGrab.grab())
        elapsed = time.time() - start
        time.sleep(max(0.0, 1.0 / FPS - elapsed))


def main() -> None:
    capturer = threading.Thread(target=capture_loop, daemon=True)
    capturer.start()
    time.sleep(0.6)  # let the capture warm up before the window appears

    root = tk.Tk()
    root.title("System Alert")
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.configure(bg="black")

    label = tk.Label(
        root, text="", fg="red", bg="black",
        font=("Arial", 22, "bold"), wraplength=900, justify="center",
    )
    label.pack(expand=True)

    state = {"shown": 0, "hold": 0}

    def tick() -> None:
        if state["shown"] < len(MESSAGE):
            state["shown"] += CHARS_PER_FRAME
            label.config(text=MESSAGE[: state["shown"]])
            root.after(int(1000 / FPS), tick)
        elif state["hold"] < HOLD_FRAMES:
            state["hold"] += 1
            root.after(int(1000 / FPS), tick)
        else:
            done_typing.set()
            root.destroy()

    root.after(300, tick)  # brief black beat before typing starts
    root.mainloop()

    stop_capture.set()
    capturer.join(timeout=2)

    # trim leading frames captured before the window was on top
    frames[:] = frames[2:]

    first = frames[0]
    ratio = OUT_WIDTH / first.width
    size = (OUT_WIDTH, int(first.height * ratio))
    resized = [
        f.resize(size).convert("P", palette=Image.ADAPTIVE, colors=64)
        for f in frames
    ]
    resized[0].save(
        OUT_FILE, save_all=True, append_images=resized[1:],
        duration=int(1000 / FPS), loop=0, optimize=True,
    )
    print(f"saved {OUT_FILE} ({len(resized)} frames)")


if __name__ == "__main__":
    from PIL import Image  # deferred; only needed when saving
    main()
