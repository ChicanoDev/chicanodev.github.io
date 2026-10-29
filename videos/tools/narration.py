"""Segment-based narration: stable segment IDs, take selection, audio checks and ingest."""
import re
from dataclasses import dataclass
from pathlib import Path

import vidkit

AUDIO_EXTENSIONS = (".m4a", ".wav", ".mp3")


class AmbiguousTake(Exception):
    """More than one take (or a bad selection) for a segment; the user must choose."""


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
