"""The real TerminalUI in a pseudo-terminal: single keypresses, live timer, Ctrl+C. Fake microphone only."""
import os
import pty
import re
import select
import shutil
import signal
import sys
import time
from pathlib import Path

import pytest

from test_narration import VOICEOVER

TOOLS = Path(__file__).resolve().parent.parent / "tools"
TESTS = Path(__file__).resolve().parent

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

CHILD = f"""
import sys
sys.path[:0] = [{str(TOOLS)!r}, {str(TESTS)!r}]
from pathlib import Path
import narration, recorder, studio
from fake_audio import FakeBackend
folder = Path(sys.argv[1])
backend = FakeBackend()
session = studio.Session(narration.episode_segments(folder), recorder.TakeStore(folder, {{}}), backend,
                         studio.TerminalUI(), title="Demo", episode="demo/01-ep", device=backend.resolve())
sys.exit(session.run())
"""


def drive(folder, steps, timeout=20):
    """Run the studio in a pty. `steps` is [(text to wait for, bytes to send)]. Returns (output, exit code)."""
    env = dict(os.environ, TERM="xterm", NO_COLOR="1", COLUMNS="80")
    pid, fd = pty.fork()
    if pid == 0:
        signal.signal(signal.SIGINT, signal.SIG_DFL)  # a background-launched pytest passes SIGINT=ignored down
        os.execve(sys.executable, [sys.executable, "-c", CHILD, str(folder)], env)
    seen = ""
    try:
        for expect, send in steps:
            deadline = time.time() + timeout
            while expect not in seen:
                assert time.time() < deadline, f"timed out waiting for {expect!r}. Saw:\n{seen[-800:]}"
                if select.select([fd], [], [], 0.2)[0]:
                    try:
                        seen += os.read(fd, 4096).decode(errors="replace")
                    except OSError:
                        break
            seen = seen[seen.index(expect) + len(expect):] if expect in seen else seen
            if send:
                time.sleep(0.1)  # let the program reach its read
                os.write(fd, send)
        end = time.time() + timeout
        while time.time() < end:
            if select.select([fd], [], [], 0.2)[0]:
                try:
                    if not os.read(fd, 4096):
                        break
                except OSError:
                    break
        _, status = os.waitpid(pid, 0)
        return os.waitstatus_to_exitcode(status)
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "voiceover.md").write_text(VOICEOVER)
    return tmp_path


def test_three_keypresses_record_and_approve_then_quit(folder):
    code = drive(folder, [
        ("Quit", b"\r"),                      # overview: continue
        ("Save and quit", b"\r"),             # script prompt: start recording
        ("Stop recording", b"\r"),            # Enter stops
        ("Save and quit", b"\r"),             # review prompt: Enter approves
        ("Approved", b""),
        ("Save and quit", b"q"),              # next segment's script: quit
    ])
    assert code == 0
    assert (folder / "narration" / "01-hook.wav").exists()
    assert [p.name for p in (folder / "narration" / "takes").glob("*.take*.wav")] == ["01-hook.take1.wav"]


def test_ctrl_c_during_recording_exits_cleanly_and_keeps_the_take(folder):
    code = drive(folder, [
        ("Quit", b"\r"),
        ("Save and quit", b"\r"),
        ("Stop recording", b"\x03"),
        ("resume", b""),
    ])
    assert code == 0
    assert len(list((folder / "narration" / "takes").glob("01-hook.take*.wav"))) == 1
    assert not (folder / "narration" / "01-hook.wav").exists()


def test_ctrl_d_at_a_prompt_exits_cleanly(folder):
    assert drive(folder, [("Quit", b"\x04"), ("resume", b"")]) == 0


def test_script_text_is_shown_exactly(folder):
    assert drive(folder, [("Quit", b"\r"), ("Linux has no C drive.", b"q")]) == 0
