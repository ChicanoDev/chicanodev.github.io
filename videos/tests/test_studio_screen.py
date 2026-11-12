"""The persistent recording screen as a pure render: script pinned on top, status/controls below."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import studio_screen as ss  # noqa: E402

SCRIPT = ("Start with /usr/local/bin. It holds your own tools.\n\n"
          "Run `ls -la /etc/ssh` and read the output carefully, then `cp a b`.")
SEG = SimpleNamespace(id="02-bin", index=2, title="Bin", text=SCRIPT)
TAKE = {"name": "02-bin.take3.wav", "position": 3, "count": 5, "duration": 4.2, "problems": [],
        "can_approve": True, "is_approved": False}


def render(state, width=80, height=24):
    console = Console(width=width, height=height, record=True, force_terminal=False, color_system=None)
    console.print(ss.build(state, width, height))
    return console.export_text().splitlines()


def state(mode, **kw):
    return ss.ScreenState(segment=SEG, total=6, mode=mode, take=TAKE if mode == "review" else None, **kw)


@pytest.mark.parametrize("mode", ["ready", "recording", "review"])
def test_script_and_title_are_on_screen_in_every_mode(mode):
    text = "\n".join(render(state(mode)))
    assert "SEGMENT 02 / 06 - BIN" in text
    assert "Start with /usr/local/bin. It holds your own tools." in text
    assert "`ls -la /etc/ssh`" in text


def test_script_is_above_the_status_area():
    lines = render(state("recording", elapsed=3.5))
    script_row = next(i for i, l in enumerate(lines) if "usr/local/bin" in l)
    status_row = next(i for i, l in enumerate(lines) if "RECORDING" in l)
    assert script_row < status_row


def test_recording_shows_timer_and_stop_control():
    text = "\n".join(render(state("recording", elapsed=65.2)))
    assert "01:05.2" in text and "Stop recording" in text


def test_review_shows_take_info_and_all_controls():
    text = "\n".join(render(state("review")))
    for want in ("Take 3 of 5", "4.2 seconds", "Approve", "Play", "Record again", "Earlier take", "Later take", "quit"):
        assert want in text


def test_narrow_terminal_never_overflows_and_keeps_every_word():
    lines = render(state("review"), width=40, height=40)
    assert max(len(l) for l in lines) <= 40
    flat = " ".join("".join(c for c in l if c not in "│╭╮╰╯─").strip() for l in lines)
    for word in ("/usr/local/bin.", "`ls", "-la", "/etc/ssh`", "carefully,"):
        assert word in flat.split()


def test_output_fits_the_terminal_height():
    assert len(render(state("review"), width=60, height=14)) <= 14


def test_long_script_shows_scroll_hint_and_window_moves():
    long = SimpleNamespace(id="x", index=1, title="Long", text="\n\n".join(f"Line number {i} of the script." for i in range(30)))
    first = "\n".join(render(ss.ScreenState(segment=long, total=1, mode="ready"), width=60, height=16))
    assert "Line number 0 of" in first and "Line number 29 of" not in first and "scroll" in first
    moved = "\n".join(render(ss.ScreenState(segment=long, total=1, mode="ready", script_offset=10), width=60, height=16))
    assert "Line number 0 of" not in moved


def test_scroll_offset_is_clamped_to_the_text():
    long = SimpleNamespace(id="x", index=1, title="Long", text="\n\n".join(f"Line number {i} of the script." for i in range(30)))
    text = "\n".join(render(ss.ScreenState(segment=long, total=1, mode="ready", script_offset=9999), width=60, height=16))
    assert "Line number 29 of" in text


def test_short_script_has_no_scroll_hint():
    assert "scroll" not in "\n".join(render(state("ready"), width=80, height=30))


def test_script_lines_wraps_without_changing_words():
    lines = ss.script_lines(SCRIPT, 20)
    assert " ".join(" ".join(lines).split()) == " ".join(SCRIPT.split())
    assert all(len(l) <= 20 for l in lines)
