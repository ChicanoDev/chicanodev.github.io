"""Word-timed transcripts per narration segment, stored as editable YAML next to the episode.

The YAML is the source of truth for captions. Edit a word's `text` to fix terminology; edits survive
rebuilds until the recording itself changes (its `audio_sha`), at which point the old file is kept
as `<segment>.stale.yaml` for reference.
"""
import difflib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

LOW_CONFIDENCE = 0.6


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str
    conf: float = 1.0
    asr: str = ""  # what the recogniser heard; `text` may be user-corrected


@dataclass(frozen=True)
class Transcript:
    segment: str
    audio_sha: str
    words: list

    @property
    def has_edits(self):
        return any(w.asr and w.text != w.asr for w in self.words)


@dataclass(frozen=True)
class Flag:
    kind: str  # low-confidence | differs-from-script
    word: str
    expected: str
    start: float
    index: int


def _path(folder, segment_id, stale=False):
    return Path(folder) / f"{segment_id}{'.stale' if stale else ''}.yaml"


def save(folder, transcript, stale=False):
    path = _path(folder, transcript.segment, stale)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "segment": transcript.segment,
        "audio_sha": transcript.audio_sha,
        "words": [{"text": w.text, "start": float(w.start), "end": float(w.end), "conf": round(float(w.conf), 3), "asr": w.asr or w.text}
                  for w in transcript.words],
    }
    path.write_text("# Edit a word's `text` to correct it. Edits are kept until the recording changes.\n"
                    + yaml.safe_dump(data, sort_keys=False, default_flow_style=None, width=120))
    return path


def load(folder, segment_id):
    data = yaml.safe_load(_path(folder, segment_id).read_text())
    words = [Word(float(w["start"]), float(w["end"]), str(w["text"]), float(w.get("conf", 1.0)), str(w.get("asr", w["text"])))
             for w in data["words"]]
    return Transcript(data["segment"], data["audio_sha"], words)


def exists(folder, segment_id):
    return _path(folder, segment_id).exists()


def ensure(segment, audio_sha, wav, folder, engine, force=False):
    """Transcribe `wav` unless a transcript for this exact recording exists. Returns 'ran' or 'cached'."""
    if exists(folder, segment.id) and not force:
        current = load(folder, segment.id)
        if current.audio_sha == audio_sha:
            return "cached"
        save(folder, current, stale=True)
    heard = engine(wav)
    save(folder, Transcript(segment.id, audio_sha, [Word(w.start, w.end, w.text, w.conf, w.text) for w in heard]))
    return "ran"


def _norm(text):
    return re.sub(r"[^a-z0-9']", "", text.lower())


def review_flags(words, script_text):
    """Things a human should look at: shaky words, and any place the speech differs from the script.

    The script is a spelling reference only; speech is never silently replaced by script text.
    """
    flags = [Flag("low-confidence", w.text, "", w.start, i) for i, w in enumerate(words) if w.conf < LOW_CONFIDENCE]
    spoken = [_norm(w.text) for w in words]
    tokens = [(t, _norm(t)) for t in script_text.split() if _norm(t)]
    shown, expected = [re.sub(r"^\W+|\W+$", "", t) for t, _ in tokens], [n for _, n in tokens]
    for op, a0, a1, b0, b1 in difflib.SequenceMatcher(None, spoken, expected, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        if op == "delete":  # spoken but not in script
            flags += [Flag("differs-from-script", words[i].text, "", words[i].start, i) for i in range(a0, a1)]
        elif op == "insert":  # in script but not spoken
            at = max(a0 - 1, 0)
            at_start = words[at].start if words else 0.0
            flags += [Flag("differs-from-script", "", shown[j], at_start, at) for j in range(b0, b1)]
        else:  # replace
            for k, i in enumerate(range(a0, a1)):
                flags.append(Flag("differs-from-script", words[i].text, shown[b0 + k] if b0 + k < b1 else "",
                                  words[i].start, i))
            for j in range(b0 + (a1 - a0), b1):
                flags.append(Flag("differs-from-script", "", shown[j], words[a1 - 1].start, a1 - 1))
    return sorted(flags, key=lambda f: (f.index, f.kind))


def whisper_engine(model="small.en", device="cpu", compute_type="int8"):
    """Real recogniser (faster-whisper, local, CPU). Returns wav -> [Word]. Imported lazily."""
    from faster_whisper import WhisperModel
    loaded = WhisperModel(model, device=device, compute_type=compute_type)

    def run(wav):
        segments, _ = loaded.transcribe(str(wav), word_timestamps=True, language="en", vad_filter=False,
                                        beam_size=5, condition_on_previous_text=False)
        return [Word(round(float(w.start), 3), round(float(w.end), 3), w.word.strip(), float(w.probability))
                for s in segments for w in s.words if w.word.strip()]

    return run
