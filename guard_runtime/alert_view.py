"""Bounded Canvas animation. All code and file activity are fictional text."""
import random
import tkinter as tk

GLYPHS = "0123456789ABCDEF:;<>[]{}/*+="
MAX_COLUMNS = 32


class MatrixRain:
    """Three reusable text items per column, driven by the screen's own clock."""

    def __init__(self, canvas):
        self.canvas = canvas
        self.columns = []
        self.glyph_tick = None

    def resize(self, width, height):
        self.canvas.delete("rain")
        self.height = height
        self.columns = []
        self.glyph_tick = None
        count = min(MAX_COLUMNS, max(6, width // 38))
        rng = random.Random(42)
        for index in range(count):
            x = (index + 0.5) * width / count
            items = [self.canvas.create_text(x, 0, text="", anchor="n", fill=color,
                                            font=("Consolas", -16), tags="rain")
                     for color in ("#083c20", "#14713d", "#64b983")]
            self.columns.append((x, rng.uniform(-height, height), rng.uniform(24, 58), items))
        self.canvas.tag_lower("rain")

    def render(self, elapsed):
        tick = int(elapsed * 2)
        rng = random.Random(tick)
        change_glyphs = tick != self.glyph_tick
        for x, offset, speed, items in self.columns:
            head = (offset + elapsed * speed) % (self.height + 240) - 20
            for item, y in zip(items, (head - 220, head - 60, head)):
                self.canvas.coords(item, x, y)
            if change_glyphs:
                for item, length in zip(items, (8, 3, 1)):
                    self.canvas.itemconfigure(item, text="\n".join(rng.choice(GLYPHS) for _ in range(length)))
        self.glyph_tick = tick


class WarningView:
    """Readable foreground card over optional digital rain; owns no timers."""

    def __init__(self, window, config, width, height, *, standard_message=True):
        self.config = config
        self.standard_message = standard_message
        self.canvas = tk.Canvas(window, bg="#020704", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.rain = MatrixRain(self.canvas) if config.matrix_background else None
        self.background_code = self.canvas.create_text(
            20, 20, anchor="nw", fill="#165331", font=("Consolas", -12),
            text='// ACTIVITY MONITOR\nevent = {"type": "unauthorized_input"}\n'
                 'if event["type"] == "unauthorized_input":\n    alert_owner()')
        self.card = self.canvas.create_rectangle(0, 0, 1, 1, fill="#080c0a", outline="#742428", width=2)
        self.badge = self.canvas.create_text(0, 0, text="SECURITY ALERT  /  LAPTOP GUARD", fill="#ad7478",
                                             font=("Arial", -12, "bold"))
        self.message = self.canvas.create_text(0, 0, text="INTRUSION DETECTED" if standard_message else config.message,
                                               fill="#ff3030", justify="center")
        self.prompt = self.canvas.create_text(0, 0, text="CALL THE OWNER IMMEDIATELY", fill="#efb1b1",
                                              font=("Arial", -15, "bold"))
        self.phone = self.canvas.create_text(0, 0, text=config.phone, fill="#ff3030", justify="center")
        self.action = self.canvas.create_text(0, 0, text="Contact the owner to resolve this alert.",
                                              fill="#c59494", font=("Arial", -14), justify="center")
        self.timer = self.canvas.create_text(0, 0, fill="#ff3030", justify="center")
        self.console = self.canvas.create_text(0, 0, fill="#719781", justify="left")
        self.footer = self.canvas.create_text(0, 0, text="NO FILES ARE MODIFIED",
                                              fill="#74817a", font=("Arial", -11), justify="center")
        if not config.matrix_background:
            self.canvas.itemconfigure(self.background_code, state="hidden")
        if not standard_message:
            for item in (self.prompt, self.phone, self.action):
                self.canvas.itemconfigure(item, state="hidden")
        if not config.show_simulation:
            for item in (self.timer, self.console, self.footer):
                self.canvas.itemconfigure(item, state="hidden")
        self.last_state = None
        self.dimensions = None
        self.resize(width, height)
        self.canvas.bind("<Configure>", lambda event: self.resize(event.width, event.height))

    def resize(self, width, height):
        if width < 2 or height < 2 or self.dimensions == (width, height):
            return
        self.dimensions = (width, height)
        if self.rain:
            self.rain.resize(width, height)
        card_width = min(940, max(100, width - 48))
        card_height = min(560, max(160, height - 64))
        cx, cy = width / 2, height / 2
        top = cy - card_height / 2
        self.canvas.coords(self.card, cx - card_width / 2, top, cx + card_width / 2, top + card_height)
        self.canvas.coords(self.badge, cx, top + 28)
        message_y = top + card_height * (0.36 if self.config.show_simulation else 0.52)
        if self.standard_message:
            message_y = top + card_height * 0.22
        self.canvas.coords(self.message, cx, message_y)
        size = max(12, min(32, int(card_width / 26), int(card_height / 18)))
        self.canvas.itemconfigure(self.message, width=card_width - 40, font=("Arial", -size, "bold"))
        self.canvas.coords(self.prompt, cx, top + card_height * 0.34)
        self.canvas.itemconfigure(self.prompt, width=card_width - 40)
        self.canvas.coords(self.phone, cx, top + card_height * 0.44)
        phone_size = max(14, min(52, int(card_width / (max(8, len(self.config.phone)) * 0.7)), int(card_height / 9)))
        self.canvas.itemconfigure(self.phone, width=card_width - 40, font=("Arial", -phone_size, "bold"))
        self.canvas.coords(self.action, cx, top + card_height * 0.54)
        self.canvas.itemconfigure(self.action, width=card_width - 40)
        self.canvas.coords(self.timer, cx, top + card_height * 0.64)
        self.canvas.itemconfigure(self.timer, width=card_width - 40,
                                  font=("Consolas", -max(16, min(44, int(card_width / 14))), "bold"))
        self.canvas.coords(self.console, cx, top + card_height * 0.81)
        self.canvas.itemconfigure(self.console, width=card_width - 40,
                                  font=("Consolas", -max(10, min(13, int(card_width / 44)))))
        self.canvas.coords(self.footer, cx, top + card_height - 20)
        self.canvas.itemconfigure(self.footer, width=card_width - 30)

    def render(self, elapsed, state):
        if self.rain:
            self.rain.render(elapsed)
        if state != self.last_state:
            self.canvas.itemconfigure(self.message, fill=state.color)
            self.canvas.itemconfigure(self.phone, fill=state.color)
            self.canvas.itemconfigure(self.timer, fill=state.color,
                                      text=state.countdown.split(" — ")[0])
            self.canvas.itemconfigure(self.console, text=state.console)
            self.last_state = state
