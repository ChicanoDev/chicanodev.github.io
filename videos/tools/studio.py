"""Interactive narration studio: the Session state machine and its terminal UI.

`Session` holds all the decisions (resume, record, review, retake, skip, quit) and talks to a `ui` and an
audio `backend` through small interfaces, so tests drive it with fakes. `live_ui.LiveUI` is the real screen (script pinned on top,
full-screen); `TerminalUI` is the plain line-by-line fallback for pipes and dumb terminals. `make_ui()` picks.
"""
import os
import select
import sys

import cli_ui
import narration
import recorder

LOW_RATE = 44100  # Bluetooth headset mics report 8-16 kHz and sound like a phone call
SILENT_DB = -80.0


class Session:
    def __init__(self, segments, store, backend, ui, title="", episode="", device=None, autoplay=True, only=None):
        self.segments, self.store, self.backend, self.ui = segments, store, backend, ui
        self.title, self.episode, self.device, self.autoplay = title, episode, device, autoplay
        self.only, self._bad_only = None, None
        if only:
            self.only = self._find(only)
            self._bad_only = None if self.only else only
        self._stats = {}

    # --- lookup ---
    def _find(self, spec):
        spec = str(spec)
        for s in self.segments:
            slug = s.id.split("-", 1)[-1]
            if spec in (s.id, slug) or (spec.isdigit() and s.id.split("-")[0] == spec.zfill(2)):
                return s
        return None

    def _approved(self, seg):
        return self.store.status(seg.id) == "approved"

    def _incomplete(self):
        return [s for s in self.segments if not self._approved(s)]

    def info(self, nxt=None):
        rows = [(s, self.store.status(s.id), self.store.pending(s.id) is not None) for s in self.segments]
        return {"title": self.title, "episode": self.episode, "rows": rows, "device": self.device,
                "approved": sum(1 for _, st, _ in rows if st == "approved"), "total": len(rows),
                "next": nxt.id if nxt else None}

    # --- main loop ---
    def run(self):
        if self._bad_only:
            ids = ", ".join(s.id for s in self.segments)
            self.ui.note(f"No segment matches {self._bad_only!r}. Segments: {ids}", "error")
            return 2
        try:
            self.store.recover()
            for warning in self.store.warnings:
                self.ui.note(warning, "warn")
            if self.only:
                self._work(self.only, explicit=True)
                return self._wrap_up()
            return self._loop()
        except (KeyboardInterrupt, EOFError):
            self._close_ui()  # leave the full-screen view first so this message stays in the terminal
            self.ui.note("Stopped. Everything recorded so far is saved. Run the same command to resume.", "info")
            return 0
        finally:
            self._close_ui()

    def _close_ui(self):
        close = getattr(self.ui, "close", None)
        if close:
            close()

    def _wrap_up(self):
        if not self._incomplete():
            self._complete()
        return 0

    def _loop(self):
        skipped, show_overview = set(), True
        while True:
            if not self._incomplete():
                self._complete()
                return 0
            todo = [s for s in self._incomplete() if s.id not in skipped]
            seg = None
            if show_overview or not todo:
                if not todo:
                    skipped.clear()
                    todo = self._incomplete()
                self.ui.overview(self.info(todo[0]))
                key = self.ui.key("enter l q")
                show_overview = False
                if key == "q":
                    return 0
                if key == "l":
                    chosen = self.ui.choose(self.info())
                    seg = self._find(chosen) if chosen else None
                    if seg is None:
                        show_overview = True
                        continue
            explicit = seg is not None
            seg = seg or todo[0]
            result = self._work(seg, explicit=explicit)
            if result == "quit":
                return 0
            if result == "skipped":
                skipped.add(seg.id)
            elif result == "declined":
                show_overview = True

    # --- one segment ---
    def _work(self, seg, explicit=False):
        pending = self.store.pending(seg.id)
        if explicit and self._approved(seg) and not pending:
            if not self.ui.confirm(f"{seg.id} is already approved. Record a new take? "
                                   "(The approved one stays until you approve the replacement.)"):
                return "declined"
        if pending:
            self.ui.focus({"segment": seg, "total": len(self.segments)})  # script first, then the take's options
            self.ui.note(f"Found an unreviewed take from earlier: {pending.name}. Review it before recording again.")
            return self._review(seg, pending)
        while True:
            self.ui.segment({"segment": seg, "position": seg.index, "total": len(self.segments),
                             "status": self.store.status(seg.id)})
            key = self.ui.key("enter s q")
            if key == "q":
                return "quit"
            if key == "s":
                return "skipped"
            take = self._record(seg)
            if take is not None:
                return self._review(seg, take)

    def _record(self, seg):
        """Capture one take. Returns its path, or None if nothing usable was saved (the reason is shown)."""
        try:
            capture = self.backend.start(self.device)
        except recorder.RecorderError as err:
            self.ui.note(str(err), "error")
            return None
        interrupted = None
        try:
            self.ui.record_wait(capture, {"segment": seg, "total": len(self.segments)})
        except (KeyboardInterrupt, EOFError) as err:
            interrupted = err
        except recorder.RecorderError as err:
            self.ui.note(str(err), "error")
        samples, rate = capture.stop()
        self.ui.flush_input()
        if capture.error:
            self.ui.note(f"{capture.error} The take may be cut short; listen before approving.", "warn")
        path = None
        if len(samples) == 0:
            self.ui.note("Nothing was captured. Check the microphone and try again.", "error")
        else:
            try:
                path = recorder.to_wav(samples, rate, self.store.next_take_path(seg.id))
            except recorder.RecorderError as err:
                self.ui.note(str(err), "error")
        if interrupted:
            raise interrupted
        return path

    def _analyze(self, take):
        """(stats, problems, can_approve) for one take; cached."""
        if take not in self._stats:
            try:
                stats = narration.measure(take)
            except narration.BadAudio as err:
                self._stats[take] = (None, [str(err)], False)
                return self._stats[take]
            problems = narration.audio_problems(stats)
            can = stats.duration >= narration.MIN_SECONDS
            if stats.peak_db <= SILENT_DB:
                problems, can = [f"No sound was captured. {recorder.MIC_PERMISSION_HINT}"], False
            self._stats[take] = (stats, problems, can)
        return self._stats[take]

    def _review(self, seg, take):
        takes = self.store.takes(seg.id)
        idx = takes.index(take)
        play_now = self.autoplay
        while True:
            take = takes[idx]
            stats, problems, can_approve = self._analyze(take)
            self.ui.review({"segment": seg, "total": len(self.segments), "take": take,
                            "position": idx + 1, "count": len(takes),
                            "duration": stats.duration if stats else 0.0, "problems": problems,
                            "can_approve": can_approve, "is_approved": self.store.approved_take(seg.id) == take.name})
            if play_now:
                self._play(take)
            play_now = False
            key = self.ui.key("enter p r b n q")
            self.backend.stop_playback()
            if key == "enter" and can_approve:
                try:
                    self.store.approve(seg.id, take)
                except recorder.RecorderError as err:
                    self.ui.note(str(err), "error")
                    continue
                for warning in self.store.warnings:
                    self.ui.note(warning, "warn")
                self.ui.note(f"Approved {take.name}", "ok")
                return "approved"
            if key in ("r", "enter"):  # Enter on an unusable take means: try again
                new = self._record(seg)
                if new is None:
                    continue
                if self.store.approved_take(seg.id) != take.name:
                    self.store.reject(seg.id, take)
                takes = self.store.takes(seg.id)
                idx = takes.index(new)
                play_now = self.autoplay
            elif key == "p":
                play_now = True
            elif key == "b" and idx > 0:
                idx, play_now = idx - 1, True
            elif key == "n" and idx < len(takes) - 1:
                idx, play_now = idx + 1, True
            elif key == "q":
                return "quit"

    def _play(self, take):
        try:
            self.backend.play(take)
        except recorder.RecorderError as err:
            self.ui.note(str(err), "warn")

    def _complete(self):
        problems = {}
        for seg in self.segments:
            canonical = self.store.canonical(seg.id)
            try:
                found = narration.audio_problems(narration.measure(canonical))
            except narration.BadAudio as err:
                found = [str(err)]
            if found:
                problems[seg.id] = found
        info = self.info()
        info["problems"] = problems
        self.ui.complete(info)


# --- the real screen -----------------------------------------------------------------------------

def _fmt_time(seconds):
    return f"{int(seconds // 60):02}:{seconds % 60:04.1f}"


class TerminalUI:
    def __init__(self, out=None):
        self.out = out or sys.stdout

    @property
    def fd(self):
        return sys.stdin.fileno()

    # output
    def say(self, text=""):
        print(text, file=self.out, flush=True)

    def _sym(self, ok, fancy, plain):
        return fancy if not cli_ui.is_dumb() else plain

    def _row(self, seg, status, pending):
        mark, rgb, word = {
            "approved": (self._sym(1, "✓", "x"), cli_ui.GREEN, "Approved"),
            "pending": (self._sym(1, "◐", "~"), cli_ui.YELLOW, "Recorded, waiting for your approval"),
            "conflict": (self._sym(1, "!", "!"), cli_ui.RED, "More than one audio file. Remove the extras"),
        }.get(status, (self._sym(1, "○", "o"), cli_ui.MUTED, "Not recorded"))
        if status == "approved" and pending:
            word += " (newer take waiting)"
        return f"  {cli_ui.paint(mark, rgb)} {seg.id:<20} {cli_ui.paint(word, rgb)}"

    def _header(self, info):
        self.say(cli_ui.panel(["", "CHICANODEV / VIDKIT", "Narration Recording Studio", ""], center=True))
        self.say()
        if info["title"]:
            self.say("  " + cli_ui.paint(info["title"], cli_ui.CYAN, bold=True))
        done, total = info["approved"], info["total"]
        self.say(f"  {done} of {total} segments approved")
        dev = info["device"]
        if dev:
            self.say(f"  Microphone: {dev.name}")
            self.say("  Saved as: WAV, mono, 48 kHz, 16-bit")
            if dev.rate < LOW_RATE:
                self.say(cli_ui.paint(f"  ! This mic runs at {dev.rate / 1000:g} kHz (often a Bluetooth headset), so "
                                      "narration will sound thin. Pick another: --device (see --list-devices).",
                                      cli_ui.YELLOW))
        self.say()

    def status(self, info):
        self._header(info)
        for seg, status, pending in info["rows"]:
            self.say(self._row(seg, status, pending))

    def overview(self, info):
        self.status(info)
        self.say()
        nxt = info["next"]
        self.say(f"  {cli_ui.paint('[Enter]', cli_ui.PURPLE)} Continue with {nxt}")
        self.say(f"  {cli_ui.paint('[l]', cli_ui.PURPLE)}     List and select a segment")
        self.say(f"  {cli_ui.paint('[q]', cli_ui.PURPLE)}     Quit")

    def _script(self, info):
        """The narration for this segment, boxed. Printed on every screen so it is never out of view."""
        seg = info["segment"]
        title = f"SEGMENT {seg.index:02} / {info['total']:02} - {seg.title.upper()}"
        self.say()
        self.say(cli_ui.panel([""] + seg.text.splitlines() + [""], title=title))

    def focus(self, info):
        pass  # the plain screen prints the script with each screen instead

    def segment(self, info):
        self._script(info)
        self.say()
        if info["status"] == "approved":
            self.say("  (Already approved. Approving a new take replaces it; the old audio is archived.)")
        self.say(f"  {cli_ui.paint('[Enter]', cli_ui.PURPLE)} Start recording")
        self.say(f"  {cli_ui.paint('[s]', cli_ui.PURPLE)}     Skip for now")
        self.say(f"  {cli_ui.paint('[q]', cli_ui.PURPLE)}     Save and quit")

    def review(self, info):
        seg, take = info["segment"], info["take"]
        lines = ["", f"Segment: {seg.id}", f"Take:    {take.name.split('.')[-2]} ({info['position']} of {info['count']})"
                 + ("  [approved]" if info["is_approved"] else ""),
                 f"Length:  {info['duration']:.1f} seconds", ""]
        self._script(info)
        self.say()
        self.say(cli_ui.panel(lines, title="TAKE RECORDED", rgb=cli_ui.CYAN))
        for problem in info["problems"]:
            self.say(cli_ui.paint("  ! ", cli_ui.YELLOW) + problem)
        self.say()
        first = "Approve and continue" if info["can_approve"] else "Record again (this take is unusable)"
        self.say(f"  {cli_ui.paint('[Enter]', cli_ui.PURPLE)} {first}")
        self.say(f"  {cli_ui.paint('[p]', cli_ui.PURPLE)} Play   {cli_ui.paint('[r]', cli_ui.PURPLE)} Record again"
                 + (f"   {cli_ui.paint('[b]', cli_ui.PURPLE)} Earlier take" if info["position"] > 1 else "")
                 + (f"   {cli_ui.paint('[n]', cli_ui.PURPLE)} Later take" if info["position"] < info["count"] else "")
                 + f"   {cli_ui.paint('[q]', cli_ui.PURPLE)} Save and quit")

    def note(self, text, kind="info"):
        mark, rgb = {"ok": ("✓" if not cli_ui.is_dumb() else "ok", cli_ui.GREEN),
                     "warn": ("!", cli_ui.YELLOW), "error": ("x", cli_ui.RED)}.get(kind, (">", cli_ui.CYAN))
        self.say(f"  {cli_ui.paint(mark, rgb, bold=True)} {text}")

    def choose(self, info):
        self.say()
        for n, (seg, status, pending) in enumerate(info["rows"], 1):
            self.say(f"  {n:>2}. {self._row(seg, status, pending).strip()}")
        answer = input("\n  Segment number (blank to go back): ").strip()
        if not answer:
            return None
        rows = [seg for seg, _, _ in info["rows"]]
        if answer.isdigit() and 1 <= int(answer) <= len(rows):
            return rows[int(answer) - 1].id
        self.note(f"{answer!r} is not one of the numbers above.", "warn")
        return None

    def confirm(self, question):
        self.say()
        self.say(f"  {question} [y/N]")
        return self.key("y n enter") == "y"

    def complete(self, info):
        self.say()
        self.say(cli_ui.panel(["", "RECORDING COMPLETE", ""], rgb=cli_ui.GREEN, center=True))
        self.say()
        self.say(f"  Episode: {info['title'] or info['episode']}")
        self.say()
        self.say(cli_ui.paint(f"  ✓ {info['approved']} / {info['total']} narration segments approved", cli_ui.GREEN))
        for seg_id, problems in info["problems"].items():
            for problem in problems:
                self.say(cli_ui.paint(f"  ! {seg_id}: {problem}", cli_ui.YELLOW))
        if not info["problems"]:
            self.say(cli_ui.paint("  ✓ Audio checks passed", cli_ui.GREEN))
        ep = info["episode"] or "<episode>"
        self.say("\n  Next steps:\n")
        self.say(f"  python3 tools/vidkit.py check-audio {ep}\n")
        self.say(f"  python3 tools/vidkit.py build {ep} --format both")

    # input
    def _read(self):
        import termios
        import tty
        old = termios.tcgetattr(self.fd)
        try:
            tty.setcbreak(self.fd, termios.TCSANOW)  # NOW: do not drop a key typed early
            return os.read(self.fd, 1)
        finally:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, old)

    def key(self, allowed=""):
        names = set(allowed.split())
        while True:
            raw = self._read()
            if not raw or raw == b"\x04":
                raise EOFError
            key = "enter" if raw in (b"\n", b"\r") else raw.decode(errors="ignore").lower()
            if not names or key in names:
                return key

    def flush_input(self):
        import termios
        termios.tcflush(self.fd, termios.TCIFLUSH)

    def record_wait(self, capture, info=None):
        import termios
        import tty
        old = termios.tcgetattr(self.fd)
        if info:
            self._script(info)
        self.say()
        self.say(cli_ui.paint("  ● RECORDING" if not cli_ui.is_dumb() else "  * RECORDING", cli_ui.RED, bold=True))
        self.say()
        self.say(f"  {cli_ui.paint('[Enter]', cli_ui.PURPLE)} Stop recording\n")
        try:
            tty.setcbreak(self.fd, termios.TCSANOW)  # NOW: do not drop a key typed early
            while True:
                print(f"\r  {_fmt_time(capture.elapsed)}", end="", file=self.out, flush=True)
                if select.select([self.fd], [], [], 0.1)[0]:
                    raw = os.read(self.fd, 1)
                    if not raw or raw == b"\x04":
                        raise EOFError
                    if raw in (b"\n", b"\r"):
                        return
        finally:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, old)
            print(file=self.out, flush=True)


def make_ui(out=None):
    """The persistent full-screen recorder on a real terminal; the plain line-by-line screen otherwise
    (pipes, TERM=dumb, or rich not installed)."""
    out = out or sys.stdout
    smart = sys.stdin.isatty() and out.isatty() and os.environ.get("TERM", "") not in ("", "dumb")
    if smart:
        try:
            import live_ui
            return live_ui.LiveUI(out)
        except ImportError:
            pass
    return TerminalUI(out)
