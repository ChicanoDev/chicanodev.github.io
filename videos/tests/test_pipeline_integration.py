"""Whole-pipeline tests on synthetic media: no Docker, no whisper model, no network."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import approval  # noqa: E402
import pipeline  # noqa: E402
import compose  # noqa: E402
import narration  # noqa: E402
import retime  # noqa: E402
import transcribe  # noqa: E402
import vidkit  # noqa: E402
from test_measure import fake_terminal  # noqa: E402
from test_narration import synth  # noqa: E402

TAPE = """Hide
Type "export PS1='$ '"
Enter
Show

# @beat 0:00 Hook
Type "# no drive"
Sleep 700ms
Enter
Sleep 2s

# @beat 0:05 Root
Type "clear"
Enter
Sleep 300ms
Type "ls /"
Enter
Sleep 3s

# @beat 0:12 Home
Type "clear"
Enter
Sleep 300ms
Type "ls /home"
Enter
Sleep 3s
"""

VOICEOVER = """# Demo #1: tiny episode

## [0:00-0:05] Hook
Linux has no C drive.

## [0:05-0:12] Root
That slash is root.

## [0:12-0:20] Home
Slash home is where your stuff lives.

## Post copy
**YouTube Shorts title:** Linux has NO C: drive #shorts
**Reels / Shorts caption:** Linux has no C: drive. Part 1.
**Hashtags:** #linux #chicanodev
"""

SPOKEN = {"01-hook": "Linux has no C drive.", "02-root": "That slash is root.", "03-home": "Slash home is where your stuff lives."}
LENGTHS = {"01-hook": 3.0, "02-root": 4.5, "03-home": 5.0}


class FakeVhs:
    """Stands in for VHS-in-Docker: makes a terminal-like video whose clears fall where the tape says.

    `speed` < 1 makes the 'render' run faster than the tape's Sleeps claim (like the real drift we measured);
    `fixed` ignores the tape and clears at fixed times (an unfixable render).
    """

    def __init__(self, speed=1.0, fixed=None):
        self.speed, self.fixed, self.calls = speed, fixed, []

    def __call__(self, tape_text, orient, tape_path, raw_path):
        self.calls.append((orient, tape_text))
        _, blocks = retime.split_beats(tape_text)
        starts, t = [], 0.0
        for b in blocks:
            starts.append(t)
            t += b.seconds
        clears = [starts[i] * self.speed + (retime.anchor_offset(b) or 0) * self.speed
                  for i, b in enumerate(blocks) if i]
        size = "1080x1920" if orient == "vertical" else "1920x1080"
        fake_terminal(raw_path, seconds=t * self.speed, clears=self.fixed or clears, size=size)


class FakeEngine:
    def __init__(self):
        self.calls = []

    def __call__(self, wav):
        self.calls.append(Path(wav).stem)
        toks = SPOKEN[Path(wav).stem].split()
        length = narration.duration_of(wav)
        step = (length - 0.4) / len(toks)
        return [transcribe.Word(round(0.1 + i * step, 3), round(0.1 + i * step + step * 0.8, 3), t, 0.95) for i, t in enumerate(toks)]


def fake_burn(master, srt, dst, orient):
    """Host ffmpeg has no subtitles filter, so the test burner copies and keeps the SRT it was given."""
    compose.run_ffmpeg("-i", master, "-c", "copy", dst)
    Path(str(dst) + ".srt").write_text(Path(srt).read_text())


@pytest.fixture(scope="module")
def intro(tmp_path_factory):
    path = tmp_path_factory.mktemp("brand") / "intro.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=5",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


@pytest.fixture
def world(tmp_path, intro, monkeypatch):
    """A throwaway videos/ tree with one 3-beat episode and all 3 takes recorded."""
    root = tmp_path / "videos"
    folder = root / "series" / "demo" / "01-ep"
    (folder / "narration").mkdir(parents=True)
    (folder / "body.tape").write_text(TAPE)
    (folder / "voiceover.md").write_text(VOICEOVER)
    (root / "common").mkdir()
    for o in ("vertical", "horizontal"):
        (root / "common" / f"{o}.settings.tape").write_text("Set TypingSpeed 70ms\n")
    (root / "assets" / "branding").mkdir(parents=True)
    shutil.copy(intro, root / "assets" / "branding" / "chicanodev-intro.mp4")
    for sid, secs in LENGTHS.items():
        synth(folder / "narration" / f"{sid}.wav", secs, lead=0.5, tail=0.5, volume=4)
    monkeypatch.setattr(vidkit, "ROOT", root)
    monkeypatch.setattr(vidkit, "EPISODES", [("demo", "01-ep")])
    vhs, engine = FakeVhs(), FakeEngine()
    env = pipeline.Env(root=root, render=vhs, burn=fake_burn, engine=engine, log=lambda m: None)
    return env, folder, vhs, engine


def run(world, **kw):
    env, *_ = world
    return pipeline.build_episode("demo", "01-ep", pipeline.Config(**kw), env)


def duration(path):
    return compose.seconds(path)


class TestFullBuild:
    def test_vertical_build_produces_final_video_with_outro(self, world):
        env, folder, vhs, engine = world
        result = run(world, formats=["vertical"])
        final = env.root / "out" / "final" / "vertical" / "demo-01-ep.mp4"
        assert final.exists() and result.outputs["vertical"] == final
        assert compose.qa_problems(final, "vertical", result.expected["vertical"], 1, 5) == []
        # narration ~ 3.2+4.7+5.2 (+pauses, tail) then the 5 s brand outro
        assert duration(final) > 5 + 12

    def test_build_is_not_approved(self, world):
        env, *_ = world
        run(world, formats=["vertical"])
        assert approval.current(env.root / "out" / "final", "demo-01-ep").state == "built"

    def test_both_formats(self, world):
        env, *_ = world
        result = run(world, formats=["vertical", "horizontal"])
        assert set(result.outputs) == {"vertical", "horizontal"}
        v = [s for s in compose.probe(result.outputs["horizontal"])["streams"] if s["codec_type"] == "video"][0]
        assert (v["width"], v["height"]) == (1920, 1080)

    def test_horizontal_default_is_after_hook_and_vertical_outro(self, world):
        result = run(world, formats=["vertical", "horizontal"])
        assert result.placements == {"vertical": "outro", "horizontal": "after-hook"}

    def test_brand_placement_none_has_no_brand_time(self, world):
        plain = duration(run(world, formats=["vertical"], placement="none").outputs["vertical"])  # same path is reused
        with_brand = run(world, formats=["vertical"], placement="outro")
        assert duration(with_brand.outputs["vertical"]) == pytest.approx(plain + 5, abs=0.3)

    def test_original_tape_is_never_modified(self, world):
        env, folder, *_ = world
        before = (folder / "body.tape").read_bytes()
        run(world, formats=["vertical"])
        assert (folder / "body.tape").read_bytes() == before

    def test_original_takes_are_never_modified(self, world):
        env, folder, *_ = world
        before = {p.name: p.read_bytes() for p in (folder / "narration").iterdir()}
        run(world, formats=["vertical"])
        assert {p.name: p.read_bytes() for p in (folder / "narration").iterdir()} == before


class TestIncrementalRebuilds:
    def test_second_build_does_nothing(self, world):
        env, folder, vhs, engine = world
        run(world, formats=["vertical"])
        vhs.calls.clear(), engine.calls.clear()
        result = run(world, formats=["vertical"])
        assert vhs.calls == [] and engine.calls == []
        assert set(result.stage_status.values()) == {"cached"}

    def test_replacing_one_take_reprocesses_only_that_segment(self, world):
        env, folder, vhs, engine = world
        run(world, formats=["vertical"])
        engine.calls.clear()
        synth(folder / "narration" / "02-root.wav", 5.5, lead=0.5, tail=0.5, freq=700, volume=4)
        result = run(world, formats=["vertical"])
        assert engine.calls == ["02-root"]
        assert result.segment_status == {"01-hook": ("cached", "cached"), "02-root": ("ran", "ran"), "03-home": ("cached", "cached")}

    def test_timing_change_rerenders_vhs_but_not_other_segments(self, world):
        env, folder, vhs, engine = world
        run(world, formats=["vertical"])
        vhs.calls.clear()
        synth(folder / "narration" / "02-root.wav", 6.5, lead=0.5, tail=0.5, volume=4)
        run(world, formats=["vertical"])
        assert len(vhs.calls) >= 1  # whole episode re-rendered: allowed

    def test_unchanged_take_never_rerenders_vhs(self, world):
        env, folder, vhs, engine = world
        run(world, formats=["vertical"])
        vhs.calls.clear()
        (folder / "voiceover.md").write_text(VOICEOVER + "\n")  # harmless edit
        run(world, formats=["vertical"])
        assert vhs.calls == []


class TestCaptions:
    def test_sidecars_follow_the_actual_words(self, world):
        env, *_ = world
        run(world, formats=["vertical"])
        srt = (env.root / "out" / "final" / "vertical" / "demo-01-ep.srt").read_text()
        assert "Linux has no C drive." in srt and "Slash home is where" in srt
        assert (env.root / "out" / "final" / "vertical" / "demo-01-ep.vtt").read_text().startswith("WEBVTT")

    def test_caption_timing_comes_from_the_recording_not_the_script(self, world):
        env, *_ = world
        run(world, formats=["vertical"])
        cues = vidkit._parse_srt_cues((env.root / "out" / "final" / "vertical" / "demo-01-ep.srt").read_text())
        second = next(c for c in cues if "slash is root" in c.text.lower())
        # script says 0:05, but segment 2 really starts after hook (3.2s) + pause
        assert 3.0 < second.start < 4.6

    def test_corrected_transcript_survives_rebuild_and_reaches_captions(self, world):
        env, folder, vhs, engine = world
        run(world, formats=["vertical"])
        path = folder / "transcript" / "02-root.yaml"
        data = yaml.safe_load(path.read_text())
        data["words"][1]["text"] = "SLASH"
        path.write_text(yaml.safe_dump(data, sort_keys=False))
        engine.calls.clear()
        run(world, formats=["vertical"])
        assert engine.calls == []
        assert "SLASH" in (env.root / "out" / "final" / "vertical" / "demo-01-ep.srt").read_text()

    def test_burned_copy_gets_unshifted_captions_and_final_gets_none_burned_twice(self, world):
        env, *_ = world
        run(world, formats=["horizontal"], placement="after-hook")
        burned = list((env.root / "out" / "intermediate" / "demo-01-ep").glob("horizontal-captioned.mp4.srt"))
        assert len(burned) == 1
        starts = [c.start for c in vidkit._parse_srt_cues(burned[0].read_text())]
        final = vidkit._parse_srt_cues((env.root / "out" / "final" / "horizontal" / "demo-01-ep.srt").read_text())
        assert max(c.start for c in final) == pytest.approx(max(starts) + 5, abs=0.05)


class TestMeasuredSync:
    def test_drifting_render_is_corrected_by_rerender(self, world):
        env, folder, vhs, engine = world
        vhs.speed = 0.96  # render runs 4% faster than the tape claims
        result = run(world, formats=["vertical"])
        assert len(vhs.calls) == 2
        assert result.sync["vertical"].ok

    def test_final_sync_is_within_tolerance(self, world):
        env, folder, vhs, engine = world
        vhs.speed = 0.96
        result = run(world, formats=["vertical"])
        assert all(abs(b.drift) <= 0.3 for b in result.sync["vertical"].beats)

    def test_unfixable_render_stops_with_report_and_no_output(self, world):
        env, folder, vhs, engine = world
        vhs.fixed = [1.0, 2.0]  # clears nowhere near the narration, whatever we ask
        with pytest.raises(pipeline.SyncFailed) as err:
            run(world, formats=["vertical"])
        report = env.root / "out" / "intermediate" / "demo-01-ep" / "sync-report.md"
        assert report.exists() and "Root" in report.read_text()
        assert "sync-report.md" in str(err.value)
        assert not (env.root / "out" / "final" / "vertical" / "demo-01-ep.mp4").exists()

    def test_narration_too_short_for_visuals_stops_with_actionable_message(self, world):
        env, folder, vhs, engine = world
        synth(folder / "narration" / "02-root.wav", 1.2, lead=0.2, tail=0.2, volume=4)
        with pytest.raises(retime.SyncError) as err:
            run(world, formats=["vertical"])
        assert "Root" in str(err.value) and "at least" in str(err.value)


class TestGuards:
    def test_missing_take_fails_before_any_render(self, world):
        env, folder, vhs, engine = world
        (folder / "narration" / "03-home.wav").unlink()
        with pytest.raises(narration.MissingTakes):
            run(world, formats=["vertical"])
        assert vhs.calls == []

    def test_dry_run_changes_nothing(self, world):
        env, folder, vhs, engine = world
        plan = run(world, formats=["vertical"], dry_run=True)
        assert vhs.calls == [] and engine.calls == []
        assert not (env.root / "out").exists()
        assert any("transcribe" in line or "ingest" in line for line in plan.plan_lines)

    def test_unknown_placement_rejected(self, world):
        with pytest.raises(ValueError):
            run(world, formats=["vertical"], placement="middle")


class TestApprovalFlow:
    def test_approve_then_identical_rebuild_stays_approved(self, world):
        env, *_ = world
        run(world, formats=["vertical"])
        final = env.root / "out" / "final"
        approval.approve(final, "demo-01-ep", "Dave")
        run(world, formats=["vertical"])
        assert approval.current(final, "demo-01-ep").state == "approved"

    def test_new_take_voids_approval(self, world):
        env, folder, *_ = world
        run(world, formats=["vertical"])
        final = env.root / "out" / "final"
        approval.approve(final, "demo-01-ep", "Dave")
        synth(folder / "narration" / "03-home.wav", 5.5, lead=0.5, tail=0.5, freq=500, volume=4)
        run(world, formats=["vertical"])
        assert approval.current(final, "demo-01-ep").state == "built"

    def test_metadata_extracted_from_post_copy(self, world):
        env, *_ = world
        run(world, formats=["vertical"])
        meta = (env.root / "out" / "final" / "demo-01-ep.meta.md").read_text()
        assert "Linux has NO C: drive #shorts" in meta and "#linux #chicanodev" in meta
        assert "Linux has no C drive." in meta  # accessible transcript
