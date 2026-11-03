"""Narration recording foundation: WAV output, take files, crash-safe approval, audio backends.

No interactive code here (see studio.py), so everything but `SoundDeviceBackend` runs without hardware.

Files, per episode folder:
    narration/<seg>.wav                  the approved take. The ONLY file the pipeline reads
    narration/takes/<seg>.takeN.wav      every recording, kept (pending, rejected or approved)
    narration/takes/<seg>.prevN.<ext>    older approved audio, archived when a take is replaced
    narration/takes/record-state.json    labels only (rejected takes); rebuilt from the audio if lost

Narration approval lives here and nowhere else. It is independent of `vidkit.py approve`, which
approves the finished video (approval.py).
"""
import hashlib
import json
import os
import re
import shutil
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import narration

OUT_RATE = narration.WORK_RATE  # 48 kHz
SETUP_HINT = "uv pip install --python .venv/bin/python -r requirements.txt  (from videos/)"
MIC_PERMISSION_HINT = ("Allow your terminal app under System Settings > Privacy & Security > Microphone, "
                       "then run the command again.")


class RecorderError(Exception):
    """Something the user can fix; the message says what and what to do next."""


class MicError(RecorderError):
    """No microphone, permission denied, or the device went away."""


class StorageError(RecorderError):
    """A file could not be written (disk full, permissions)."""


# --- thin filesystem hooks (tests inject failures here) -------------------------------------------

def _fsync(path):
    with open(path, "rb") as fh:
        os.fsync(fh.fileno())


def _copy(src, dst):
    shutil.copyfile(src, dst)
    _fsync(dst)


def _replace(src, dst):
    os.replace(src, dst)


def _write_json(path, data):
    tmp = Path(path).with_name(Path(path).name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    _fsync(tmp)
    os.replace(tmp, path)


def _write_raw_wav(path, pcm, rate, channels):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes(pcm.tobytes())


# --- audio files ----------------------------------------------------------------------------------

def _to_int16(samples):
    arr = np.asarray(samples)
    if arr.dtype == np.int16:
        return arr
    return np.rint(np.clip(arr.astype(np.float32), -1.0, 1.0) * 32767).astype(np.int16)


def to_wav(samples, rate, dst):
    """Write captured audio as 48 kHz mono signed 16-bit PCM WAV, atomically.

    `samples` is float (-1..1) or int16, shape (frames,) or (frames, channels), at `rate` Hz.
    FFmpeg does the downmix and resampling. A failure never leaves a partial file or damages `dst`.
    """
    dst = Path(dst)
    raw = dst.with_name(f".{dst.name}.raw.wav")
    tmp = dst.with_name(f".{dst.name}.tmp.wav")
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        pcm = _to_int16(samples)
        channels = pcm.shape[1] if pcm.ndim == 2 else 1
        _write_raw_wav(raw, pcm.reshape(-1), rate, channels)
        narration._ffmpeg("-y", "-i", str(raw), "-ac", "1", "-ar", str(OUT_RATE), "-c:a", "pcm_s16le", str(tmp))
        _fsync(tmp)
        _replace(tmp, dst)
    except FileNotFoundError as err:
        if err.filename in (None, "ffmpeg") or "ffmpeg" in str(err):
            raise RecorderError("ffmpeg not found. Install it with: brew install ffmpeg") from err
        raise StorageError(f"could not write {dst.name}: {err.strerror or err}") from err
    except OSError as err:
        reason = "the disk is full" if err.errno == 28 else (err.strerror or str(err))
        raise StorageError(f"could not save {dst.name}: {reason}. Free some space and record again.") from err
    except narration.BadAudio as err:
        raise RecorderError(f"could not convert the recording to WAV ({err})") from err
    finally:
        for leftover in (raw, tmp):
            leftover.unlink(missing_ok=True)
    return dst


def check_wav_format(path):
    """Raise RecorderError unless `path` is 48 kHz mono 16-bit PCM with audio in it."""
    try:
        with wave.open(str(path), "rb") as w:
            got = (w.getnchannels(), w.getframerate(), w.getsampwidth(), w.getnframes())
    except (wave.Error, EOFError, OSError) as err:
        raise RecorderError(f"{Path(path).name} is not a readable WAV file ({err})") from err
    if got[:3] != (1, OUT_RATE, 2) or got[3] == 0:
        raise RecorderError(f"{Path(path).name}: expected {OUT_RATE} Hz mono 16-bit PCM with audio, "
                            f"got {got[1]} Hz, {got[0]} ch, {got[2] * 8}-bit, {got[3]} frames")


def read_wav(path):
    """(float32 mono samples, rate) of a take, for playback."""
    with wave.open(str(path), "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        return data.astype(np.float32) / 32768.0, w.getframerate()


# --- takes and approval ---------------------------------------------------------------------------

_TAKE = re.compile(r"^(?P<seg>.+)\.take(?P<n>\d+)\.wav$")


def take_number(path):
    m = _TAKE.match(Path(path).name)
    return int(m["n"]) if m else 0


class TakeStore:
    """Takes and approval for one episode folder."""

    def __init__(self, folder, selected=None):
        self.folder = Path(folder)
        self.dir = self.folder / "narration"
        self.takes_dir = self.dir / "takes"
        self.manifest_path = self.takes_dir / "record-state.json"
        self.selected = dict(selected or {})
        self.warnings = []
        self._segments = self._load()

    # state labels (never the source of truth for audio)
    def _load(self):
        if not self.manifest_path.exists():
            return {}
        try:
            data = json.loads(self.manifest_path.read_text())
            segments = data["segments"]
            if not isinstance(segments, dict):
                raise ValueError("segments is not a mapping")
            return segments
        except (ValueError, KeyError, OSError):
            aside = self.manifest_path.with_name("record-state.corrupt.json")
            try:
                os.replace(self.manifest_path, aside)  # keep it for inspection, never delete
            except OSError:
                pass
            self.warnings.append("record-state.json was unreadable and was rebuilt from the audio files")
            self._save()
            return {}

    def _save(self):
        try:
            self.takes_dir.mkdir(parents=True, exist_ok=True)
            _write_json(self.manifest_path, {"version": 1, "segments": getattr(self, "_segments", {})})
        except OSError as err:
            self.warnings.append(f"could not update record-state.json ({err.strerror or err}); audio is safe")

    def _entry(self, seg):
        return self._segments.setdefault(seg, {})

    # files
    def canonical_files(self, seg):
        if not self.dir.exists():
            return []
        return sorted(p for p in self.dir.iterdir()
                      if p.is_file() and p.suffix.lower() in narration.AUDIO_EXTENSIONS and p.name.startswith(seg + "."))

    def canonical(self, seg):
        return narration.resolve_take(self.dir, seg, self.selected)

    def takes(self, seg):
        if not self.takes_dir.exists():
            return []
        found = [p for p in self.takes_dir.iterdir() if (m := _TAKE.match(p.name)) and m["seg"] == seg]
        return sorted(found, key=take_number)

    def next_take_path(self, seg):
        self.takes_dir.mkdir(parents=True, exist_ok=True)
        n = max([take_number(p) for p in self.takes(seg)] + [0]) + 1
        while (self.takes_dir / f"{seg}.take{n}.wav").exists():
            n += 1
        return self.takes_dir / f"{seg}.take{n}.wav"

    def approved_take(self, seg):
        """Name of the take whose audio is the approved file (None for a hand-made file or nothing)."""
        try:
            canonical = self.canonical(seg)
        except narration.AmbiguousTake:
            return None
        if canonical is None:
            return None
        sha = narration.file_sha(canonical)
        for take in reversed(self.takes(seg)):
            if narration.file_sha(take) == sha:
                return take.name
        return None

    def pending(self, seg):
        """Latest recording that was neither approved, rejected, nor superseded by an approval."""
        rejected = set(self._segments.get(seg, {}).get("rejected", []))
        candidates = [t for t in self.takes(seg) if t.name not in rejected]
        name = self.approved_take(seg)
        if name:
            candidates = [t for t in candidates if take_number(t) > take_number(self.takes_dir / name)]
        else:
            try:
                canonical = self.canonical(seg)
            except narration.AmbiguousTake:
                canonical = None
            if canonical:
                candidates = [t for t in candidates if t.stat().st_mtime > canonical.stat().st_mtime]
        return candidates[-1] if candidates else None

    def status(self, seg):
        """'approved', 'pending' (recorded, awaiting your decision), 'missing', or 'conflict'."""
        try:
            if self.canonical(seg):
                return "approved"
        except narration.AmbiguousTake:
            return "conflict"
        return "pending" if self.pending(seg) else "missing"

    def reject(self, seg, take):
        names = self._entry(seg).setdefault("rejected", [])
        if Path(take).name not in names:
            names.append(Path(take).name)
        self._save()

    # approval
    def approve(self, seg, take):
        """Make `take` the approved recording for `seg`. A failure at any step leaves the old one intact.

        Order: stage + validate the new file, archive the old one (copy), swap in the new one
        (one atomic rename), drop superseded duplicates, then label the manifest.
        """
        if seg in self.selected:
            raise RecorderError(f"alignment.yaml pins {seg} to {self.selected[seg]} under `selected:`. "
                                "Remove that entry so recorded takes are used.")
        take = Path(take)
        check_wav_format(take)
        final = self.dir / f"{seg}.wav"
        staged = self.dir / f".{seg}.staged.wav"
        olds = self.canonical_files(seg)
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            _copy(take, staged)
            check_wav_format(staged)
            self._archive(seg, olds)
            _replace(staged, final)
        except OSError as err:
            raise StorageError(f"could not approve {take.name}: {err.strerror or err}. "
                               f"The previous recording is unchanged.") from err
        finally:
            staged.unlink(missing_ok=True)
        for old in olds:
            if old != final:
                try:
                    old.unlink()
                except OSError as err:
                    raise StorageError(f"approved, but could not remove old {old.name} ({err.strerror or err}). "
                                       f"It is archived in narration/takes/. Delete {old} by hand.") from err
        entry = self._entry(seg)
        entry["approved"] = take.name
        entry["approved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rejected = entry.setdefault("rejected", [])
        rejected += [t.name for t in self.takes(seg) if take_number(t) > take_number(take) and t.name not in rejected]
        self._save()

    def _archive(self, seg, olds):
        """Copy audio about to be replaced into takes/, unless an identical copy is already there."""
        if not olds:
            return
        self.takes_dir.mkdir(parents=True, exist_ok=True)
        kept = {narration.file_sha(p) for p in self.takes_dir.glob(f"{seg}.*") if p.is_file()}
        for old in olds:
            if narration.file_sha(old) in kept:
                continue
            n = 1
            while (dst := self.takes_dir / f"{seg}.prev{n}{old.suffix}").exists():
                n += 1
            _copy(old, dst)

    def recover(self):
        """Tidy after a crash without ever deleting the only copy of anything."""
        if not self.dir.exists():
            return
        for staged in self.dir.glob(".*.staged.wav"):
            seg = staged.name[1:-len(".staged.wav")]
            if any(p.stat().st_size > 0 for p in self.canonical_files(seg)):
                staged.unlink(missing_ok=True)  # the approved file is intact; this was an unfinished swap
        segs = {p.name.split(".")[0] for p in self.dir.iterdir() if p.is_file() and not p.name.startswith(".")}
        for seg in segs:
            files = self.canonical_files(seg)
            final = self.dir / f"{seg}.wav"
            if len(files) < 2 or final not in files:
                continue
            archived = {narration.file_sha(p) for p in self.takes_dir.glob(f"{seg}.prev*") if p.is_file()}
            for extra in files:
                if extra != final and narration.file_sha(extra) in archived:
                    extra.unlink(missing_ok=True)  # swap finished but old file was not yet removed


# --- audio devices --------------------------------------------------------------------------------

@dataclass(frozen=True)
class Device:
    id: int
    name: str
    rate: float
    default: bool = False


class SoundDeviceBackend:
    """Microphone capture and playback through sounddevice (PortAudio). Needs real hardware."""

    def __init__(self):
        self._sd = None

    def _lib(self):
        if self._sd is None:
            try:
                import sounddevice
            except (ImportError, OSError) as err:
                raise MicError(f"The audio library (sounddevice) is not installed. Run: {SETUP_HINT}") from err
            self._sd = sounddevice
        return self._sd

    def list_devices(self):
        sd = self._lib()
        try:
            default = sd.default.device[0]
            return [Device(i, d["name"], d["default_samplerate"], i == default)
                    for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
        except Exception as err:  # PortAudioError and friends
            raise MicError(f"Could not list audio devices ({err}).") from err

    def resolve(self, spec=None):
        """The Device to record from: the system default, or `spec` as an id or part of a name."""
        devices = self.list_devices()
        if not devices:
            raise MicError("No microphone found. Plug one in or check System Settings > Sound > Input.")
        if spec is None:
            default = next((d for d in devices if d.default), None)
            if default is None:
                raise MicError("No default input device. Pick one with --device (see --list-devices).")
            return default
        by_id = [d for d in devices if str(d.id) == str(spec)]
        by_name = [d for d in devices if str(spec).lower() in d.name.lower()]
        match = by_id or by_name
        if len(match) != 1:
            why = "matches several microphones" if match else "is not a microphone"
            names = "; ".join(f"{d.id}: {d.name}" for d in devices)
            raise MicError(f"--device {spec!r} {why}. Available: {names}")
        return match[0]

    def start(self, device):
        return _SdCapture(self._lib(), device)

    def play(self, path):
        sd = self._lib()
        try:
            samples, rate = read_wav(path)
            sd.play(samples, rate)
        except Exception as err:
            raise RecorderError(f"Playback failed ({err}). Check your output device.") from err

    def stop_playback(self):
        try:
            self._lib().stop()
        except Exception:
            pass


class _SdCapture:
    """An open input stream. Opening starts it, so nothing at the start of a take is lost."""

    def __init__(self, sd, device):
        self._frames, self.error, self.rate = [], None, int(device.rate)
        try:
            self._stream = sd.InputStream(device=device.id, channels=1, samplerate=device.rate,
                                          dtype="float32", callback=self._callback)
            self._stream.start()
        except Exception as err:
            raise MicError(f"Could not open {device.name} ({err}). {MIC_PERMISSION_HINT}") from err

    def _callback(self, indata, frames, time, status):
        self._frames.append(indata.copy())

    @property
    def elapsed(self):
        return sum(len(f) for f in list(self._frames)) / self.rate

    def stop(self):
        """(samples, rate). `error` is set when the device stopped by itself (unplugged)."""
        try:
            if not self._stream.active:
                self.error = "The microphone stopped during recording (unplugged or asleep?)."
            self._stream.stop()
            self._stream.close()
        except Exception as err:
            self.error = self.error or f"The microphone reported an error ({err})."
        samples = np.concatenate(self._frames)[:, 0] if self._frames else np.zeros(0, dtype=np.float32)
        return samples, self.rate
