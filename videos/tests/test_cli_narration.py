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


SPOKEN = {"01-hook": "Linux has no sea drive.", "02-root-home": "That slash is root.", "03-etc-config": "Config lives here."}


@pytest.fixture
def recorded(episode, monkeypatch):
    import transcribe
    d = episode / "narration"
    d.mkdir()
    for sid in SPOKEN:
        synth(d / f"{sid}.wav", 1.5, volume=4)
    calls = []

    def fake_engine(*a, **k):
        def run(wav):
            calls.append(Path(wav).stem)
            toks = SPOKEN[Path(wav).stem].split()
            return [transcribe.Word(i * 0.4, i * 0.4 + 0.3, t, 0.95) for i, t in enumerate(toks)]
        return run

    monkeypatch.setattr(transcribe, "whisper_engine", fake_engine)
    return episode, calls


class TestTranscribeCommand:
    def test_writes_editable_transcripts_and_reports_flags(self, recorded, capsys):
        episode, calls = recorded
        assert vidkit.main(["transcribe", "demo/01-ep"]) == 0
        assert (episode / "transcript" / "01-hook.yaml").exists()
        out = capsys.readouterr().out
        assert "sea" in out and "differs-from-script" in out

    def test_second_run_transcribes_nothing(self, recorded, capsys):
        episode, calls = recorded
        vidkit.main(["transcribe", "demo/01-ep"])
        calls.clear()
        vidkit.main(["transcribe", "demo/01-ep"])
        assert calls == []
        assert "cached" in capsys.readouterr().out

    def test_replacing_one_take_retranscribes_only_it(self, recorded, capsys):
        episode, calls = recorded
        vidkit.main(["transcribe", "demo/01-ep"])
        calls.clear()
        synth(episode / "narration" / "02-root-home.wav", 2.0, freq=700, volume=4)
        vidkit.main(["transcribe", "demo/01-ep"])
        assert calls == ["02-root-home"]

    def test_missing_takes_exit_1(self, episode, capsys):
        assert vidkit.main(["transcribe", "demo/01-ep"]) == 1
        assert "01-hook" in capsys.readouterr().out


class TestTranscriptCommand:
    def test_shows_flags_without_running_engine(self, recorded, capsys):
        episode, calls = recorded
        vidkit.main(["transcribe", "demo/01-ep"])
        calls.clear()
        capsys.readouterr()
        assert vidkit.main(["transcript", "demo/01-ep"]) == 0
        assert calls == []
        assert "sea" in capsys.readouterr().out

    def test_corrected_word_clears_flag(self, recorded, capsys):
        import yaml
        episode, _ = recorded
        vidkit.main(["transcribe", "demo/01-ep"])
        path = episode / "transcript" / "01-hook.yaml"
        data = yaml.safe_load(path.read_text())
        data["words"][3]["text"] = "C"
        path.write_text(yaml.safe_dump(data, sort_keys=False))
        capsys.readouterr()
        vidkit.main(["transcript", "demo/01-ep"])
        out = capsys.readouterr().out
        assert "sea" not in out and "edited" in out

    def test_before_transcribing_tells_user_what_to_run(self, episode, capsys):
        assert vidkit.main(["transcript", "demo/01-ep"]) == 1
        assert "transcribe" in capsys.readouterr().out


class TestVenvGuard:
    """Running with the system python3 must not crash with ModuleNotFoundError."""

    def test_new_command_reexecs_into_project_venv(self, episode, monkeypatch, tmp_path):
        venv_python = tmp_path / ".venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        venv_python.write_text("")
        calls = []
        monkeypatch.setattr(vidkit.os, "execv", lambda path, args: calls.append((path, args)))
        monkeypatch.setattr(vidkit.sys, "prefix", "/usr/local")  # pretend: system python
        vidkit.main(["segments", "demo/01-ep"])
        assert calls and calls[0][0] == str(venv_python)
        assert calls[0][1][1:] == vidkit.sys.argv

    def test_legacy_command_does_not_reexec(self, episode, monkeypatch, tmp_path):
        (tmp_path / ".venv" / "bin").mkdir(parents=True)
        (tmp_path / ".venv" / "bin" / "python").write_text("")
        calls = []
        monkeypatch.setattr(vidkit.os, "execv", lambda *a: calls.append(a))
        monkeypatch.setattr(vidkit.sys, "prefix", "/usr/local")
        vidkit.main(["lint", "demo/01-ep"])
        assert calls == []

    def test_already_in_venv_does_not_loop(self, episode, monkeypatch, tmp_path):
        (tmp_path / ".venv" / "bin").mkdir(parents=True)
        (tmp_path / ".venv" / "bin" / "python").write_text("")
        calls = []
        monkeypatch.setattr(vidkit.os, "execv", lambda *a: calls.append(a))
        monkeypatch.setattr(vidkit.sys, "prefix", str(tmp_path / ".venv"))
        vidkit.main(["segments", "demo/01-ep"])
        assert calls == []

    def test_no_venv_and_no_yaml_prints_setup_command(self, episode, monkeypatch, capsys):
        monkeypatch.setattr(vidkit.sys, "prefix", "/usr/local")
        monkeypatch.setattr(vidkit, "_has_module", lambda name: False)
        assert vidkit.main(["segments", "demo/01-ep"]) == 1
        out = capsys.readouterr().out
        assert "uv venv --python 3.12" in out and "requirements.txt" in out


class TestSegmentsCreatesFolder:
    def test_narration_folder_is_created_so_you_know_where_to_save(self, episode, capsys):
        assert not (episode / "narration").exists()
        vidkit.main(["segments", "demo/01-ep"])
        assert (episode / "narration").is_dir()
        assert "series/demo/01-ep/narration" in capsys.readouterr().out
