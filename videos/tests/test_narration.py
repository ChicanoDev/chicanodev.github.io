import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import narration  # noqa: E402
import vidkit  # noqa: E402

VOICEOVER = """# Title

> On screen: stuff

## [0:00-0:05] Hook
Linux has no C drive.

## [0:05-0:17] Root home
That slash is root.

## [0:17-0:29] Etc / config!
Config lives here.

## Post copy
**YouTube title:** x
"""


class TestSegments:
    def test_ids_are_ordered_slugs(self):
        segs = narration.segments_from_voiceover(VOICEOVER)
        assert [s.id for s in segs] == ["01-hook", "02-root-home", "03-etc-config"]

    def test_text_comes_from_beat(self):
        segs = narration.segments_from_voiceover(VOICEOVER)
        assert segs[1].text == "That slash is root."

    def test_post_copy_is_not_a_segment(self):
        assert len(narration.segments_from_voiceover(VOICEOVER)) == 3

    def test_explicit_manifest_ids_override_slugs(self):
        segs = narration.segments_from_voiceover(VOICEOVER, ids={"Root home": "root"})
        assert segs[1].id == "02-root"


class TestTakes:
    def make(self, tmp_path, *names):
        for n in names:
            (tmp_path / n).write_bytes(b"x")
        return tmp_path

    def test_single_take_resolves(self, tmp_path):
        d = self.make(tmp_path, "01-hook.m4a")
        assert narration.resolve_take(d, "01-hook", {}) == d / "01-hook.m4a"

    def test_missing_returns_none(self, tmp_path):
        assert narration.resolve_take(tmp_path, "01-hook", {}) is None

    def test_multiple_takes_without_selection_is_an_error(self, tmp_path):
        d = self.make(tmp_path, "01-hook.m4a", "01-hook.take2.wav")
        with pytest.raises(narration.AmbiguousTake) as err:
            narration.resolve_take(d, "01-hook", {})
        assert "selected" in str(err.value)

    def test_selection_picks_named_file(self, tmp_path):
        d = self.make(tmp_path, "01-hook.m4a", "01-hook.take2.wav")
        assert narration.resolve_take(d, "01-hook", {"01-hook": "01-hook.take2.wav"}) == d / "01-hook.take2.wav"

    def test_selection_of_missing_file_is_an_error(self, tmp_path):
        d = self.make(tmp_path, "01-hook.m4a")
        with pytest.raises(narration.AmbiguousTake):
            narration.resolve_take(d, "01-hook", {"01-hook": "nope.wav"})

    def test_other_segment_files_are_ignored(self, tmp_path):
        d = self.make(tmp_path, "01-hook.m4a", "02-root.m4a", "01-hooky.m4a")
        assert narration.resolve_take(d, "01-hook", {}) == d / "01-hook.m4a"

    def test_unsupported_extension_ignored(self, tmp_path):
        d = self.make(tmp_path, "01-hook.txt")
        assert narration.resolve_take(d, "01-hook", {}) is None
