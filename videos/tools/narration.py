"""Segment-based narration: stable segment IDs, take selection, audio checks and ingest."""
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import vidkit

AUDIO_EXTENSIONS = (".m4a", ".wav", ".mp3")
WORK_RATE = 48000
SILENCE_DB = -45
MIN_SECONDS, MAX_SECONDS = 1.0, 40.0
CLIP_DB, QUIET_DB, MAX_SILENCE_RATIO = -0.5, -30.0, 0.5


class AmbiguousTake(Exception):
    """More than one take (or a bad selection) for a segment; the user must choose."""


class BadAudio(Exception):
    """ffmpeg could not read the file."""


@dataclass(frozen=True)
class AudioStats:
    duration: float
    channels: int
    peak_db: float
    silence_ratio: float


@dataclass(frozen=True)
class Segment:
    index: int
    id: str
    title: str
    text: str


def slugify(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def segments_from_voiceover(md_text, ids=None):
    """One segment per timed voiceover heading. `ids` maps a beat title to an explicit slug."""
    ids = ids or {}
    return [
        Segment(n, f"{n:02}-{ids.get(beat.title) or slugify(beat.title)}", beat.title, beat.text)
        for n, beat in enumerate(vidkit.parse_voiceover(md_text), 1)
    ]


def resolve_take(narration_dir, segment_id, selected):
    """The one audio file for a segment, or None. Several takes need an explicit `selected` entry."""
    narration_dir = Path(narration_dir)
    found = sorted(
        p for p in narration_dir.iterdir()
        if p.suffix.lower() in AUDIO_EXTENSIONS and (p.name.startswith(segment_id + "."))
    ) if narration_dir.exists() else []
    choice = selected.get(segment_id)
    if choice:
        path = narration_dir / choice
        if not path.exists():
            raise AmbiguousTake(f"{segment_id}: selected take {choice} does not exist in {narration_dir}")
        return path
    if len(found) > 1:
        names = ", ".join(p.name for p in found)
        raise AmbiguousTake(
            f"{segment_id}: {len(found)} takes ({names}). Pick one under `selected:` in alignment.yaml "
            f"or move the others out of {narration_dir}.")
    return found[0] if found else None


def _ffmpeg(*args):
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", *args], capture_output=True, text=True)
    if result.returncode:
        raise BadAudio(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "ffmpeg failed")
    return result.stderr


def measure(path):
    """Duration, channels, peak level and silence share of a take."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=channels:format=duration",
         "-of", "json", str(path)], capture_output=True, text=True)
    try:
        info = json.loads(probe.stdout)
        duration, channels = float(info["format"]["duration"]), int(info["streams"][0]["channels"])
    except (ValueError, KeyError, IndexError):
        raise BadAudio(f"{Path(path).name}: not a readable audio file") from None
    log = _ffmpeg("-i", str(path), "-af", f"silencedetect=n={SILENCE_DB}dB:d=0.1,volumedetect", "-f", "null", "-")
    peak = re.search(r"max_volume:\s*(-?[\d.]+) dB", log)
    silent = sum(float(m) for m in re.findall(r"silence_duration:\s*([\d.]+)", log))
    return AudioStats(duration, channels, float(peak.group(1)) if peak else -91.0,
                      min(silent / duration, 1.0) if duration else 1.0)


def audio_problems(stats):
    """Human-fixable problems for one take; empty list means fine."""
    problems = []
    if stats.duration < MIN_SECONDS:
        problems.append(f"only {stats.duration:.1f}s, too short or empty. Re-record the segment")
    if stats.duration > MAX_SECONDS:
        problems.append(f"{stats.duration:.0f}s is long. Make it shorter: split the script section into two segments")
    if stats.peak_db >= CLIP_DB:
        problems.append(f"peaks at {stats.peak_db:.1f} dB, likely clipping. Record further from the mic or lower input gain")
    elif stats.peak_db <= QUIET_DB:
        problems.append(f"very quiet (peak {stats.peak_db:.0f} dB). Check the mic or record closer")
    if stats.silence_ratio > MAX_SILENCE_RATIO:
        problems.append(f"{stats.silence_ratio:.0%} silence. Trim dead air or re-record")
    return problems


def ingest(src, dst, pad=0.12):
    """Working copy: trimmed to `pad` seconds of silence each side, loudness-normalised, 48k mono PCM.

    The original take is only read, never modified.
    """
    trim = (f"silenceremove=start_periods=1:start_threshold={SILENCE_DB}dB:start_silence={pad}:detection=peak")
    chain = ",".join([trim, "areverse", trim, "areverse",
                      "loudnorm=I=-16:TP=-1.5:LRA=11",
                      f"afade=t=in:d=0.01,areverse,afade=t=in:d=0.02,areverse"])
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg("-y", "-i", str(src), "-af", chain, "-ac", "1", "-ar", str(WORK_RATE), "-c:a", "pcm_s16le", str(dst))
    return Path(dst)
