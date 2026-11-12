"""The persistent full-screen recorder: the script stays pinned on top, only the status area changes.

`LiveUI` has the same interface `studio.Session` already drives (overview, segment, focus, review,
record_wait, note, key, choose, confirm, complete), so the state machine is unchanged. It draws with
rich's Live on the alternate screen, which means nothing is ever pushed into scrollback. We refresh
by hand (no background thread) only when something changed: a tick of the timer, a keypress that
scrolls, or a terminal resize. Keys are read from one cbreak session held for the whole run, so a
refresh can never swallow or delay a keypress.
"""
import io
import os
import select
import shutil
import sys
import termios
import tty

from rich.console import Console
from rich.live import Live
from rich.text import Text

import cli_ui
import studio
import studio_screen as screen

TICK = 0.1
ESCAPES = {b"[A": -1, b"[B": 1, b"[5~": -10, b"[6~": 10}  # up, down, page up, page down


class LiveUI:
    def __init__(self, out=None):
        self.out = out or sys.stdout
        self.plain = studio.TerminalUI(self.out)  # used before/after the full-screen view
        self.console = Console(file=self.out, force_terminal=True)
        self.state = None            # ScreenState of the segment on screen
        self.view = None             # a non-script renderable (overview, list, confirm), or None
        self._early = []             # notes raised before the first screen exists
        self._live = None
        self._termios = None
        self._closed = False
        self._size = None

    @property
    def fd(self):
        return sys.stdin.fileno()

    # --- lifecycle ---
    def _term_size(self):
        try:
            cols, rows = os.get_terminal_size(self.out.fileno())
        except (OSError, ValueError, AttributeError):
            cols, rows = shutil.get_terminal_size((80, 24))
        return max(cols, 20), max(rows, 8)

    def _start(self):
        if self._live is not None or self._closed:
            return
        self._termios = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd, termios.TCSANOW)  # NOW: a key typed early is kept
        self.console.size = self._size = self._term_size()
        self._live = Live(get_renderable=self._render, console=self.console, screen=True,
                          auto_refresh=False, redirect_stdout=False, redirect_stderr=False)
        self._live.start(refresh=False)
        if self._early and self.state:
            self.state.notes += self._early
            self._early = []

    def close(self):
        """Leave the full-screen view and restore the terminal. Safe to call twice."""
        if self._live is not None:
            try:
                self.view = Text("")  # rich redraws once more on stop; make that last frame empty
                self._live.stop()
            finally:
                self._live = None
                if self._termios is not None:
                    termios.tcsetattr(self.fd, termios.TCSADRAIN, self._termios)
        self._closed = True
        for kind, text in self._early:  # raised but never shown on a screen
            self.plain.note(text, kind)
        self._early = []

    def _render(self):
        self.console.size = self._size = self._term_size()
        width, height = self._size
        if self.view is not None:
            return self.view
        return screen.build(self.state, width, height)

    def _refresh(self):
        self._start()
        if self._live is not None:
            self._live.refresh()

    def _capture(self, fn, *args):
        """Run a TerminalUI printer and keep its text, so the list screens reuse the existing layout."""
        buf = io.StringIO()
        ui = studio.TerminalUI(buf)
        fn(ui, *args)
        return Text(buf.getvalue().rstrip("\n"), no_wrap=True, overflow="crop")

    # --- script-bearing screens ---
    def _new_state(self, seg, total):
        ascii_only = "utf" not in (getattr(self.out, "encoding", "") or "").lower()
        return screen.ScreenState(segment=seg, total=total, ascii_only=ascii_only)

    def focus(self, info):
        """Pin this segment's script. Offset and notes reset only when the segment actually changes."""
        seg = info["segment"]
        if self.state is None or self.state.segment.id != seg.id or self.state.total != info["total"]:
            old = self.state.notes if self.state else []
            self.state = self._new_state(seg, info["total"])
            self.state.notes = old
        self.view = None

    def segment(self, info):
        self.state = None
        self.focus(info)
        self.state.mode, self.state.take, self.state.notes = "ready", None, []
        if info["status"] == "approved":
            self.state.notes.append(("info", "Already approved. Approving a new take replaces it; "
                                             "the old audio is archived."))
        self._refresh()

    def review(self, info):
        self.focus(info)
        take = info["take"]
        self.state.mode = "review"
        self.state.take = {"name": take.name, "position": info["position"], "count": info["count"],
                           "duration": info["duration"], "problems": info["problems"],
                           "can_approve": info["can_approve"], "is_approved": info["is_approved"]}
        self._refresh()

    def record_wait(self, capture, info=None):
        if info:
            self.focus(info)
        self.state.mode, self.state.take, self.state.notes = "recording", None, []
        while True:
            self.state.elapsed = capture.elapsed
            self._refresh()
            kind, value = self._next_input(TICK)
            if kind == "key" and value == "enter":
                return

    def note(self, text, kind="info"):
        if self._closed:
            self.plain.note(text, kind)
        elif self.state is None:
            self._early.append((kind, text))
        else:
            self.state.notes = (self.state.notes + [(kind, text)])[-screen.MAX_NOTES:]
            if self._live is not None:
                self._refresh()

    # --- list and prompt screens (no script) ---
    def overview(self, info):
        self.state = None
        self.view = self._capture(studio.TerminalUI.overview, info)
        self._refresh()

    def choose(self, info):
        typed = ""
        base = self._capture(studio.TerminalUI.status, info)
        rows = [f"  {n:>2}. {studio.TerminalUI._row(None, seg, status, pending).strip()}"
                for n, (seg, status, pending) in enumerate(info["rows"], 1)]
        while True:
            self.view = Text("\n".join(rows + ["", f"  Segment number (blank to go back): {typed}"]),
                             no_wrap=True, overflow="crop")
            self._refresh()
            kind, value = self._next_input(None)
            if kind != "key":
                continue
            if value == "enter":
                break
            if value in ("\x7f", "\b"):
                typed = typed[:-1]
            elif value.isdigit():
                typed += value
        del base
        if not typed:
            return None
        picked = [seg for seg, _, _ in info["rows"]]
        if 1 <= int(typed) <= len(picked):
            return picked[int(typed) - 1].id
        self.note(f"{typed!r} is not one of the numbers above.", "warn")
        return None

    def confirm(self, question):
        self.view = Text(f"\n  {question} [y/N]", no_wrap=False)
        self._refresh()
        answer = self.key("y n enter") == "y"
        self.view = None
        return answer

    def complete(self, info):
        self.close()
        self.plain.complete(info)

    # --- input ---
    def _read_byte(self, timeout):
        if select.select([self.fd], [], [], timeout)[0]:
            return os.read(self.fd, 1)
        return None

    def _next_input(self, timeout):
        """('key', name) | ('scroll', None) | ('tick', None). Handles resize and script scrolling itself."""
        raw = self._read_byte(TICK if timeout is None else timeout)
        if raw is None:
            if self._size != self._term_size():
                self._refresh()
            return "tick", None
        if raw == b"":
            raise EOFError
        if raw == b"\x04":
            raise EOFError
        if raw == b"\x1b":
            seq = b""
            while len(seq) < 4 and (more := self._read_byte(0.02)):
                seq += more
                if more.isalpha() or more == b"~":
                    break
            if seq in ESCAPES and self.view is None and self.state is not None:
                self._scroll(ESCAPES[seq])
                return "scroll", None
            return "tick", None
        if raw in (b"\n", b"\r"):
            return "key", "enter"
        return "key", raw.decode(errors="ignore").lower()

    def _scroll(self, delta):
        width, height = self._size
        _, _, _, _, rows = screen.layout(self.state, width, height)
        step = delta if abs(delta) == 1 else (rows - 1) * (1 if delta > 0 else -1)
        self.state.script_offset = max(self.state.script_offset + step, 0)
        _, offset, *_ = screen.layout(self.state, width, height)
        self.state.script_offset = offset
        self._refresh()

    def key(self, allowed=""):
        self._refresh() if self._live is not None else None
        names = set(allowed.split())
        while True:
            kind, value = self._next_input(None)
            if kind == "key" and (not names or value in names):
                return value

    def flush_input(self):
        termios.tcflush(self.fd, termios.TCIFLUSH)
