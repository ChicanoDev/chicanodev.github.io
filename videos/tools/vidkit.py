"""vidkit: build, lint, caption and render the ChicanoDev VHS episodes."""
import re

_SLEEP = re.compile(r"^Sleep\s+([\d.]+)(ms|s)\b")
_SET_SPEED = re.compile(r"^Set\s+TypingSpeed\s+([\d.]+)(ms|s)\b")
_TYPE = re.compile(r'^Type(?:@([\d.]+)(ms|s))?\s+(["\'`])(.*)\3\s*$')
_BEAT = re.compile(r"^#\s*@beat\s+(\S+)\s*(.*)$")


def parse_timestamp(text):
    """'1:05' -> 65, '0:06.5' -> 6.5."""
    minutes, seconds = text.split(":")
    return int(minutes) * 60 + float(seconds)


def _to_seconds(value, unit):
    return float(value) / 1000 if unit == "ms" else float(value)


def estimate_duration(tape_text, default_typing_ms=50):
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
