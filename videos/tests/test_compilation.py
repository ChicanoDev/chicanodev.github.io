import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import approval  # noqa: E402
import compose  # noqa: E402
import pipeline  # noqa: E402
import vidkit  # noqa: E402
from test_compose import intro, lesson, tone  # noqa: E402,F401


def compiled(tmp_path, seconds=30):
    return compose.master(lesson(tmp_path / "raw.mp4", seconds, "1920x1080"), tone(tmp_path / "v.wav", seconds - 1), tmp_path / "c.mp4")


CUES = [vidkit.Cue(1.0, 3.0, "hook"), vidkit.Cue(10.0, 12.0, "later"), vidkit.Cue(25.0, 27.0, "end")]


class TestBrandCompilation:
    def test_after_hook_adds_brand_exactly_once(self, tmp_path, intro):
        out, cues = pipeline.brand_compilation(compiled(tmp_path), CUES, "after-hook", 6.0, intro, tmp_path / "w", tmp_path / "o.mp4")
        assert compose.seconds(out) == pytest.approx(35, abs=0.3)
        assert [c.start for c in cues] == [1.0, 15.0, 30.0]

    def test_outro_adds_brand_at_end_and_keeps_cues(self, tmp_path, intro):
        out, cues = pipeline.brand_compilation(compiled(tmp_path), CUES, "outro", 6.0, intro, tmp_path / "w", tmp_path / "o.mp4")
        assert compose.seconds(out) == pytest.approx(35, abs=0.3)
        assert cues == CUES

    def test_none_leaves_length_alone(self, tmp_path, intro):
        out, cues = pipeline.brand_compilation(compiled(tmp_path), CUES, "none", 6.0, intro, tmp_path / "w", tmp_path / "o.mp4")
        assert compose.seconds(out) == pytest.approx(30, abs=0.3)

    def test_both_would_double_brand_so_it_is_refused_for_compilations(self, tmp_path, intro):
        with pytest.raises(ValueError) as err:
            pipeline.brand_compilation(compiled(tmp_path), CUES, "both", 6.0, intro, tmp_path / "w", tmp_path / "o.mp4")
        assert "once" in str(err.value)


class TestCleanSources:
    """Pipeline-built episodes contribute their brand-free master; anything else is left to the legacy path."""

    def make_built(self, root, eid):
        work = root / "out" / "intermediate" / eid
        work.mkdir(parents=True)
        (work / "horizontal-captioned.mp4").write_bytes(b"clean")
        (work / "horizontal-captions.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nhi\n")
        (work / "timing.json").write_text(json.dumps({"hook_end": 4.5}))
        final = root / "out" / "final" / "horizontal" / f"{eid}.mp4"
        final.parent.mkdir(parents=True)
        final.write_bytes(b"branded")
        approval.record_build(root / "out" / "final", eid, "k", {"horizontal": final}, [])
        return final

    def test_uses_clean_master_when_final_is_the_pipeline_output(self, tmp_path):
        self.make_built(tmp_path, "ep1")
        src = pipeline.clean_source(tmp_path, "ep1")
        assert src.clip.name == "horizontal-captioned.mp4" and src.hook_end == 4.5
        assert "hi" in src.srt.read_text()

    def test_none_when_never_built_by_pipeline(self, tmp_path):
        assert pipeline.clean_source(tmp_path, "ep1") is None

    def test_none_when_final_was_overwritten_by_legacy_mux(self, tmp_path):
        final = self.make_built(tmp_path, "ep1")
        final.write_bytes(b"legacy mux output")
        assert pipeline.clean_source(tmp_path, "ep1") is None
