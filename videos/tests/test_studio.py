"""Interactive recording session: resume, approve, retry, skip, quit, errors. No hardware needed."""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import narration  # noqa: E402
import recorder  # noqa: E402
import studio  # noqa: E402
from fake_audio import FakeBackend, FakeUI, tone  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

VOICEOVER = """# Demo: where programs live

## [0:00-0:10] Hook
Programs live in a few places.

## [0:10-0:25] Bin
Start with /bin. It holds core commands.

Like `ls` and `cp`.

## [0:25-0:40] Local
Then there is /usr/local for your own tools.
"""
IDS = ["01-hook", "02-bin", "03-local"]
ENTER = "enter"
TAKE = [ENTER, ENTER, ENTER]  # record, stop, approve


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "voiceover.md").write_text(VOICEOVER)
    return tmp_path


def session(folder, keys, recordings=None, backend=None, **opts):
    backend = backend or FakeBackend(recordings)
    ui = FakeUI(keys, choose=opts.pop("choose", None), confirms=opts.pop("confirms", None))
    store = recorder.TakeStore(folder, selected={})
    segments = narration.episode_segments(folder)
    s = studio.Session(segments, store, backend, ui, title="Demo", device=backend.resolve(), **opts)
    return s, ui, backend, store


def run(folder, keys, **kw):
    s, ui, backend, store = session(folder, keys, **kw)
    return s.run(), ui, backend, store


def approved(store):
    return [i for i in IDS if store.status(i) == "approved"]


class TestHappyPath:
    def test_records_a_whole_episode_with_three_keypresses_per_segment(self, folder):
        code, ui, backend, store = run(folder, [ENTER] + TAKE * 3)
        assert code == 0
        assert approved(store) == IDS
        assert backend.started == 3
        assert len(backend.played) == 3  # autoplay after each take
        for seg in IDS:
            assert narration.resolve_take(folder / "narration", seg, {}) == folder / "narration" / f"{seg}.wav"
        assert len(ui.named("complete")) == 1

    def test_segment_screen_shows_exact_script_text(self, folder):
        _, ui, _, _ = run(folder, [ENTER, "q"])
        seg = ui.named("segment")[0]
        assert seg["segment"].text == narration.episode_segments(folder)[0].text
        assert (seg["position"], seg["total"]) == (1, 3)

    def test_completion_lists_next_steps_and_does_not_build(self, folder):
        _, ui, _, _ = run(folder, [ENTER] + TAKE * 3)
        info = ui.named("complete")[0]
        assert info["approved"] == 3 and info["total"] == 3 and info["problems"] == {}

    def test_no_autoplay(self, folder):
        _, _, backend, _ = run(folder, [ENTER] + TAKE * 3, autoplay=False)
        assert backend.played == []

    def test_never_touches_video_approval(self):
        for name in ("studio.py", "recorder.py"):
            text = (Path(__file__).resolve().parent.parent / "tools" / name).read_text()
            assert "import approval" not in text and "from approval" not in text


class TestRetakes:
    def test_retry_keeps_the_old_take_and_approves_the_new_one(self, folder):
        keys = [ENTER, ENTER, ENTER, "r", ENTER, ENTER, "q"]  # overview, rec, stop, r (records at once), stop, approve, quit
        _, _, _, store = run(folder, keys, recordings=[tone(2, freq=300), tone(2, freq=900)])
        takes = store.takes("01-hook")
        assert [p.name for p in takes] == ["01-hook.take1.wav", "01-hook.take2.wav"]
        canonical = folder / "narration" / "01-hook.wav"
        assert canonical.read_bytes() == takes[1].read_bytes()
        assert store.approved_take("01-hook") == "01-hook.take2.wav"

    def test_previous_take_can_be_replayed_and_chosen(self, folder):
        keys = [ENTER, ENTER, ENTER, "r", ENTER, "b", ENTER, "q"]
        _, ui, backend, store = run(folder, keys, recordings=[tone(2, freq=300), tone(2, freq=900)])
        assert store.approved_take("01-hook") == "01-hook.take1.wav"
        assert backend.played[-1].name == "01-hook.take1.wav"
        assert any(r["position"] == 1 and r["count"] == 2 for r in ui.named("review"))

    def test_rerecording_an_approved_segment_asks_first(self, folder):
        run(folder, [ENTER] + TAKE + ["q"])
        old = (folder / "narration" / "01-hook.wav").read_bytes()
        _, ui, backend, store = run(folder, ["l", "q"], choose=["01-hook"], confirms=[False])
        assert "confirm" in [n for n, _ in ui.events]
        assert backend.started == 0
        assert (folder / "narration" / "01-hook.wav").read_bytes() == old


class TestResumeAndQuit:
    def test_resume_starts_at_first_incomplete_segment(self, folder):
        run(folder, [ENTER] + TAKE * 2 + ["q"])  # 01 and 02 approved, quit at 03's script
        _, ui, _, _ = run(folder, [ENTER, "q"])
        assert ui.named("segment")[0]["segment"].id == "03-local"
        assert ui.named("overview")[0]["next"] == "03-local"

    def test_quit_in_review_keeps_take_pending_not_approved(self, folder):
        _, _, _, store = run(folder, [ENTER, ENTER, ENTER, "q"])
        assert store.status("01-hook") == "pending"
        assert narration.resolve_take(folder / "narration", "01-hook", {}) is None

    def test_pending_take_is_offered_on_resume_without_recording_again(self, folder):
        run(folder, [ENTER, ENTER, ENTER, "q"])  # record, stop, (autoplay), quit before approving
        code, ui, backend, store = run(folder, [ENTER, ENTER, "q"])  # overview, approve pending, quit
        assert backend.started == 0
        assert store.status("01-hook") == "approved"
        assert "unreviewed" in ui.notes()

    def test_crash_recovery_after_hard_kill(self, folder):
        s, ui, backend, store = session(folder, [ENTER, ENTER, ENTER, "q"])
        s.run()
        (folder / "narration" / ".01-hook.staged.wav").write_bytes(b"junk")  # a swap that never finished
        code, _, _, store2 = run(folder, [ENTER, ENTER, "q"])
        assert store2.status("01-hook") == "approved"
        assert not list((folder / "narration").glob(".*staged*"))

    def test_eof_exits_cleanly_and_keeps_work(self, folder):
        code, _, _, store = run(folder, [ENTER] + TAKE)  # then input ends mid-episode
        assert code == 0
        assert store.status("01-hook") == "approved"

    def test_ctrl_c_while_recording_saves_the_partial_take(self, folder):
        s, ui, backend, store = session(folder, [ENTER, ENTER])
        ui.stop_interrupt = KeyboardInterrupt
        assert s.run() == 0
        assert len(store.takes("01-hook")) == 1
        assert store.status("01-hook") == "pending"


class TestScriptStaysPinned:
    """Every screen the session shows is told which segment's script to keep on screen."""

    @staticmethod
    def shown(ui):
        """(event, segment id, total) for every screen that must carry the script."""
        out = []
        for name, p in ui.events:
            if name in ("segment", "recording", "review", "focus"):
                out.append((name, p["segment"].id, p["total"]))
        return out

    def test_fresh_recording_carries_the_script(self, folder):
        _, ui, _, _ = run(folder, [ENTER, ENTER, ENTER, "q"])
        rec = ui.named("recording")[0]
        assert rec["segment"].text == narration.episode_segments(folder)[0].text
        assert rec["total"] == 3

    def test_resumed_pending_take_focuses_the_script_before_review(self, folder):
        run(folder, [ENTER, ENTER, ENTER, "q"])
        _, ui, backend, _ = run(folder, [ENTER, "q"])
        names = [n for n, _ in ui.events if n in ("focus", "review")]
        assert names[:2] == ["focus", "review"]
        assert ui.named("focus")[0]["segment"].id == "01-hook" and backend.started == 0

    def test_rerecording_carries_the_script(self, folder):
        _, ui, _, _ = run(folder, [ENTER, ENTER, ENTER, "r", ENTER, "q"])
        recs = ui.named("recording")
        assert len(recs) == 2 and all(r["segment"].id == "01-hook" and r["total"] == 3 for r in recs)

    def test_review_and_playback_carry_the_script(self, folder):
        _, ui, _, _ = run(folder, [ENTER, ENTER, ENTER, "p", "q"])
        reviews = ui.named("review")
        assert len(reviews) >= 2
        assert all(r["segment"].id == "01-hook" and r["total"] == 3 for r in reviews)

    def test_switching_to_an_earlier_take_carries_the_script(self, folder):
        _, ui, _, _ = run(folder, [ENTER, ENTER, ENTER, "r", ENTER, "b", "q"],
                          recordings=[tone(2, freq=300), tone(2, freq=900)])
        last = ui.named("review")[-1]
        assert last["position"] == 1 and last["segment"].id == "01-hook" and last["total"] == 3

    def test_same_segment_five_times_play_each_then_approve_the_third(self, folder):
        keys = [ENTER, ENTER, ENTER, "p"] + ["r", ENTER, "p"] * 4 + ["b", "b", ENTER, "q"]
        _, ui, backend, store = run(folder, keys, recordings=[tone(2, freq=200 + 100 * i) for i in range(5)])
        assert len(store.takes("01-hook")) == 5
        assert store.approved_take("01-hook") == "01-hook.take3.wav"
        pinned = [s for s in self.shown(ui) if s[0] in ("recording", "review")]
        assert len(pinned) >= 15 and {(i, t) for _, i, t in pinned} == {("01-hook", 3)}
        assert {p.name for p in backend.played} == {f"01-hook.take{n}.wav" for n in range(1, 6)}


class TestSkipAndOrder:
    def test_skip_moves_on_and_returns_to_skipped_at_the_end(self, folder):
        keys = [ENTER, "s"] + TAKE * 2 + [ENTER] + TAKE  # skip 01; do 02, 03; overview; do 01
        code, ui, _, store = run(folder, keys)
        assert approved(store) == IDS
        assert [s["segment"].id for s in ui.named("segment")] == ["01-hook", "02-bin", "03-local", "01-hook"]

    def test_list_lets_you_record_out_of_order(self, folder):
        _, ui, _, store = run(folder, ["l"] + TAKE + ["q"], choose=["03-local"])
        assert approved(store) == ["03-local"]

    def test_segment_option_works_on_one_segment_then_stops(self, folder):
        code, ui, backend, store = run(folder, TAKE, only="02-bin")
        assert code == 0 and approved(store) == ["02-bin"] and backend.started == 1

    @pytest.mark.parametrize("name", ["02-bin", "02", "bin"])
    def test_segment_option_accepts_id_number_or_slug(self, folder, name):
        s, *_ = session(folder, [], only=name)
        assert s.only.id == "02-bin"

    def test_unknown_segment_is_a_clear_error(self, folder):
        s, ui, backend, _ = session(folder, [], only="nope")
        assert s.run() == 2
        assert "01-hook" in ui.notes() and backend.started == 0


class TestProblems:
    def test_mic_error_is_explained_and_nothing_is_saved(self, folder):
        backend = FakeBackend([recorder.MicError("Could not open Fake Mic. Allow the terminal under Privacy.")])
        code, ui, _, store = run(folder, [ENTER, ENTER, "q"], backend=backend)
        assert "Privacy" in ui.notes()
        assert store.takes("01-hook") == []

    def test_after_a_mic_error_the_same_segment_can_be_retried(self, folder):
        backend = FakeBackend([recorder.MicError("no mic"), tone()])
        _, _, _, store = run(folder, [ENTER, ENTER, ENTER, ENTER, ENTER, "q"], backend=backend)
        assert store.status("01-hook") == "approved"

    def test_too_short_take_cannot_be_approved(self, folder):
        _, ui, _, store = run(folder, [ENTER, ENTER, ENTER, "q"], recordings=[tone(0.2)])
        assert store.status("01-hook") == "pending" and not approved(store)
        assert ui.named("review")[0]["can_approve"] is False

    def test_silent_take_points_at_microphone_permission(self, folder):
        silent = tone(2) * 0
        _, ui, _, _ = run(folder, [ENTER, ENTER, ENTER, "q"], recordings=[silent])
        assert "Privacy" in " ".join(ui.named("review")[0]["problems"])
        assert ui.named("review")[0]["can_approve"] is False

    def test_quiet_take_warns_but_can_be_approved(self, folder):
        _, ui, _, store = run(folder, [ENTER] + TAKE + ["q"], recordings=[tone(2, amp=0.01)])
        assert ui.named("review")[0]["problems"] and ui.named("review")[0]["can_approve"] is True
        assert store.status("01-hook") == "approved"

    def test_device_disconnect_warns_and_keeps_audio(self, folder):
        backend = FakeBackend()
        backend.capture_error = "The microphone stopped during recording."
        _, ui, _, store = run(folder, [ENTER, ENTER, ENTER, "q"], backend=backend)
        assert "stopped" in ui.notes()
        assert len(store.takes("01-hook")) == 1

    def test_disk_full_while_saving_is_reported_and_old_take_is_safe(self, folder, monkeypatch):
        run(folder, [ENTER] + TAKE + ["q"])
        old = (folder / "narration" / "01-hook.wav").read_bytes()

        def full(*a, **k):
            raise OSError(28, "No space left on device")
        monkeypatch.setattr(recorder, "_write_raw_wav", full)
        _, ui, _, store = run(folder, ["l", ENTER, ENTER, "q"], choose=["01-hook"], confirms=[True])
        assert "disk is full" in ui.notes()
        assert (folder / "narration" / "01-hook.wav").read_bytes() == old
