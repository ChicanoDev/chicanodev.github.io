"""vidkit: build, lint, caption and render the ChicanoDev VHS episodes."""
import re
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

_SLEEP = re.compile(r"^Sleep\s+([\d.]+)(ms|s)\b")
_SET_SPEED = re.compile(r"^Set\s+TypingSpeed\s+([\d.]+)(ms|s)\b")
_TYPE = re.compile(r'^Type(?:@([\d.]+)(ms|s))?\s+(["\'`])(.*)\3\s*$')
_BEAT = re.compile(r"^#\s*@beat\s+(\S+)\s*(.*)$")
_VO_HEADING = re.compile(r"^##\s*\[(\d+:\d+(?:\.\d+)?)-(\d+:\d+(?:\.\d+)?)\]\s*(.*)$")


def parse_timestamp(text):
    """'1:05' -> 65, '0:06.5' -> 6.5."""
    minutes, seconds = text.split(":")
    return int(minutes) * 60 + float(seconds)


def _to_seconds(value, unit):
    return float(value) / 1000 if unit == "ms" else float(value)


def estimate_duration(tape_text, default_typing_ms=70):
    """Seconds of visible recording a tape produces (Hide..Show is cut by VHS)."""
    speed = default_typing_ms / 1000
    hidden = False
    total = 0.0
    for raw in tape_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "Hide":
            hidden = True
            continue
        if line == "Show":
            hidden = False
            continue
        if m := _SET_SPEED.match(line):
            speed = _to_seconds(*m.groups())
            continue
        if hidden:
            continue
        if m := _SLEEP.match(line):
            total += _to_seconds(*m.groups())
        elif m := _TYPE.match(line):
            per_char = _to_seconds(m.group(1), m.group(2)) if m.group(1) else speed
            total += per_char * len(m.group(4))
    return total


def parse_tape_beats(tape_text):
    """[(seconds, label)] from '# @beat M:SS Label' markers."""
    beats = []
    for line in tape_text.splitlines():
        if m := _BEAT.match(line.strip()):
            beats.append((parse_timestamp(m.group(1)), m.group(2).strip()))
    return beats


@dataclass(frozen=True)
class Beat:
    start: float
    end: float
    title: str
    text: str


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def parse_voiceover(md_text):
    """Beats from '## [M:SS-M:SS] Title' sections; '>' note lines and other headings are skipped."""
    beats = []
    current = None
    for line in md_text.splitlines():
        if line.startswith("#"):
            if current:
                beats.append(current)
            current = None
            if m := _VO_HEADING.match(line):
                current = [parse_timestamp(m.group(1)), parse_timestamp(m.group(2)), m.group(3).strip(), []]
        elif current is not None and line.strip() and not line.lstrip().startswith(">"):
            current[3].append(line.strip())
    if current:
        beats.append(current)
    return [Beat(start, end, title, " ".join(lines)) for start, end, title, lines in beats]


def make_cues(beats, max_chars=32, max_lines=2):
    """Caption cues: wrapped to max_chars, max_lines per cue, timed by length inside each beat."""
    cues = []
    for beat in beats:
        lines = textwrap.wrap(beat.text, width=max_chars)
        chunks = ["\n".join(lines[i:i + max_lines]) for i in range(0, len(lines), max_lines)]
        total = sum(len(c.replace("\n", "")) for c in chunks)
        span = beat.end - beat.start
        cursor = beat.start
        for n, chunk in enumerate(chunks):
            end = beat.end if n == len(chunks) - 1 else cursor + span * len(chunk.replace("\n", "")) / total
            cues.append(Cue(cursor, end, chunk))
            cursor = end
    return cues


def _srt_time(seconds):
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def format_srt(cues):
    blocks = [
        f"{n}\n{_srt_time(c.start)} --> {_srt_time(c.end)}\n{c.text}\n"
        for n, c in enumerate(cues, 1)
    ]
    return "\n".join(blocks)


def offset_cues(cues, offset):
    return [Cue(c.start + offset, c.end + offset, c.text) for c in cues]


def _estimate_at_beat(tape_text, marker_line):
    """Estimated recording time at the line index of a beat marker."""
    return estimate_duration("\n".join(tape_text.splitlines()[:marker_line]))


def lint_episode(tape_text, voiceover_md, min_seconds=60, max_seconds=90,
                 min_words=140, max_words=230, max_typed=32, tolerance=1.0):
    """Return a list of human-readable problems; empty means the episode is ready."""
    problems = []

    total = estimate_duration(tape_text)
    if not min_seconds <= total <= max_seconds:
        problems.append(f"duration {total:.0f}s outside {min_seconds}-{max_seconds}s")

    beats = parse_voiceover(voiceover_md)
    words = sum(len(b.text.split()) for b in beats)
    if not min_words <= words <= max_words:
        problems.append(f"voiceover has {words} words, want {min_words}-{max_words}")

    for raw in tape_text.splitlines():
        m = _TYPE.match(raw.strip())
        if m and len(m.group(4)) > max_typed:
            problems.append(f"typed line over {max_typed} chars: {m.group(4)[:40]!r}")

    markers = [(n, m) for n, raw in enumerate(tape_text.splitlines())
               if (m := _BEAT.match(raw.strip()))]
    if len(markers) != len(beats):
        problems.append(f"beat count: tape has {len(markers)}, voiceover has {len(beats)}")
    for (line_no, m), beat in zip(markers, beats):
        marked = parse_timestamp(m.group(1))
        if abs(marked - beat.start) > tolerance:
            problems.append(f"beat {beat.title!r}: voiceover starts at {beat.start:.0f}s, tape marker at {marked:.0f}s")
        est = _estimate_at_beat(tape_text, line_no)
        if abs(marked - est) > tolerance:
            problems.append(f"beat {beat.title!r}: marker {marked:.0f}s but estimate is {est:.1f}s")
    return problems


def build_tape(settings_text, body_text, output_path):
    return f"Output {output_path}\n{settings_text.rstrip()}\n\n{body_text.rstrip()}\n"


ROOT = Path(__file__).resolve().parent.parent

EPISODES = [
    ("linux-fs", "01-no-c-drive"),
    ("linux-fs", "02-where-programs-live"),
    ("linux-fs", "03-where-things-change"),
    ("linux-fs", "04-the-weird-ones"),
    ("linux-cmds", "01-get-around"),
    ("linux-cmds", "02-move-stuff"),
    ("linux-cmds", "03-read-files"),
    ("linux-cmds", "04-find-anything"),
    ("linux-cmds", "05-pipes-and-text"),
    ("linux-cmds", "06-users-and-permissions"),
    ("linux-cmds", "07-system-health"),
    ("linux-cmds", "08-network-and-archives"),
    ("linux-cmds", "09-help-yourself"),
    ("where-code-runs", "01-bare-metal-vs-vm"),
    ("where-code-runs", "02-containers"),
    ("where-code-runs", "03-the-cloud"),
]


def episode_dir(series, slug):
    return ROOT / "series" / series / slug


def _cmd_lint(argv):
    wanted = set(argv)
    failed = False
    for series, slug in EPISODES:
        name = f"{series}/{slug}"
        if wanted and name not in wanted and slug not in wanted:
            continue
        folder = episode_dir(series, slug)
        if not (folder / "body.tape").exists() or not (folder / "voiceover.md").exists():
            print(f"-- {name}: missing files")
            failed = failed or not wanted
            continue
        tape, voiceover = (folder / "body.tape").read_text(), (folder / "voiceover.md").read_text()
        problems = lint_episode(tape, voiceover)
        print(f"{'OK' if not problems else '!!'} {name}  ~{estimate_duration(tape):.1f}s")
        for problem in problems:
            print(f"     {problem}")
        failed = failed or bool(problems)
    return 1 if failed else 0


COMMANDS = {"lint": _cmd_lint}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in COMMANDS:
        print(f"usage: vidkit.py {{{'|'.join(COMMANDS)}}} [episode ...]")
        return 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main())
