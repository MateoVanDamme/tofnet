"""tofnet live dashboard (tkinter frontend).

Shows the latest distance for up to NUM_NODES nodes (tofnet-1 .. tofnet-N) in a
row of cards that update in real time.

This does NOT talk to BLE itself. It launches the existing ``receiver.py`` as a
child process and parses its stdout, so the background script stays untouched
and remains the only thing connected to the nodes (a BLE peripheral accepts
just one central connection at a time). Lines it understands:

    [22:05:08.773] tofnet-2: 1790 mm

Run:  python dashboard.py
Quit: close the window (the child receiver is terminated automatically).
"""
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import scrolledtext

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
try:
    import pygame              # audio backend: play / pause / resume / stop
except ImportError:
    pygame = None

NUM_NODES = 4
RECEIVER = "receiver.py"
STALE_AFTER_S = 12.0          # firmware notifies every 5 s; >12 s = something's off
POLL_MS = 300                 # how often the GUI redraws
LOG_MAX_LINES = 500           # trim the live log so it can't grow unbounded

# Each node is a story character: (marker letter, character name). The dashboard
# builds a sound name by concatenating <marker><zone> per node, e.g. P1Q3K2M4 —
# the zone (distance band) encodes how important that character is.
MARKERS = {
    1: ("P", "Prince"),
    2: ("Q", "Queen"),
    3: ("K", "King"),
    4: ("M", "Mobat"),   # the priest
}


def marker_letter(node_id: int) -> str:
    return MARKERS.get(node_id, ("?", "?"))[0]


def character_name(node_id: int) -> str:
    return MARKERS.get(node_id, ("?", "?"))[1]


# Distance is bucketed into 4 zones (1 = closest .. 4 = farthest); the sound name
# uses the zone digit, e.g. P1Q3K2M4. 4 zones ^ 4 nodes = 256 possible sounds.
# EDIT these metre boundaries to taste. A 0 / "no valid sensor reading" is
# treated as the farthest zone (4).
ZONE_EDGES_M = (2.0, 4.0, 6.0)   # <2 m -> 1, 2-4 -> 2, 4-6 -> 3, >=6 m -> 4
NUM_ZONES = len(ZONE_EDGES_M) + 1


def distance_to_zone(mm: int) -> int:
    if mm <= 0:
        return NUM_ZONES            # no valid reading -> farthest / least important
    metres = mm / 1000
    for zone, edge in enumerate(ZONE_EDGES_M, start=1):
        if metres < edge:
            return zone
    return NUM_ZONES

SOUND_DIR = "sounds"          # plays sounds/<code>.<ext>, e.g. sounds/P1Q3K2M4.wav
SOUND_EXTS = (".wav", ".ogg", ".mp3")   # pygame tries these in order

HERE = os.path.dirname(os.path.abspath(__file__))


def find_sound(code: str) -> "str | None":
    for ext in SOUND_EXTS:
        path = os.path.join(HERE, SOUND_DIR, code + ext)
        if os.path.exists(path):
            return path
    return None
MEASURE_RE = re.compile(r"(tofnet-\d+):\s*(\d+)\s*mm")

# Colors
BG = "#1e1e1e"
CARD_BG = "#2a2a2a"
FG = "#e0e0e0"
MUTED = "#888888"
LIVE = "#4caf50"
STALE = "#ff9800"
OFFLINE = "#555555"
NOECHO = "#c0392b"


class NodeCard:
    def __init__(self, parent, node_id: int):
        self.node_id = node_id
        self.last_mm: int | None = None
        self.last_seen: float | None = None

        self.frame = tk.Frame(parent, bg=CARD_BG, bd=2, relief="ridge",
                              highlightthickness=3, highlightbackground=OFFLINE)
        self.frame.pack(side="left", expand=True, fill="both", padx=8, pady=8)

        self.title = tk.Label(self.frame, text=character_name(node_id),
                             bg=CARD_BG, fg=FG, font=("Segoe UI", 17, "bold"))
        self.title.pack(pady=(14, 0))

        self.subtitle = tk.Label(
            self.frame, text=f"tofnet-{node_id} · {marker_letter(node_id)}",
            bg=CARD_BG, fg=MUTED, font=("Segoe UI", 14))
        self.subtitle.pack(pady=(0, 2))

        self.value = tk.Label(self.frame, text="—", bg=CARD_BG, fg=MUTED,
                             font=("Consolas", 40, "bold"))
        self.value.pack(expand=True)

        self.unit = tk.Label(self.frame, text="mm", bg=CARD_BG, fg=MUTED,
                            font=("Segoe UI", 14))
        self.unit.pack()

        self.status = tk.Label(self.frame, text="waiting…", bg=CARD_BG, fg=MUTED,
                              font=("Segoe UI", 14))
        self.status.pack(pady=(2, 6))

        # Per-node zone control: "Auto" follows the sensor; "1".."N" pins this
        # node to a fixed zone. Independent per card — no global mode.
        zrow = tk.Frame(self.frame, bg=CARD_BG)
        zrow.pack(pady=(0, 12))
        tk.Label(zrow, text="zone", bg=CARD_BG, fg=MUTED,
                font=("Segoe UI", 14)).pack(side="left", padx=(0, 6))
        self.zone_var = tk.StringVar(value="Auto")
        choices = ["Auto"] + [str(z) for z in range(1, NUM_ZONES + 1)]
        self.zone_menu = tk.OptionMenu(zrow, self.zone_var, *choices)
        self.zone_menu.configure(font=("Consolas", 14), width=5, bg=CARD_BG,
                                fg=FG, activebackground=OFFLINE,
                                highlightthickness=0)
        self.zone_menu["menu"].configure(font=("Consolas", 14), bg=CARD_BG, fg=FG)
        self.zone_menu.pack(side="left")
        self.eff_label = tk.Label(zrow, text="→ —", bg=CARD_BG, fg=MUTED,
                                 font=("Consolas", 14))
        self.eff_label.pack(side="left", padx=(8, 0))

    def zone(self) -> int:
        """Effective zone: the dropdown pick, or the live sensor zone in Auto."""
        sel = self.zone_var.get()
        if sel == "Auto":
            return distance_to_zone(self.last_mm or 0)
        return int(sel)

    def update_value(self, mm: int) -> None:
        self.last_mm = mm
        self.last_seen = time.monotonic()

    def refresh(self) -> None:
        if self.last_seen is None:
            self._set(OFFLINE, MUTED, "—", "waiting…", MUTED)
            return
        age = time.monotonic() - self.last_seen
        if self.last_mm == 0:
            # firmware returns 0 mm on a TF-Luna read failure or no return pulse
            self._set(NOECHO, NOECHO, "0", "no valid sensor reading", NOECHO)
        elif age <= STALE_AFTER_S:
            self._set(LIVE, FG, str(self.last_mm), f"live · {age:.0f}s ago", LIVE)
        else:
            self._set(STALE, FG, str(self.last_mm),
                     f"stale · {age:.0f}s ago", STALE)

    def _set(self, border, val_fg, val, status_text, status_fg) -> None:
        self.frame.configure(highlightbackground=border)
        self.value.configure(text=val, fg=val_fg)
        self.status.configure(text=status_text, fg=status_fg)


def reader_thread(proc: subprocess.Popen, q: "queue.Queue") -> None:
    """Pump receiver.py stdout into the queue. Runs off the GUI thread."""
    for line in proc.stdout:
        q.put(line.rstrip("\n"))


class Dashboard:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.q: "queue.Queue" = queue.Queue()
        self.play_state = "stopped"     # stopped | playing
        self.current_code = None
        self.mixer_ok = False
        root.title("tofnet — live distances")
        root.configure(bg=BG)
        root.geometry("1100x620")

        header = tk.Label(root, text="tofnet live measurements", bg=BG, fg=FG,
                         font=("Segoe UI", 18, "bold"))
        header.pack(pady=(12, 0))

        row = tk.Frame(root, bg=BG)
        row.pack(fill="both", padx=10, pady=10)

        self.cards = {i: NodeCard(row, i) for i in range(1, NUM_NODES + 1)}

        # Live code (left) + audio transport (right).
        bottom = tk.Frame(root, bg=BG)
        bottom.pack(fill="x", padx=20, pady=(0, 10))

        self.code_var = tk.StringVar(value="—")
        self.code_label = tk.Label(bottom, textvariable=self.code_var, bg=BG,
                                   fg="#ffd54f", font=("Consolas", 30, "bold"))
        self.code_label.pack(side="left")

        # One button: toggles Play <-> Stop for the current code.
        self.play_btn = tk.Button(bottom, text="▶ Play", command=self.on_toggle,
                                 font=("Segoe UI", 16, "bold"), fg="white",
                                 bg=LIVE, activebackground="#43a047",
                                 relief="flat", padx=28, pady=10, cursor="hand2")
        self.play_btn.pack(side="right")

        self.audio_var = tk.StringVar(value="idle")
        tk.Label(bottom, textvariable=self.audio_var, bg=BG, fg=MUTED,
                font=("Segoe UI", 14)).pack(side="right", padx=(0, 16))

        # Live log: the receiver's stdout, streamed in.
        self.log = scrolledtext.ScrolledText(
            root, height=8, bg="#141414", fg="#b0b0b0", insertbackground=FG,
            font=("Consolas", 14), relief="flat", borderwidth=0, state="disabled")
        self.log.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        # Launch the untouched background receiver and stream its stdout.
        self.proc = subprocess.Popen(
            [sys.executable, "-u", RECEIVER],
            cwd=HERE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=reader_thread, args=(self.proc, self.q),
                        daemon=True).start()

        self.init_audio()
        self.update_transport()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.tick()

    def init_audio(self) -> None:
        if pygame is None:
            self.append_log(["  >> audio OFF: pygame not installed "
                            "(pip install pygame)"])
            return
        try:
            pygame.mixer.init()
            self.mixer_ok = True
        except Exception as e:
            self.append_log([f"  >> audio OFF: mixer init failed ({e})"])

    def tick(self) -> None:
        # Drain everything the receiver printed since last tick.
        lines = []
        try:
            while True:
                line = self.q.get_nowait()
                lines.append(line)
                m = MEASURE_RE.search(line)
                if m:
                    node_id = int(m.group(1).split("-")[1])
                    if node_id in self.cards:
                        self.cards[node_id].update_value(int(m.group(2)))
        except queue.Empty:
            pass
        if lines:
            self.append_log(lines)
        any_override = False
        for card in self.cards.values():
            card.refresh()
            overridden = card.zone_var.get() != "Auto"
            any_override = any_override or overridden
            card.eff_label.configure(text=f"→ zone {card.zone()}",
                                    fg="#ff7043" if overridden else MUTED)
        self.code_var.set(self.build_code())   # code is always live
        # Code turns orange if ANY node is overridden, so it's never silently off-auto.
        self.code_label.configure(fg="#ff7043" if any_override else "#ffd54f")
        # Reset the transport when a track finishes on its own.
        if (self.play_state == "playing" and self.mixer_ok
                and not pygame.mixer.music.get_busy()):
            self.play_state = "stopped"
            self.update_transport()
        self.root.after(POLL_MS, self.tick)

    def append_log(self, lines: list) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", "\n".join(lines) + "\n")
        # Trim to the last LOG_MAX_LINES so the widget can't grow unbounded.
        excess = int(self.log.index("end-1c").split(".")[0]) - LOG_MAX_LINES
        if excess > 0:
            self.log.delete("1.0", f"{excess + 1}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def build_code(self) -> str:
        """Concatenate <marker><zone> for every node (4 zones -> 256 sounds).

        Each node's zone is its dropdown pick, or its live sensor zone when the
        dropdown is on Auto.
        """
        parts = []
        for i in range(1, NUM_NODES + 1):
            parts.append(f"{marker_letter(i)}{self.cards[i].zone()}")
        return "".join(parts)

    def on_toggle(self) -> None:
        """One button: play the current code, or stop if it's already playing."""
        if self.play_state == "playing":
            self._stop()
        else:
            self._play()

    def _play(self) -> None:
        code = self.build_code()
        path = find_sound(code)
        if path is None:
            self.append_log([f"  >> Play {code}: no sound file in {SOUND_DIR}/"])
            self.audio_var.set(f"{code}: no file")
            return
        if not self.mixer_ok:
            self.append_log(["  >> Play ignored: audio is OFF"])
            return
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
        except Exception as e:
            self.append_log([f"  >> play error: {e}"])
            return
        self.current_code = code
        self.play_state = "playing"
        self.append_log([f"  >> Play {code}  ({os.path.basename(path)})"])
        self.update_transport()

    def _stop(self) -> None:
        if self.mixer_ok:
            pygame.mixer.music.stop()
        self.play_state = "stopped"
        self.append_log(["  >> Stop"])
        self.update_transport()

    def update_transport(self) -> None:
        if not self.mixer_ok:
            self.play_btn.configure(text="▶ Play", state="disabled")
            self.audio_var.set("audio OFF")
            return
        playing = self.play_state == "playing"
        self.play_btn.configure(
            text="■ Stop" if playing else "▶ Play",
            bg="#b0392b" if playing else LIVE,
            activebackground="#922d22" if playing else "#43a047",
            state="normal")
        self.audio_var.set(f"▶ playing {self.current_code}" if playing else "idle")

    def on_close(self) -> None:
        if self.mixer_ok:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.quit()
            except Exception:
                pass
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    Dashboard(root)
    root.mainloop()
