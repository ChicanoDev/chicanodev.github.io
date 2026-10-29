"""Retime a VHS tape to narration without ever editing the original tape.

Typing is never touched (it would turn into an unreadable blur). Each beat's final Sleep is extended
to hold a longer narration, or every Sleep in the beat is scaled down (not below MIN_SCALE) for a
shorter one. If neither fits, we stop and say exactly what to change.
"""
import re
from dataclasses import dataclass

import vidkit

MIN_SCALE = 0.5
KEEP_TOLERANCE = 0.005
_SLEEP_LINE = re.compile(r"^(\s*)Sleep\s+([\d.]+)(ms|s)\b(.*)$")


class SyncError(Exception):
    """The tape cannot be fitted to the narration; the message says why and what to do."""


@dataclass(frozen=True)
class Block:
    title: str
    lines: tuple

    @property
    def seconds(self):
        return vidkit.estimate_duration("\n".join(self.lines))


@dataclass(frozen=True)
class BeatPlan:
    index: int
    title: str
    natural: float
    target: float
    action: str  # keep | hold | shrink
    scale: float = 1.0


def split_beats(tape_text):
    """(preamble_lines, [Block]) split at '# @beat' markers."""
    preamble, blocks, current = [], [], None
    for line in tape_text.splitlines():
        m = vidkit._BEAT.match(line.strip())
        if m:
            current = [m.group(2).strip(), [line]]
            blocks.append(current)
        elif current is None:
            preamble.append(line)
        else:
            current[1].append(line)
    return preamble, [Block(title, tuple(lines)) for title, lines in blocks]


def beat_periods(narration_seconds, pause, tail):
    """How long each beat's visuals must last: its narration plus the pause before the next one."""
    n = len(narration_seconds)
    return [d + (pause if i < n - 1 else tail) for i, d in enumerate(narration_seconds)]


def _fmt(seconds):
    return f"Sleep {max(round(seconds * 1000), 0)}ms"


def _retime_block(lines, natural, target):
    sleeps = [(i, vidkit._to_seconds(m.group(2), m.group(3))) for i, l in enumerate(lines) if (m := _SLEEP_LINE.match(l))]
    need = target - natural
    if abs(need) <= KEEP_TOLERANCE:
        return list(lines), "keep", 1.0
    out = list(lines)
    if need > 0:
        if sleeps:
            i, value = sleeps[-1]
            out[i] = _fmt(value + need)
        else:
            out.append(_fmt(need))
        return out, "hold", 1.0
    total = sum(v for _, v in sleeps)
    scale = (total + need) / total if total else 0.0
    if scale < MIN_SCALE:
        raise ValueError(natural - total + MIN_SCALE * total)
    for i, value in sleeps:
        out[i] = _fmt(value * scale)
    return out, "shrink", scale


def retime_tape(tape_text, periods):
    """(new_tape_text, [BeatPlan]) with each beat lasting its period. Original text is untouched."""
    preamble, blocks = split_beats(tape_text)
    if len(blocks) != len(periods):
        raise SyncError(f"tape has {len(blocks)} beats but there are {len(periods)} narration segments. "
                        "Each '# @beat' in body.tape needs one '## [..] Title' section in voiceover.md.")
    lines, plans = list(preamble), []
    for n, (block, target) in enumerate(zip(blocks, periods), 1):
        natural = block.seconds
        try:
            new, action, scale = _retime_block(block.lines, natural, target)
        except ValueError as floor:
            raise SyncError(
                f"beat {n} '{block.title}': narration needs {target:.1f}s but the visuals run {natural:.1f}s "
                f"and cannot go below {floor.args[0]:.1f}s without blurring the typing. "
                f"Say at least {floor.args[0]:.1f}s of narration for this section, or shorten its commands "
                "in a copy of body.tape.") from None
        lines += new
        plans.append(BeatPlan(n, block.title, natural, target, action, scale))
    return "\n".join(lines) + "\n", plans
