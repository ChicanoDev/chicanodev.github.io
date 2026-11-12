"""The real recording screen in a pseudo-terminal, read back through a terminal emulator (pyte).

What is asserted is what a person would see on screen after each keypress, plus that nothing is
pushed into scrollback. Fake microphone only.
"""
import codecs
import fcntl
import os
import pty
import re
import select
import shutil
import signal
import struct
import sys
import termios
import time
from pathlib import Path

import pyte
import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
TESTS = Path(__file__).resolve().parent

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

HOOK = "Start with /usr/local/bin. It holds core commands, like `ls` and `cp`."
VOICEOVER = f"""# Demo

## [0:00-0:10] Hook
{HOOK}

## [0:10-0:25] Bin
Second segment script text.
"""
LONG = "\n\n".join(f"Paragraph {i:02} of a long narration section." for i in range(40))
LONG_VOICEOVER = f"# Demo\n\n## [0:00-0:10] Hook\n{LONG}\n\n## [0:10-0:25] Bin\nSecond.\n"

CHILD = f"""
import sys
sys.path[:0] = [{str(TOOLS)!r}, {str(TESTS)!r}]
from pathlib import Path
import narration, recorder, studio
from fake_audio import FakeBackend
folder = Path(sys.argv[1])
backend = FakeBackend()
session = studio.Session(narration.episode_segments(folder), recorder.TakeStore(folder, {{}}), backend,
                         studio.make_ui(), title="Demo", episode="demo/01-ep", device=backend.resolve())
sys.exit(session.run())
"""


class Term:
    """A child process on a pty whose output is interpreted by a virtual terminal."""

    def __init__(self, folder, cols=80, rows=24, term="xterm-256color"):
        self.cols, self.rows = cols, rows
        # two screens, like a real terminal: pyte itself ignores the alternate-screen switch (?1049h/l)
        self.main = pyte.HistoryScreen(cols, rows, history=2000, ratio=1.0)
        self.alt = pyte.HistoryScreen(cols, rows, history=2000, ratio=1.0)
        self.streams = {id(self.main): pyte.Stream(self.main), id(self.alt): pyte.Stream(self.alt)}
        self.screen = self.main
        self.raw = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")  # reads can split a character
        env = dict(os.environ, TERM=term, NO_COLOR="1")
        env.pop("COLUMNS", None)
        env.pop("LINES", None)
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            signal.signal(signal.SIGINT, signal.SIG_DFL)  # a background-launched pytest passes SIGINT=ignored down
            os.execve(sys.executable, [sys.executable, "-c", CHILD, str(folder)], env)
        self._winsize(cols, rows)
        self.code = None

    def _winsize(self, cols, rows):
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def resize(self, cols, rows):
        self.cols, self.rows = cols, rows
        self._winsize(cols, rows)
        self.main.resize(rows, cols)
        self.alt.resize(rows, cols)
        os.kill(self.pid, signal.SIGWINCH)

    def pump(self, wait=0.1):
        if select.select([self.fd], [], [], wait)[0]:
            try:
                chunk = os.read(self.fd, 65536)
            except OSError:
                return False
            if not chunk:
                return False
            data = self._decoder.decode(chunk)
            self.raw += data
            for part in re.split(r"(\x1b\[\?1049[hl])", data):
                if part == "\x1b[?1049h":
                    self.screen = self.alt
                elif part == "\x1b[?1049l":
                    self.screen = self.main
                elif part:
                    self.streams[id(self.screen)].feed(part)
        return True

    @property
    def display(self):
        return "\n".join(self.screen.display)

    def scrolled(self):
        """Lines the full-screen view pushed off its top. Must stay 0 while the person is working."""
        return len(self.alt.history.top)

    def scrollback(self):
        """What the normal screen holds (history + visible): what is left in the terminal after the
        full-screen view is gone."""
        rows = ["".join(line[i].data for i in sorted(line)) for line in self.main.history.top]
        return "\n".join(rows + list(self.main.display))

    def settle(self, quiet=0.4, timeout=5):
        """Pump until the program has been silent for `quiet` seconds (the screen has caught up)."""
        end, last = time.time() + timeout, time.time()
        while time.time() < end and time.time() - last < quiet:
            before = len(self.raw)
            self.pump(0.05)
            if len(self.raw) != before:
                last = time.time()

    def wait_for(self, text, timeout=15):
        deadline = time.time() + timeout
        while text not in self.display:
            assert time.time() < deadline, f"timed out waiting for {text!r}. Screen:\n{self.display}"
            if not self.pump():
                break
        assert text in self.display, f"{text!r} never appeared. Screen:\n{self.display}"

    def send(self, data, then=None):
        time.sleep(0.15)  # let the program reach its read
        os.write(self.fd, data)
        self.pump(0.05)  # keep draining so the program never blocks writing to a full pty
        if then:
            self.wait_for(then)

    def finish(self, timeout=15):
        """Wait for the child to exit; fail (and kill it) instead of hanging forever."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.pump(0.05)
            done, status = os.waitpid(self.pid, os.WNOHANG)
            if done:
                while self.pump(0.02) and select.select([self.fd], [], [], 0)[0]:
                    pass
                self.code = os.waitstatus_to_exitcode(status)
                return self.code
        self.close()
        raise AssertionError(f"program did not exit. Screen:\n{self.display}")

    def close(self):
        try:
            os.kill(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "voiceover.md").write_text(VOICEOVER)
    return tmp_path


@pytest.fixture
def term_factory():
    made = []

    def make(folder, **kw):
        made.append(Term(folder, **kw))
        return made[-1]
    yield make
    for t in made:
        t.close()


def script_visible(t, text=HOOK, title="SEGMENT 01 / 02 - HOOK"):
    flat = " ".join(t.display.split())
    squashed = " ".join(c for c in flat.replace("│", " ").split())
    assert title in flat, f"title missing:\n{t.display}"
    assert text in squashed, f"script missing:\n{t.display}"


def test_script_stays_on_screen_through_five_takes_playback_and_approval(folder, term_factory):
    t = term_factory(folder)
    t.wait_for("Continue with")
    t.send(b"\r", then="Start recording")
    script_visible(t)
    t.send(b"\r", then="RECORDING")
    script_visible(t)
    t.send(b"\r", then="Take 1 of 1")
    script_visible(t)
    t.send(b"p")
    script_visible(t)
    for n in range(2, 6):
        t.send(b"r", then="RECORDING")
        script_visible(t)
        t.send(b"\r", then=f"Take {n} of {n}")
        script_visible(t)
        t.send(b"p")
        script_visible(t)
    t.send(b"b", then="Take 4 of 5")
    script_visible(t)
    t.send(b"b", then="Take 3 of 5")
    script_visible(t)
    t.send(b"\r", then="SEGMENT 02 / 02 - BIN")  # approve take 3, move on
    assert (folder / "narration" / "01-hook.wav").exists()
    assert len(list((folder / "narration" / "takes").glob("01-hook.take*.wav"))) == 5
    assert t.scrolled() == 0
    t.send(b"q")
    assert t.finish() == 0
    assert t.scrolled() == 0
    assert "Start with /usr/local/bin" not in t.scrollback()


def test_resume_shows_the_script_with_the_pending_takes_options(folder, term_factory):
    first = term_factory(folder)
    first.wait_for("Continue with")
    first.send(b"\r", then="Start recording")
    first.send(b"\r", then="RECORDING")
    first.send(b"\r", then="Take 1 of 1")
    first.send(b"q")
    assert first.finish() == 0

    again = term_factory(folder)
    again.wait_for("Continue with")
    again.send(b"\r", then="Approve and continue")
    script_visible(again)
    assert "unreviewed" in again.display
    again.send(b"q")
    assert again.finish() == 0


def test_narrow_terminal_keeps_every_word_of_the_script(folder, term_factory):
    t = term_factory(folder, cols=38, rows=24)
    t.wait_for("Continue with")
    t.send(b"\r", then="Start recording")
    for word in ("/usr/local/bin.", "`ls`", "`cp`.", "commands,"):
        assert word in t.display.replace("│", " ").split()
    assert all(len(line.rstrip()) <= 38 for line in t.screen.display)
    t.send(b"\r", then="RECORDING")
    assert "/usr/local/bin." in t.display.split()
    t.send(b"\x03")
    assert t.finish() == 0


def test_resizing_the_terminal_redraws_with_the_script_still_there(folder, term_factory):
    t = term_factory(folder)
    t.wait_for("Continue with")
    t.send(b"\r", then="Start recording")
    t.resize(44, 18)
    t.wait_for("SEGMENT 01 / 02 - HOOK")
    for _ in range(30):
        t.pump(0.05)
    assert "/usr/local/bin." in t.display.replace("│", " ").split()
    t.resize(90, 30)
    t.wait_for("Start recording")
    t.send(b"q")
    assert t.finish() == 0


def test_long_script_scrolls_inside_the_screen_not_the_terminal(tmp_path, term_factory):
    (tmp_path / "voiceover.md").write_text(LONG_VOICEOVER)
    t = term_factory(tmp_path, cols=60, rows=16)
    t.wait_for("Continue with")
    t.send(b"\r", then="scroll")
    assert "Paragraph 00" in t.display and "Paragraph 39" not in t.display
    for _ in range(12):
        t.send(b"\x1b[B")
    t.send(b"\x1b[6~")  # page down
    t.settle()
    assert "Paragraph 00" not in t.display
    t.send(b"\r", then="RECORDING")
    t.settle()
    assert "Paragraph 00" not in t.display and "Paragraph" in t.display  # same window; never reset mid-segment
    assert t.scrolled() == 0  # the terminal itself never scrolled; the script moved inside the panel
    t.send(b"\x03")
    assert t.finish() == 0
    assert "Paragraph 00" not in t.scrollback()


def test_ctrl_c_restores_the_normal_screen_and_keeps_the_take(folder, term_factory):
    t = term_factory(folder)
    t.wait_for("Continue with")
    t.send(b"\r", then="Start recording")
    t.send(b"\r", then="RECORDING")
    t.send(b"\x03")
    assert t.finish() == 0
    assert "\x1b[?1049l" in t.raw
    assert "resume" in t.raw.split("\x1b[?1049l")[-1]
    assert len(list((folder / "narration" / "takes").glob("01-hook.take*.wav"))) == 1


def test_ctrl_d_at_a_prompt_exits_cleanly(folder, term_factory):
    t = term_factory(folder)
    t.wait_for("Continue with")
    t.send(b"\x04")
    assert t.finish() == 0


def test_dumb_terminal_falls_back_to_plain_output_with_the_script_every_time(folder, term_factory):
    t = term_factory(folder, term="dumb")
    t.wait_for("Continue with")
    t.send(b"\r", then="Start recording")
    t.send(b"\r", then="RECORDING")
    t.send(b"\r", then="TAKE RECORDED")
    t.send(b"r", then="RECORDING")
    t.send(b"\r", then="TAKE RECORDED")
    t.send(b"q")
    assert t.finish() == 0
    assert "\x1b[?1049h" not in t.raw
    flat = " ".join(t.raw.replace("|", " ").split())
    assert flat.count(HOOK) >= 5  # ready, recording, review, recording again, review again
