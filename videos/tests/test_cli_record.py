"""`vidkit.py record`: argument handling, status, devices, and end-to-end compatibility with the pipeline."""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import narration  # noqa: E402
import recorder  # noqa: E402
import studio  # noqa: E402
import vidkit  # noqa: E402
from fake_audio import FakeBackend, FakeUI  # noqa: E402
from test_narration import VOICEOVER  # noqa: E402

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
ENTER = "enter"


@pytest.fixture
def episode(tmp_path, monkeypatch):
    folder = tmp_path / "series" / "demo" / "01-ep"
    folder.mkdir(parents=True)
    (folder / "voiceover.md").write_text(VOICEOVER)
    (folder / "body.tape").write_text("# @beat 0:00 Hook\nSleep 1s\n")
    monkeypatch.setattr(vidkit, "ROOT", tmp_path)
    monkeypatch.setattr(vidkit, "EPISODES", [("demo", "01-ep")])
    return folder


@pytest.fixture
def backend(monkeypatch):
    fake = FakeBackend()
    monkeypatch.setattr(recorder, "default_backend", lambda: fake)
    return fake


@pytest.fixture
def interactive(monkeypatch):
    """Pretend stdin/stdout are a terminal and drive the screen from a key script."""
    holder = {}

    def start(keys, **kw):
        holder["ui"] = FakeUI(keys, **kw)
        monkeypatch.setattr(vidkit, "_is_interactive", lambda: True)
        monkeypatch.setattr(studio, "make_ui", lambda *a, **k: holder["ui"])
        return holder["ui"]
    return start


class TestArguments:
    def test_needs_an_episode(self, episode, backend, capsys):
        assert vidkit.main(["record"]) == 2
        assert "episode" in capsys.readouterr().out

    def test_unknown_episode(self, episode, backend, capsys):
        assert vidkit.main(["record", "nope/99"]) == 2
        assert "unknown episode" in capsys.readouterr().out

    def test_one_episode_at_a_time(self, episode, backend, monkeypatch, capsys):
        other = episode.parent / "02-other"
        other.mkdir()
        (other / "voiceover.md").write_text(VOICEOVER)
        monkeypatch.setattr(vidkit, "EPISODES", [("demo", "01-ep"), ("demo", "02-other")])
        assert vidkit.main(["record", "demo"]) == 2
        assert "one episode" in capsys.readouterr().out

    def test_segment_value_is_not_mistaken_for_an_episode_name(self, episode, backend, interactive):
        interactive([ENTER] * 3, )
        assert vidkit.main(["record", "demo/01-ep", "--segment", "01-hook", "--device", "Fake Mic"]) == 0

    def test_script_without_timed_headings_is_explained(self, episode, backend, capsys):
        (episode / "voiceover.md").write_text("# Title\n\njust some text\n")
        assert vidkit.main(["record", "demo/01-ep", "--status"]) == 2
        assert "## [0:00-0:10]" in capsys.readouterr().out

    def test_not_a_terminal_refuses_instead_of_recording(self, episode, backend, capsys):
        assert vidkit.main(["record", "demo/01-ep"]) == 2
        assert "terminal" in capsys.readouterr().out
        assert backend.started == 0 and not (episode / "narration").exists()

    def test_bad_device_is_explained(self, episode, backend, interactive, capsys):
        interactive([])
        assert vidkit.main(["record", "demo/01-ep", "--device", "nope"]) == 1
        assert "not a microphone" in capsys.readouterr().out
        assert backend.started == 0


class TestNonInteractiveViews:
    def test_list_devices_needs_no_episode(self, backend, capsys):
        assert vidkit.main(["record", "--list-devices"]) == 0
        out = capsys.readouterr().out
        assert "Fake Mic" in out and "48" in out

    def test_status_shows_approved_and_missing_without_a_microphone(self, episode, monkeypatch, capsys):
        def no_mic():
            raise AssertionError("--status must not touch audio hardware")
        monkeypatch.setattr(recorder, "default_backend", no_mic)
        (episode / "narration").mkdir()
        (episode / "narration" / "01-hook.wav").write_bytes(b"x")
        assert vidkit.main(["record", "demo/01-ep", "--status"]) == 0
        out = capsys.readouterr().out
        assert "1 of 3" in out
        assert "Approved" in out and "Not recorded" in out and "02-root-home" in out

    def test_status_reports_waiting_takes(self, episode, backend, capsys):
        store = recorder.TakeStore(episode, {})
        path = store.next_take_path("01-hook")
        path.write_bytes(b"x")
        vidkit.main(["record", "demo/01-ep", "--status"])
        assert "waiting for your approval" in capsys.readouterr().out


@needs_ffmpeg
class TestEndToEnd:
    def test_recorded_episode_passes_check_audio_and_feeds_the_pipeline(self, episode, backend, interactive, capsys):
        interactive([ENTER] + [ENTER] * 9)  # overview, then record/stop/approve x3
        assert vidkit.main(["record", "demo/01-ep"]) == 0
        capsys.readouterr()
        assert sorted(p.name for p in (episode / "narration").glob("*.wav")) == [
            "01-hook.wav", "02-root-home.wav", "03-etc-config.wav"]
        assert vidkit.main(["check-audio", "demo/01-ep"]) == 0
        segments = narration.episode_segments(episode)
        report = narration.prepare(segments, episode / "narration", episode / "work", {})
        assert [r.segment.id for r in report] == [s.id for s in segments]

    def test_resume_in_a_second_run_finishes_the_episode(self, episode, backend, interactive):
        interactive([ENTER, ENTER, ENTER, ENTER, "q"])  # overview, take 1 approved, quit at segment 2
        assert vidkit.main(["record", "demo/01-ep"]) == 0
        interactive([ENTER] + [ENTER] * 6)
        assert vidkit.main(["record", "demo/01-ep"]) == 0
        assert len(list((episode / "narration").glob("*.wav"))) == 3

    def test_video_approval_state_is_untouched(self, episode, backend, interactive):
        interactive([ENTER] + [ENTER] * 9)
        vidkit.main(["record", "demo/01-ep"])
        assert not (vidkit.ROOT / "out").exists()
