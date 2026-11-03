"""Recorder foundation: WAV output format, take files, safe approval, crash recovery."""
import json
import shutil
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import narration  # noqa: E402
import recorder  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

SEG = "04-local"


def tone(seconds=1.0, rate=48000, channels=1, freq=440, amp=0.4):
    t = np.arange(int(seconds * rate)) / rate
    mono = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.stack([mono] * channels, axis=1) if channels > 1 else mono


def wav_info(path):
    with wave.open(str(path), "rb") as w:
        return w.getnchannels(), w.getframerate(), w.getsampwidth(), w.getnframes()


def make_take(store, seg=SEG, seconds=1.0, freq=440):
    path = store.next_take_path(seg)
    recorder.to_wav(tone(seconds, freq=freq), 48000, path)
    return path


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "narration").mkdir()
    return tmp_path


@pytest.fixture
def store(folder):
    return recorder.TakeStore(folder, selected={})


class TestToWav:
    def test_output_is_mono_48k_16bit(self, tmp_path):
        out = tmp_path / "a.wav"
        recorder.to_wav(tone(1.0, rate=44100, channels=2), 44100, out)
        channels, rate, width, frames = wav_info(out)
        assert (channels, rate, width) == (1, 48000, 2)
        assert abs(frames - 48000) < 200  # same duration after resampling

    def test_already_correct_format_keeps_duration(self, tmp_path):
        out = tmp_path / "a.wav"
        recorder.to_wav(tone(0.5), 48000, out)
        assert abs(wav_info(out)[3] - 24000) < 100

    def test_int16_input_accepted(self, tmp_path):
        out = tmp_path / "a.wav"
        recorder.to_wav((tone(0.5) * 32767).astype(np.int16), 48000, out)
        assert wav_info(out)[:3] == (1, 48000, 2)

    def test_failure_leaves_no_partial_file_and_keeps_existing(self, tmp_path, monkeypatch):
        out = tmp_path / "a.wav"
        recorder.to_wav(tone(0.5), 48000, out)
        before = out.read_bytes()

        def boom(*a, **k):
            raise narration.BadAudio("ffmpeg exploded")
        monkeypatch.setattr(narration, "_ffmpeg", boom)
        with pytest.raises(recorder.RecorderError):
            recorder.to_wav(tone(0.5), 48000, out)
        assert out.read_bytes() == before
        assert [p.name for p in tmp_path.iterdir()] == ["a.wav"]

    def test_disk_full_is_a_clear_storage_error(self, tmp_path, monkeypatch):
        def full(*a, **k):
            raise OSError(28, "No space left on device")
        monkeypatch.setattr(recorder, "_write_raw_wav", full)
        with pytest.raises(recorder.StorageError, match="space|disk"):
            recorder.to_wav(tone(0.5), 48000, tmp_path / "a.wav")
        assert list(tmp_path.iterdir()) == []


class TestTakeFiles:
    def test_takes_live_outside_the_resolver_scan(self, store, folder):
        path = make_take(store)
        assert path.parent == folder / "narration" / "takes"
        assert path.name == f"{SEG}.take1.wav"
        assert narration.resolve_take(folder / "narration", SEG, {}) is None

    def test_numbering_never_reuses_a_number(self, store):
        first, second = make_take(store), make_take(store)
        first.unlink()
        third = make_take(store)
        assert [p.name for p in (first, second, third)] == [f"{SEG}.take{n}.wav" for n in (1, 2, 3)]

    def test_takes_listed_in_order(self, store):
        for _ in range(11):
            make_take(store)
        assert [p.name for p in store.takes(SEG)][-1] == f"{SEG}.take11.wav"
        assert store.takes(SEG)[1].name == f"{SEG}.take2.wav"

    def test_other_segments_do_not_mix(self, store):
        make_take(store, "01-hook")
        assert store.takes(SEG) == []


class TestApprove:
    def test_approval_creates_the_canonical_file_pipeline_reads(self, store, folder):
        take = make_take(store)
        store.approve(SEG, take)
        canonical = narration.resolve_take(folder / "narration", SEG, {})
        assert canonical == folder / "narration" / f"{SEG}.wav"
        assert canonical.read_bytes() == take.read_bytes()
        assert take.exists()  # the take itself is kept

    def test_status_transitions(self, store):
        assert store.status(SEG) == "missing"
        take = make_take(store)
        assert store.status(SEG) == "pending"
        store.approve(SEG, take)
        assert store.status(SEG) == "approved"

    def test_existing_hand_made_narration_counts_as_approved(self, store, folder):
        (folder / "narration" / f"{SEG}.m4a").write_bytes(b"not really audio")
        assert store.status(SEG) == "approved"

    def test_replacing_archives_a_foreign_file_and_leaves_one_canonical(self, store, folder):
        original = folder / "narration" / f"{SEG}.m4a"
        original.write_bytes(b"hand made recording")
        store.approve(SEG, make_take(store))
        top = [p.name for p in (folder / "narration").iterdir() if p.is_file()]
        assert top == [f"{SEG}.wav"]
        archived = list((folder / "narration" / "takes").glob(f"{SEG}.prev*.m4a"))
        assert [p.read_bytes() for p in archived] == [b"hand made recording"]

    def test_replacing_an_approved_take_keeps_the_old_audio(self, store, folder):
        first = make_take(store, freq=300)
        store.approve(SEG, first)
        second = make_take(store, freq=900)
        store.approve(SEG, second)
        canonical = folder / "narration" / f"{SEG}.wav"
        assert canonical.read_bytes() == second.read_bytes()
        assert first.read_bytes() != second.read_bytes() and first.exists()

    def test_selected_take_is_reported(self, store):
        take = make_take(store)
        store.approve(SEG, take)
        assert store.approved_take(SEG) == take.name

    def test_rejects_wrong_format(self, store, folder):
        bad = store.takes_dir / f"{SEG}.take1.wav"
        bad.parent.mkdir(parents=True)
        with wave.open(str(bad), "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100); w.writeframes(b"\0\0" * 400)
        with pytest.raises(recorder.RecorderError, match="48"):
            store.approve(SEG, bad)
        assert store.status(SEG) == "pending"

    def test_refuses_when_alignment_selected_names_a_file(self, folder):
        pinned = recorder.TakeStore(folder, selected={SEG: "something.m4a"})
        take = make_take(pinned)
        with pytest.raises(recorder.RecorderError, match="selected"):
            pinned.approve(SEG, take)


class TestFailureInjection:
    """A failure at any step of replacing an approved take must leave the old audio recoverable."""

    @pytest.fixture
    def approved(self, store, folder):
        first = make_take(store, freq=300)
        store.approve(SEG, first)
        return first.read_bytes(), make_take(store, freq=900), folder / "narration" / f"{SEG}.wav"

    @pytest.mark.parametrize("hook", ["_copy", "_replace"])
    def test_old_canonical_survives(self, store, folder, approved, monkeypatch, hook):
        old_bytes, new_take, canonical = approved

        def boom(*a, **k):
            raise OSError(28, "No space left on device")
        monkeypatch.setattr(recorder, hook, boom)
        with pytest.raises(recorder.RecorderError):
            store.approve(SEG, new_take)
        assert canonical.read_bytes() == old_bytes
        assert narration.resolve_take(folder / "narration", SEG, {}) == canonical
        assert not list((folder / "narration").glob(".*staged*"))

    def test_failure_archiving_the_old_file_replaces_nothing(self, store, folder, monkeypatch):
        """Staging works, archiving the hand-made old file fails: the old file stays the pipeline's take."""
        old = folder / "narration" / f"{SEG}.m4a"
        old.write_bytes(b"hand made recording")
        new_take = make_take(store)
        real, calls = recorder._copy, []

        def flaky(src, dst):
            calls.append(dst)
            if len(calls) == 2:
                raise OSError(5, "I/O error")
            real(src, dst)
        monkeypatch.setattr(recorder, "_copy", flaky)
        with pytest.raises(recorder.RecorderError):
            store.approve(SEG, new_take)
        assert len(calls) == 2
        assert old.read_bytes() == b"hand made recording"
        assert narration.resolve_take(folder / "narration", SEG, {}) == old
        assert not (folder / "narration" / f"{SEG}.wav").exists()

    def test_manifest_failure_does_not_lose_audio(self, store, folder, approved, monkeypatch):
        old_bytes, new_take, canonical = approved

        def boom(*a, **k):
            raise OSError(13, "Permission denied")
        monkeypatch.setattr(recorder, "_write_json", boom)
        store.approve(SEG, new_take)  # audio swap already done; metadata is best effort
        assert canonical.read_bytes() == new_take.read_bytes()
        assert store.warnings
        assert store.status(SEG) == "approved"
        assert any(p.read_bytes() == old_bytes for p in store.takes(SEG))  # old take still on disk

    def test_stale_staged_file_cleaned_only_when_canonical_is_intact(self, store, folder):
        take = make_take(store)
        store.approve(SEG, take)
        staged = folder / "narration" / f".{SEG}.staged.wav"
        staged.write_bytes(b"leftover")
        store.recover()
        assert not staged.exists()
        assert (folder / "narration" / f"{SEG}.wav").exists()

    def test_staged_file_kept_if_canonical_missing(self, store, folder):
        staged = folder / "narration" / f".{SEG}.staged.wav"
        shutil.copy(make_take(store), staged)
        store.recover()
        assert staged.exists()  # may be the only copy of a good recording

    def test_crash_after_replace_before_old_removed_is_repaired(self, store, folder):
        """Old .m4a archived, new .wav in place, process died before removing the .m4a."""
        old = folder / "narration" / f"{SEG}.m4a"
        old.write_bytes(b"hand made recording")
        archive = store.takes_dir
        archive.mkdir(parents=True, exist_ok=True)
        (archive / f"{SEG}.prev1.m4a").write_bytes(b"hand made recording")
        shutil.copy(make_take(store), folder / "narration" / f"{SEG}.wav")
        store.recover()
        assert not old.exists()
        assert (archive / f"{SEG}.prev1.m4a").exists()
        assert narration.resolve_take(folder / "narration", SEG, {}) == folder / "narration" / f"{SEG}.wav"


class TestStateRecovery:
    def test_corrupt_manifest_is_survivable(self, store, folder):
        take = make_take(store)
        store.approve(SEG, take)
        (store.takes_dir / "record-state.json").write_text("{ not json")
        fresh = recorder.TakeStore(folder, selected={})
        assert fresh.status(SEG) == "approved"
        assert fresh.approved_take(SEG) == take.name  # rebuilt by matching audio
        json.loads((fresh.takes_dir / "record-state.json").read_text())  # healed

    def test_missing_manifest_is_fine(self, store, folder):
        store.approve(SEG, make_take(store))
        (store.takes_dir / "record-state.json").unlink()
        assert recorder.TakeStore(folder, selected={}).status(SEG) == "approved"

    def test_pending_is_latest_unreviewed_take(self, store):
        t1 = make_take(store)
        assert store.pending(SEG) == t1
        store.reject(SEG, t1)
        assert store.pending(SEG) is None
        t2 = make_take(store)
        assert store.pending(SEG) == t2

    def test_take_older_than_approved_is_not_pending(self, store):
        t1, t2 = make_take(store), make_take(store, freq=700)
        store.approve(SEG, t2)
        assert store.pending(SEG) is None
        assert t1.exists()

    def test_newer_take_after_approval_is_pending(self, store):
        store.approve(SEG, make_take(store))
        t2 = make_take(store, freq=700)
        assert store.pending(SEG) == t2
        assert store.status(SEG) == "approved"  # the old approval stands until replaced

    def test_pending_survives_restart(self, store, folder):
        t1 = make_take(store)
        assert recorder.TakeStore(folder, selected={}).pending(SEG) == t1

    def test_startup_never_deletes_audio(self, store, folder):
        make_take(store)
        store.approve(SEG, make_take(store))
        before = sorted(p.name for p in folder.rglob("*.wav"))
        recorder.TakeStore(folder, selected={}).recover()
        assert sorted(p.name for p in folder.rglob("*.wav")) == before
