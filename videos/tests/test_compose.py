import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import compose  # noqa: E402


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def info(path):
    streams = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout)
    return streams


@pytest.fixture(scope="session")
def intro(tmp_path_factory):
    """Stand-in for the supplied brand clip: 1920x1080, H.264, 30 fps, 5.0 s, NO audio stream."""
    path = tmp_path_factory.mktemp("brand") / "intro.mp4"
    ff("-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=5", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path))
    return path


def lesson(path, seconds=10, size="1080x1920", fps=25):
    """Synthetic silent terminal render plus narration-length tone, like a VHS raw."""
    ff("-f", "lavfi", "-i", f"color=c=0x282a36:s={size}:r={fps}:d={seconds}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path))
    return path


def tone(path, seconds):
    ff("-f", "lavfi", "-i", f"sine=f=330:d={seconds}", "-ac", "1", "-ar", "48000", str(path))
    return path


class TestPlacementDefaults:
    def test_vertical_defaults_to_outro(self):
        assert compose.default_placement("vertical") == "outro"

    def test_horizontal_defaults_to_after_hook(self):
        assert compose.default_placement("horizontal") == "after-hook"

    def test_unknown_placement_rejected(self):
        with pytest.raises(ValueError):
            compose.check_placement("middle")

    @pytest.mark.parametrize("p,expected", [("outro", ["end"]), ("after-hook", ["hook"]), ("none", []),
                                            ("both", ["hook", "end"])])
    def test_slots(self, p, expected):
        assert compose.brand_slots(p) == expected


class TestBrandClip:
    def test_vertical_is_1080x1920_with_full_logo_contained_and_silent_audio(self, intro, tmp_path):
        out = compose.brand_clip(intro, tmp_path / "b.mp4", "vertical")
        streams = {s["codec_type"]: s for s in info(out)["streams"]}
        assert (streams["video"]["width"], streams["video"]["height"]) == (1080, 1920)
        assert streams["video"]["pix_fmt"] == "yuv420p" and streams["video"]["r_frame_rate"] == "30/1"
        assert streams["audio"]["sample_rate"] == "48000" and streams["audio"]["channels"] == 2
        assert float(info(out)["format"]["duration"]) == pytest.approx(5.0, abs=0.1)

    def test_vertical_does_not_crop_or_stretch(self, intro, tmp_path):
        """The 16:9 source is shown whole: its centre column of pixels sits in the middle of the 9:16 frame."""
        out = compose.brand_clip(intro, tmp_path / "b.mp4", "vertical")
        frame = tmp_path / "f.png"
        ff("-ss", "1", "-i", str(out), "-frames:v", "1", str(frame))
        from_src = tmp_path / "src.png"
        ff("-ss", "1", "-i", str(intro), "-frames:v", "1", "-vf", "scale=1080:608", str(from_src))
        crop = tmp_path / "crop.png"
        ff("-i", str(frame), "-vf", "crop=1080:608:0:656", str(crop))
        ssim = subprocess.run(["ffmpeg", "-i", str(crop), "-i", str(from_src), "-lavfi", "ssim", "-f", "null", "-"],
                              capture_output=True, text=True).stderr
        score = float(ssim.split("All:")[1].split()[0])
        assert score > 0.9, ssim

    def test_horizontal_is_1920x1080(self, intro, tmp_path):
        out = compose.brand_clip(intro, tmp_path / "b.mp4", "horizontal")
        v = [s for s in info(out)["streams"] if s["codec_type"] == "video"][0]
        assert (v["width"], v["height"]) == (1920, 1080)

    def test_source_with_audio_is_kept_silent_consistent(self, intro, tmp_path):
        with_audio = tmp_path / "a.mp4"
        ff("-i", str(intro), "-f", "lavfi", "-i", "sine=f=500:d=5", "-c:v", "copy", "-c:a", "aac", "-shortest", str(with_audio))
        out = compose.brand_clip(with_audio, tmp_path / "b.mp4", "horizontal")
        assert [s["codec_type"] for s in info(out)["streams"]].count("audio") == 1


class TestMaster:
    def test_vertical_master_has_voice_30fps_and_no_captions(self, tmp_path):
        raw, voice = lesson(tmp_path / "raw.mp4", 10), tone(tmp_path / "n.wav", 8)
        out = compose.master(raw, voice, tmp_path / "m.mp4")
        v = [s for s in info(out)["streams"] if s["codec_type"] == "video"][0]
        a = [s for s in info(out)["streams"] if s["codec_type"] == "audio"][0]
        assert v["r_frame_rate"] == "30/1" and v["pix_fmt"] == "yuv420p" and a["channels"] == 2
        assert float(info(out)["format"]["duration"]) == pytest.approx(10.0, abs=0.1)

    def test_video_is_held_when_voice_runs_longer(self, tmp_path):
        raw, voice = lesson(tmp_path / "raw.mp4", 5), tone(tmp_path / "n.wav", 8)
        out = compose.master(raw, voice, tmp_path / "m.mp4", min_seconds=8.5)
        assert float(info(out)["format"]["duration"]) == pytest.approx(8.5, abs=0.15)


def pixel_luma(path, x, y):
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1", "-vf", f"format=gray,crop=1:1:{x}:{y}",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return out[0]


class TestTopSafeZone:
    """Instagram's feed overlays the account name on the top of a Reel, so vertical content must start lower."""

    def bright_top(self, tmp_path):
        raw = tmp_path / "raw.mp4"
        ff("-f", "lavfi", "-i", "color=c=0x282a36:s=1080x1920:r=25:d=4", "-vf", "drawbox=x=0:y=0:w=1080:h=120:color=white:t=fill",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", str(raw))
        return raw

    def test_top_band_is_cleared_and_content_pushed_down(self, tmp_path):
        raw, voice = self.bright_top(tmp_path), tone(tmp_path / "n.wav", 3)
        out = compose.master(raw, voice, tmp_path / "m.mp4", top_safe=200)
        assert pixel_luma(out, 540, 100) < 60       # safe zone: background fill, not the bright terminal bar
        assert pixel_luma(out, 540, 230) > 200      # the bright bar now sits below the safe zone
        v = [s for s in info(out)["streams"] if s["codec_type"] == "video"][0]
        assert (v["width"], v["height"]) == (1080, 1920)

    def test_default_leaves_frame_untouched(self, tmp_path):
        raw, voice = self.bright_top(tmp_path), tone(tmp_path / "n.wav", 3)
        out = compose.master(raw, voice, tmp_path / "m.mp4")
        assert pixel_luma(out, 540, 100) > 200


def master_clip(tmp_path, seconds=10, size="1080x1920"):
    return compose.master(lesson(tmp_path / "raw.mp4", seconds, size), tone(tmp_path / "n.wav", seconds - 1), tmp_path / "m.mp4")


def duration(p):
    return float(info(p)["format"]["duration"])


class TestAssemble:
    def test_outro_appends_five_seconds(self, intro, tmp_path):
        m = master_clip(tmp_path)
        b = compose.brand_clip(intro, tmp_path / "b.mp4", "vertical")
        out = compose.assemble(m, b, tmp_path / "f.mp4", "outro", hook_end=3.0)
        assert duration(out) == pytest.approx(10 + 5, abs=0.2)

    def test_after_hook_inserts_brand_after_hook_only(self, intro, tmp_path):
        m = master_clip(tmp_path, size="1920x1080")
        b = compose.brand_clip(intro, tmp_path / "b.mp4", "horizontal")
        out = compose.assemble(m, b, tmp_path / "f.mp4", "after-hook", hook_end=3.0)
        assert duration(out) == pytest.approx(15, abs=0.2)

    def test_both_adds_two_brand_clips(self, intro, tmp_path):
        m = master_clip(tmp_path)
        b = compose.brand_clip(intro, tmp_path / "b.mp4", "vertical")
        assert duration(compose.assemble(m, b, tmp_path / "f.mp4", "both", hook_end=3.0)) == pytest.approx(20, abs=0.3)

    def test_none_keeps_length(self, intro, tmp_path):
        m = master_clip(tmp_path)
        b = compose.brand_clip(intro, tmp_path / "b.mp4", "vertical")
        assert duration(compose.assemble(m, b, tmp_path / "f.mp4", "none", hook_end=3.0)) == pytest.approx(10, abs=0.2)

    def test_audio_stays_in_sync_voice_precedes_outro_silence(self, intro, tmp_path):
        m = master_clip(tmp_path)  # voice 9s then silence to 10s
        b = compose.brand_clip(intro, tmp_path / "b.mp4", "vertical")
        out = compose.assemble(m, b, tmp_path / "f.mp4", "outro", hook_end=3.0)
        log = subprocess.run(["ffmpeg", "-i", str(out), "-af", "silencedetect=n=-50dB:d=0.5", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        starts = [float(x.split()[0]) for x in log.split("silence_start:")[1:]]
        assert starts and starts[0] == pytest.approx(9.0, abs=0.3)  # silence only after the narration

    def test_output_spec(self, intro, tmp_path):
        m = master_clip(tmp_path)
        b = compose.brand_clip(intro, tmp_path / "b.mp4", "vertical")
        out = compose.assemble(m, b, tmp_path / "f.mp4", "outro", hook_end=3.0)
        v = [s for s in info(out)["streams"] if s["codec_type"] == "video"][0]
        assert (v["width"], v["height"], v["pix_fmt"], v["codec_name"]) == (1080, 1920, "yuv420p", "h264")
        assert info(out)["format"]["format_name"].startswith("mov")


class TestLogoOverlay:
    @pytest.fixture
    def logo(self, tmp_path):
        path = tmp_path / "logo.png"
        ff("-f", "lavfi", "-i", "color=c=red:s=400x400", "-frames:v", "1", str(path))
        return path

    def centre_pixel(self, video, at, tmp_path):
        raw = tmp_path / f"px{at}.rgb"
        ff("-ss", str(at), "-i", str(video), "-frames:v", "1", "-vf", "format=rgb24,crop=2:2:iw/2:ih/2", "-f", "rawvideo",
           "-pix_fmt", "rgb24", str(raw))
        return tuple(raw.read_bytes()[:3])

    @pytest.mark.parametrize("size,orient", [("1080x1920", "vertical"), ("1920x1080", "horizontal")])
    def test_logo_shows_at_start_then_clears(self, tmp_path, logo, size, orient):
        m = master_clip(tmp_path, size=size)
        out = compose.overlay_logo(m, logo, tmp_path / "l.mp4", orient, seconds=1.5)
        r, g, b = self.centre_pixel(out, 0.7, tmp_path)
        assert r > 150 and g < 90 and b < 90, "logo should cover the centre early on"
        r, g, b = self.centre_pixel(out, 3, tmp_path)
        assert r < 80 and g < 80 and b < 80, "plain terminal background after the logo"

    def test_length_audio_and_spec_unchanged(self, tmp_path, logo):
        m = master_clip(tmp_path)
        out = compose.overlay_logo(m, logo, tmp_path / "l.mp4", "vertical")
        assert duration(out) == pytest.approx(duration(m), abs=0.1)
        kinds = [s["codec_type"] for s in info(out)["streams"]]
        assert kinds.count("audio") == 1
        v = [s for s in info(out)["streams"] if s["codec_type"] == "video"][0]
        assert (v["width"], v["height"], v["pix_fmt"], v["r_frame_rate"]) == (1080, 1920, "yuv420p", "30/1")


class TestQa:
    def make(self, tmp_path, intro, placement="outro"):
        m = master_clip(tmp_path)
        b = compose.brand_clip(intro, tmp_path / "b.mp4", "vertical")
        return compose.assemble(m, b, tmp_path / "f.mp4", placement, hook_end=3.0)

    def test_good_file_passes(self, tmp_path, intro):
        out = self.make(tmp_path, intro)
        assert compose.qa_problems(out, "vertical", expected_seconds=15, brand_slots=1, brand_seconds=5) == []

    def test_wrong_aspect_flagged(self, tmp_path, intro):
        out = self.make(tmp_path, intro)
        assert any("1920x1080" in p for p in compose.qa_problems(out, "horizontal", 15, 1, 5))

    def test_wrong_duration_flagged_including_double_outro(self, tmp_path, intro):
        out = self.make(tmp_path, intro, "both")  # 20s
        problems = compose.qa_problems(out, "vertical", expected_seconds=15, brand_slots=1, brand_seconds=5)
        assert any("duration" in p for p in problems)

    def test_silent_output_flagged(self, tmp_path):
        silent = tmp_path / "s.mp4"
        ff("-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=30:d=3", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
           "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(silent))
        assert any("silent" in p for p in compose.qa_problems(silent, "vertical", 3, 0, 5))


class TestSidecarShift:
    def test_after_hook_shifts_cues_after_cut(self):
        from vidkit import Cue
        cues = [Cue(0.5, 2.0, "a"), Cue(4.0, 5.0, "b")]
        shifted = compose.shift_cues(cues, "after-hook", hook_end=3.0, brand_seconds=5.0)
        assert [(c.start, c.end) for c in shifted] == [(0.5, 2.0), (9.0, 10.0)]

    def test_outro_does_not_shift(self):
        from vidkit import Cue
        cues = [Cue(4.0, 5.0, "b")]
        assert compose.shift_cues(cues, "outro", 3.0, 5.0) == cues

    def test_both_shifts_like_after_hook(self):
        from vidkit import Cue
        assert compose.shift_cues([Cue(4.0, 5.0, "b")], "both", 3.0, 5.0)[0].start == 9.0
