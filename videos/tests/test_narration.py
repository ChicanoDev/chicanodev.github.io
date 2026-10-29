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


class TestAudioProblems:
    def stats(self, **kw):
        base = dict(duration=6.0, channels=1, peak_db=-3.0, silence_ratio=0.1)
        base.update(kw)
        return narration.AudioStats(**base)

    def test_healthy_take_has_no_problems(self):
        assert narration.audio_problems(self.stats()) == []

    def test_too_short_is_empty(self):
        assert any("empty" in p or "short" in p for p in narration.audio_problems(self.stats(duration=0.2)))

    def test_too_long_flags_split(self):
        assert any("split" in p for p in narration.audio_problems(self.stats(duration=60)))

    def test_clipping_flagged(self):
        assert any("clip" in p for p in narration.audio_problems(self.stats(peak_db=0.0)))

    def test_quiet_flagged(self):
        assert any("quiet" in p for p in narration.audio_problems(self.stats(peak_db=-35)))

    def test_mostly_silence_flagged(self):
        assert any("silence" in p for p in narration.audio_problems(self.stats(silence_ratio=0.7)))


def synth(path, seconds, lead=0.0, tail=0.0, freq=440, volume=0.5):
    """Tiny test take: lead silence + sine + tail silence."""
    import subprocess
    filt = (f"sine=f={freq}:d={seconds},volume={volume}[s];"
            f"anullsrc=r=44100:cl=mono,atrim=0:{lead}[a];anullsrc=r=44100:cl=mono,atrim=0:{tail}[b];"
            f"[a][s][b]concat=n=3:v=0:a=1")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-filter_complex", filt, str(path)], check=True)
    return path


class TestMeasure:
    def test_measures_duration_and_channels(self, tmp_path):
        take = synth(tmp_path / "t.wav", 1.0, lead=0.5, tail=0.5)
        s = narration.measure(take)
        assert s.duration == pytest.approx(2.0, abs=0.05)
        assert s.channels == 1
        assert s.silence_ratio == pytest.approx(0.5, abs=0.1)
        # ffmpeg's sine source peaks near -18 dB; volume=0.5 takes another -6 dB.
        assert -26 < s.peak_db < -22

    def test_corrupt_file_raises_readable_error(self, tmp_path):
        bad = tmp_path / "bad.m4a"
        bad.write_bytes(b"not audio")
        with pytest.raises(narration.BadAudio):
            narration.measure(bad)


class TestIngest:
    def test_trims_silence_but_keeps_padding(self, tmp_path):
        take = synth(tmp_path / "t.wav", 1.0, lead=0.8, tail=0.8)
        out = narration.ingest(take, tmp_path / "out.wav", pad=0.1)
        assert narration.measure(out).duration == pytest.approx(1.2, abs=0.15)

    def test_output_is_48k_mono_pcm(self, tmp_path):
        import json, subprocess
        take = synth(tmp_path / "t.wav", 1.0)
        out = narration.ingest(take, tmp_path / "out.wav")
        info = json.loads(subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(out)],
            capture_output=True, text=True, check=True).stdout)["streams"][0]
        assert (info["sample_rate"], info["channels"], info["codec_name"]) == ("48000", 1, "pcm_s16le")

    def test_original_untouched(self, tmp_path):
        take = synth(tmp_path / "t.wav", 1.0, lead=0.5)
        before = take.read_bytes()
        narration.ingest(take, tmp_path / "out.wav")
        assert take.read_bytes() == before
