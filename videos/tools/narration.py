"""Segment-based narration: stable segment IDs, take selection, audio checks and ingest."""
import hashlib
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


class MissingTakes(Exception):
    """One or more segments have no recording yet."""


@dataclass(frozen=True)
class SegmentAudio:
    segment: Segment
    take: Path
    wav: Path
    duration: float
    status: str  # "ran" or "cached"
    audio_sha: str


def file_sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_key(*parts):
    """Stable key from file contents (Path parts) and plain values (everything else)."""
    digest = hashlib.sha256()
    for part in parts:
        digest.update((file_sha(part) if isinstance(part, Path) else str(part)).encode())
        digest.update(b"\0")
    return digest.hexdigest()


def run_stage(out, key, work, force=False):
    """Run `work()` unless `out` exists and was built from the same `key`. Returns 'ran' or 'cached'."""
    out = Path(out)
    stamp = out.with_name(out.name + ".key")
    if not force and out.exists() and stamp.exists() and stamp.read_text() == key:
        return "cached"
    work()
    stamp.write_text(key)
    return "ran"


def timeline(durations, pause):
    """[(start, end)] for clips joined with `pause` seconds between them."""
    spans, cursor = [], 0.0
    for d in durations:
        spans.append((round(cursor, 6), round(cursor + d, 6)))
        cursor += d + pause
    return spans


def duration_of(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        raise BadAudio(f"{Path(path).name}: not a readable audio file") from None


def prepare(segments, narration_dir, work_dir, selected, pad=0.12, force=False):
    """Ingest each segment's take. Only segments whose take (or settings) changed are reprocessed."""
    work_dir = Path(work_dir)
    takes = {s.id: resolve_take(narration_dir, s.id, selected) for s in segments}
    missing = [f"{s.id}.m4a" for s in segments if takes[s.id] is None]
    if missing:
        raise MissingTakes("missing narration: " + ", ".join(missing) + f" (in {narration_dir})")
    report = []
    for s in segments:
        take, wav = takes[s.id], work_dir / f"{s.id}.wav"
        sha = file_sha(take)
        status = run_stage(wav, cache_key(sha, pad, WORK_RATE, SILENCE_DB, "ingest-v1"),
                           lambda take=take, wav=wav: ingest(take, wav, pad), force)
        report.append(SegmentAudio(s, take, wav, duration_of(wav), status, sha))
    return report


def stitch(report, dst, pause=0.3, force=False):
    """Join prepared segments in script order with a natural pause between them."""
    wavs = [r.wav for r in report]
    key = cache_key(pause, "stitch-v1", *(r.audio_sha for r in report))

    def work():
        args = []
        for w in wavs:
            args += ["-i", str(w)]
        pads = [f"[{i}:a]apad=pad_dur={pause}[p{i}]" if i < len(wavs) - 1 else f"[{i}:a]anull[p{i}]"
                for i in range(len(wavs))]
        joined = "".join(f"[p{i}]" for i in range(len(wavs)))
        filt = ";".join(pads) + f";{joined}concat=n={len(wavs)}:v=0:a=1[out]"
        _ffmpeg("-y", *args, "-filter_complex", filt, "-map", "[out]", "-c:a", "pcm_s16le", str(dst))

    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    run_stage(Path(dst), key, work, force)
    return Path(dst)


def load_alignment(folder):
    """alignment.yaml as a dict ({} when absent). Keys used so far: `selected`, `ids`."""
    import yaml
    path = Path(folder) / "alignment.yaml"
    return (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}


def episode_segments(folder):
    folder = Path(folder)
    ids = load_alignment(folder).get("ids") or {}
    return segments_from_voiceover((folder / "voiceover.md").read_text(), ids)
