"""Measure when beats really start in a rendered terminal video, and compare with the narration.

Every beat after the first opens with `clear`; that wipes the screen, which shows up as a sudden fall in
the amount of 'ink' (non-background pixels). We look for that fall near where we expect it.
"""
import subprocess
from dataclasses import dataclass, field

import numpy as np

SIZE = 256
INK_DELTA = 24


def ink_series(video, fps=25):
    """Share of non-background pixels for each frame (sampled at `fps`)."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-vf", f"fps={fps},scale={SIZE}:{SIZE},format=gray",
         "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, SIZE * SIZE)
    if not len(frames):
        return []
    background = np.bincount(frames[0]).argmax()
    return (np.abs(frames.astype(np.int16) - int(background)) > INK_DELTA).mean(axis=1).tolist()


def find_clears(series, fps, expected, window=1.5, min_drop=0.003):
    """For each expected clear time, the time of the biggest single-frame ink drop within ±window (else None)."""
    drops = [series[i - 1] - series[i] for i in range(1, len(series))]
    found = []
    for t in expected:
        lo, hi = max(int((t - window) * fps), 0), min(int((t + window) * fps), len(drops))
        best = max(range(lo, hi), key=lambda i: drops[i], default=None)
        found.append((best + 1) / fps if best is not None and drops[best] >= min_drop else None)
    return found


@dataclass(frozen=True)
class BeatDrift:
    index: int
    title: str
    measured: float
    target: float

    @property
    def drift(self):
        return None if self.measured is None else self.measured - self.target


@dataclass
class DriftReport:
    beats: list
    total: tuple
    problems: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.problems

    def markdown(self):
        rows = ["| beat | title | video starts | narration starts | drift |", "|---|---|---|---|---|"]
        for b in self.beats:
            m = "?" if b.measured is None else f"{b.measured:.2f}s"
            d = "?" if b.drift is None else f"{b.drift:+.2f}s"
            rows.append(f"| {b.index} | {b.title} | {m} | {b.target:.2f}s | {d} |")
        head = "# Sync report\n\n" + ("Within tolerance.\n\n" if self.ok else "**Out of sync.**\n\n")
        problems = "".join(f"- {p}\n" for p in self.problems)
        return head + "\n".join(rows) + f"\n\nVideo length {self.total[0]:.2f}s, expected {self.total[1]:.2f}s.\n\n" + problems


def drift_report(measured, targets, total, beat_tol=0.3, total_tol=0.5, titles=None):
    titles = titles or [f"beat {i}" for i in range(1, len(targets) + 1)]
    beats = [BeatDrift(i, titles[i - 1], m, t) for i, (m, t) in enumerate(zip(measured, targets), 1)]
    problems = []
    for b in beats:
        if b.measured is None:
            problems.append(f"beat {b.index} '{b.title}': could not find the screen clear near {b.target:.2f}s. "
                            "The render may be broken or the beat does not start with `clear`.")
        elif abs(b.drift) > beat_tol:
            side = "late" if b.drift > 0 else "early"
            problems.append(f"beat {b.index} '{b.title}': video starts {b.measured:.2f}s but narration starts "
                            f"{b.target:.2f}s ({abs(b.drift):.2f}s {side}, tolerance {beat_tol}s)")
    if abs(total[0] - total[1]) > total_tol:
        problems.append(f"overall: video is {total[0]:.2f}s but narration plus tail is {total[1]:.2f}s "
                        f"(tolerance {total_tol}s)")
    return DriftReport(beats, total, problems)


def corrected_periods(periods, measured, total_end):
    """Ask for each beat's period minus the error seen in the last render (None = unmeasured, left alone)."""
    ends = list(measured[1:]) + [total_end]
    out = []
    for period, start, end in zip(periods, measured, ends):
        out.append(period if start is None or end is None else period - ((end - start) - period))
    return out
