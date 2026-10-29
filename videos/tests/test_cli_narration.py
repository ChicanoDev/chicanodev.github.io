import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import vidkit  # noqa: E402
from test_narration import VOICEOVER, synth  # noqa: E402


@pytest.fixture
def episode(tmp_path, monkeypatch):
    """A throwaway episode `demo/01-ep` rooted in tmp_path."""
    folder = tmp_path / "series" / "demo" / "01-ep"
    folder.mkdir(parents=True)
    (folder / "voiceover.md").write_text(VOICEOVER)
    (folder / "body.tape").write_text("# @beat 0:00 Hook\nSleep 1s\n")
    monkeypatch.setattr(vidkit, "ROOT", tmp_path)
    monkeypatch.setattr(vidkit, "EPISODES", [("demo", "01-ep")])
    return folder


class TestSegmentsCommand:
    def test_prints_numbered_segments_and_filenames(self, episode, capsys):
        assert vidkit.main(["segments", "demo/01-ep"]) == 0
        out = capsys.readouterr().out
        assert "01-hook" in out and "02-root-home" in out and "03-etc-config" in out
        assert "narration/01-hook.m4a" in out
        assert "Linux has no C drive." in out

    def test_marks_recorded_segments(self, episode, capsys):
        (episode / "narration").mkdir()
        synth(episode / "narration" / "01-hook.wav", 1.5)
        vidkit.main(["segments", "demo/01-ep"])
        lines = capsys.readouterr().out.splitlines()
        assert any("recorded" in l and "01-hook" in l for l in lines)
        assert any("todo" in l and "02-root-home" in l for l in lines)


class TestCheckAudioCommand:
    def test_missing_segments_exit_1_with_fix(self, episode, capsys):
        assert vidkit.main(["check-audio", "demo/01-ep"]) == 1
        assert "narration/01-hook.m4a" in capsys.readouterr().out

    def test_all_good_exit_0(self, episode, capsys):
        d = episode / "narration"
        d.mkdir()
        for sid in ("01-hook", "02-root-home", "03-etc-config"):
            synth(d / f"{sid}.wav", 1.5, volume=4)
        assert vidkit.main(["check-audio", "demo/01-ep"]) == 0
        assert capsys.readouterr().out.count("OK") == 3

    def test_duplicate_takes_reported(self, episode, capsys):
        d = episode / "narration"
        d.mkdir()
        synth(d / "01-hook.wav", 1.5, volume=4)
        synth(d / "01-hook.take2.wav", 1.5, volume=4)
        assert vidkit.main(["check-audio", "demo/01-ep"]) == 1
        assert "selected" in capsys.readouterr().out

    def test_corrupt_take_reported(self, episode, capsys):
        d = episode / "narration"
        d.mkdir()
        (d / "01-hook.m4a").write_bytes(b"junk")
        assert vidkit.main(["check-audio", "demo/01-ep"]) == 1
        assert "not a readable audio file" in capsys.readouterr().out

    def test_selected_manifest_resolves_duplicates(self, episode, capsys):
        d = episode / "narration"
        d.mkdir()
        synth(d / "01-hook.wav", 1.5, volume=4)
        synth(d / "01-hook.take2.wav", 1.5, volume=4)
        (episode / "alignment.yaml").write_text("selected:\n  01-hook: 01-hook.take2.wav\n")
        vidkit.main(["check-audio", "demo/01-ep"])
        assert "01-hook.take2.wav" in capsys.readouterr().out
