"""The recording screen as a pure function of state: script pinned on top, status and controls below.

No terminal I/O here. `LiveUI` (studio.py) owns the terminal and calls `build()` to get a rich
renderable sized to the current terminal, so tests can render any state at any size.
"""
import textwrap
from dataclasses import dataclass, field

from rich.box import ASCII, ROUNDED
from rich.console import Group
from rich.panel import Panel
from rich.text import Text

PURPLE, CYAN, GREEN, RED, YELLOW = "#bd93f9", "#8be9fd", "#50fa7b", "#ff5555", "#f1fa8c"
MIN_SCRIPT_ROWS = 3
MAX_NOTES = 2


@dataclass
class ScreenState:
    segment: object
    total: int
    mode: str = "ready"            # ready | recording | review
    elapsed: float = 0.0
    take: dict = None              # review: name, position, count, duration, problems, can_approve, is_approved
    notes: list = field(default_factory=list)   # [(kind, text)]
    script_offset: int = 0
    ascii_only: bool = False


def fmt_time(seconds):
    return f"{int(seconds // 60):02}:{seconds % 60:04.1f}"


def script_lines(text, width):
    """The narration wrapped to `width`, blank lines kept, words never altered."""
    out = []
    for line in text.splitlines():
        if line.strip():
            out.extend(textwrap.wrap(line, max(width, 1), break_long_words=True, break_on_hyphens=False))
        else:
            out.append("")
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()
    return out


def _wrap(line, width):
    return textwrap.wrap(line, max(width, 1), break_long_words=True, break_on_hyphens=False) or [""]


def _controls(state):
    if state.mode == "recording":
        return [("Enter", "Stop recording")]
    if state.mode == "review":
        t = state.take
        first = "Approve and continue" if t["can_approve"] else "Record again (this take is unusable)"
        keys = [("Enter", first), ("p", "Play"), ("r", "Record again")]
        if t["position"] > 1:
            keys.append(("b", "Earlier take"))
        if t["position"] < t["count"]:
            keys.append(("n", "Later take"))
        return keys + [("q", "Save and quit")]
    return [("Enter", "Start recording"), ("s", "Skip for now"), ("q", "Save and quit")]


def _status(state):
    """[(text, style)] lines before wrapping."""
    if state.mode == "recording":
        dot = "*" if state.ascii_only else "●"
        return [(f"{dot} RECORDING  {fmt_time(state.elapsed)}", f"bold {RED}")]
    if state.mode == "review":
        t = state.take
        which = t["name"].split(".")[-2] if t["name"].count(".") >= 2 else t["name"]
        tail = "  [approved]" if t["is_approved"] else ""
        lines = [("TAKE RECORDED", f"bold {CYAN}"), (f"Take {t['position']} of {t['count']} ({which}){tail}", ""),
                 (f"Length: {t['duration']:.1f} seconds", "")]
        return lines + [(f"! {p}", YELLOW) for p in t["problems"]]
    return [("Ready to record", f"bold {GREEN}")]


def _bottom(state, inner, scrollable):
    rows = []
    for text, style in _status(state):
        rows += [(w, style) for w in _wrap(text, inner)]
    for kind, text in state.notes[-MAX_NOTES:]:
        style = {"ok": GREEN, "warn": YELLOW, "error": RED}.get(kind, CYAN)
        rows += [(w, style) for w in _wrap(text, inner)]
    rows.append(("", ""))
    controls = _controls(state)
    if scrollable:
        controls = controls + [("^/v" if state.ascii_only else "↑/↓", "Scroll script")]
    pieces = [f"[{k}] {label}" for k, label in controls]
    # pack whole controls per row; a control is never split across rows (unless wider than the screen)
    line = ""
    for piece in pieces:
        if line and len(line) + 3 + len(piece) > inner:
            rows.append((line, ""))
            line = ""
        line = f"{line}   {piece}" if line else piece
    if line:
        rows += [(w, "") for w in _wrap(line, inner)]
    return rows


def layout(state, width, height):
    """(window_lines, offset, total_lines, bottom_rows, rows_for_script)."""
    inner = max(width - 4, 1)
    lines = script_lines(state.segment.text, inner)
    for scrollable in (False, True):
        bottom = _bottom(state, inner, scrollable)
        rows = max(height - (len(bottom) + 2) - 2, MIN_SCRIPT_ROWS)
        if len(lines) <= rows:
            break
    offset = min(max(state.script_offset, 0), max(len(lines) - rows, 0))
    return lines[offset:offset + rows], offset, len(lines), bottom, rows


def build(state, width, height):
    """A rich renderable that is at most `height` rows tall and exactly `width` columns wide."""
    box = ASCII if state.ascii_only else ROUNDED
    window, offset, total_lines, bottom, rows = layout(state, width, height)
    seg = state.segment
    title = f"SEGMENT {seg.index:02} / {state.total:02} - {seg.title.upper()}"
    body = Text(no_wrap=True, overflow="crop")
    for i, line in enumerate(window):
        body.append(line + ("\n" if i < len(window) - 1 else ""))
    scrollable = total_lines > rows
    arrows = "^/v" if state.ascii_only else "↑/↓"
    hint = f"{arrows} scroll - lines {offset + 1}-{offset + len(window)} of {total_lines}" if scrollable else None
    script = Panel(body, title=title, title_align="left", subtitle=hint, subtitle_align="right",
                   border_style=PURPLE, box=box, width=width)
    status = Text(no_wrap=True, overflow="crop")
    for i, (line, style) in enumerate(bottom):
        status.append(line + ("\n" if i < len(bottom) - 1 else ""), style=style or None)
    panel_status = Panel(status, border_style=RED if state.mode == "recording" else CYAN, box=box, width=width)
    return Group(script, panel_status)
