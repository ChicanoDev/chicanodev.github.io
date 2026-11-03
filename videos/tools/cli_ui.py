"""Tiny terminal UI helpers: Dracula colours, boxed panels, width-safe wrapping.

Standard library only, so help and the recorder work without installing anything.
Colour is off when NO_COLOR is set, TERM is dumb, or output is not a terminal. Box drawing
falls back to ASCII on dumb terminals.
"""
import os
import shutil
import sys
import textwrap

PURPLE, CYAN, GREEN, RED, YELLOW, MUTED = "189;147;249", "139;233;253", "80;250;123", "255;85;85", "241;250;140", "98;114;164"
MAX_WIDTH, MIN_WIDTH = 72, 30


def is_dumb():
    return os.environ.get("TERM", "") == "dumb"


def color_enabled(stream=None):
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR") or is_dumb():
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def paint(text, rgb, bold=False, stream=None):
    if not color_enabled(stream):
        return text
    return f"\x1b[{'1;' if bold else ''}38;2;{rgb}m{text}\x1b[0m"


def width():
    """Usable line width: the terminal's, clamped so panels stay readable."""
    try:
        cols = int(os.environ.get("COLUMNS", "") or shutil.get_terminal_size((80, 24)).columns)
    except ValueError:
        cols = 80
    return max(MIN_WIDTH, min(cols - 2, MAX_WIDTH))


def _box():
    return ("+", "+", "+", "+", "-", "|") if is_dumb() else ("╭", "╮", "╰", "╯", "─", "│")


def wrap(text, w, indent=""):
    return textwrap.wrap(text, w, initial_indent=indent, subsequent_indent=indent,
                         break_long_words=True, break_on_hyphens=False) or [indent.rstrip()]


def panel(lines, title="", w=None, rgb=PURPLE, center=False):
    """A boxed block. `lines` are plain strings; long ones are wrapped to fit."""
    w = w or width()
    tl, tr, bl, br, h, v = _box()
    inner = w - 4
    body = []
    for line in lines:
        body.extend(wrap(line, inner) if line.strip() else [""])
    top = f"{h} {title} " if title else ""
    top = top[:inner + 2]
    out = [paint(tl + top + h * (w - 2 - len(top)) + tr, rgb)]
    for line in body:
        text = line.center(inner) if center else line.ljust(inner)
        out.append(paint(v, rgb) + " " + text + " " + paint(v, rgb))
    out.append(paint(bl + h * (w - 2) + br, rgb))
    return "\n".join(out)


def heading(text):
    return paint(text, PURPLE, bold=True)
