import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import captions  # noqa: E402
import narration  # noqa: E402
import transcribe  # noqa: E402
from transcribe import Word  # noqa: E402


def words(text, start=0.0, step=0.4, conf=0.95):
    return [Word(round(start + i * step, 3), round(start + i * step + 0.3, 3), w, conf)
            for i, w in enumerate(text.split())]


def seg(id="01-hook", text="Linux has no C drive."):
    return narration.Segment(1, id, "Hook", text)


class FakeEngine:
    def __init__(self, text):
        self.text, self.calls = text, 0

    def __call__(self, wav):
        self.calls += 1
        return words(self.text)


class TestTranscriptStore:
    def test_first_run_transcribes_and_saves_yaml(self, tmp_path):
        eng = FakeEngine("Linux has no C drive")
        status = transcribe.ensure(seg(), "sha1", Path("x.wav"), tmp_path, eng)
        assert status == "ran"
        data = yaml.safe_load((tmp_path / "01-hook.yaml").read_text())
        assert data["audio_sha"] == "sha1"
        assert [w["text"] for w in data["words"]] == ["Linux", "has", "no", "C", "drive"]

    def test_same_audio_is_cached(self, tmp_path):
        eng = FakeEngine("Linux has no C drive")
        transcribe.ensure(seg(), "sha1", Path("x.wav"), tmp_path, eng)
        assert transcribe.ensure(seg(), "sha1", Path("x.wav"), tmp_path, eng) == "cached"
        assert eng.calls == 1

    def test_user_edit_survives_rebuild(self, tmp_path):
        eng = FakeEngine("Linux has no sea drive")
        transcribe.ensure(seg(), "sha1", Path("x.wav"), tmp_path, eng)
        path = tmp_path / "01-hook.yaml"
        data = yaml.safe_load(path.read_text())
        data["words"][3]["text"] = "C"
        path.write_text(yaml.safe_dump(data, sort_keys=False))
        transcribe.ensure(seg(), "sha1", Path("x.wav"), tmp_path, eng)
        assert [w.text for w in transcribe.load(tmp_path, "01-hook").words][3] == "C"

    def test_changed_audio_retranscribes_and_keeps_old_as_stale(self, tmp_path):
        transcribe.ensure(seg(), "sha1", Path("x.wav"), tmp_path, FakeEngine("old words here"))
        status = transcribe.ensure(seg(), "sha2", Path("x.wav"), tmp_path, FakeEngine("new words now"))
        assert status == "ran"
        assert transcribe.load(tmp_path, "01-hook").audio_sha == "sha2"
        stale = yaml.safe_load((tmp_path / "01-hook.stale.yaml").read_text())
        assert stale["words"][0]["text"] == "old"

    def test_edited_flag_set_only_when_text_differs_from_asr(self, tmp_path):
        transcribe.ensure(seg(), "sha1", Path("x.wav"), tmp_path, FakeEngine("a b c"))
        assert not transcribe.load(tmp_path, "01-hook").has_edits
        path = tmp_path / "01-hook.yaml"
        data = yaml.safe_load(path.read_text())
        data["words"][0]["text"] = "A"
        path.write_text(yaml.safe_dump(data, sort_keys=False))
        assert transcribe.load(tmp_path, "01-hook").has_edits


class TestReviewFlags:
    def flags(self, spoken, script, conf=0.95):
        return transcribe.review_flags(words(spoken, conf=conf), script)

    def test_clean_match_has_no_flags(self):
        assert self.flags("Linux has no C drive", "Linux has no C drive.") == []

    def test_low_confidence_word_flagged(self):
        ws = words("Linux has no C drive")
        ws[3] = Word(ws[3].start, ws[3].end, "C", 0.3)
        flags = transcribe.review_flags(ws, "Linux has no C drive.")
        assert any(f.kind == "low-confidence" and f.word == "C" for f in flags)

    def test_script_mismatch_flagged_not_replaced(self):
        flags = self.flags("Linux has no sea drive", "Linux has no C drive.")
        assert any(f.kind == "differs-from-script" and f.word == "sea" and f.expected == "C" for f in flags)

    def test_punctuation_and_case_ignored(self):
        assert self.flags("slash home is where", "Slash home, is where!") == []

    def test_extra_spoken_word_flagged(self):
        flags = self.flags("so linux has no C drive", "Linux has no C drive.")
        assert any(f.kind == "differs-from-script" and f.word == "so" for f in flags)

    def test_missing_spoken_word_flagged(self):
        flags = self.flags("Linux has C drive", "Linux has no C drive.")
        assert any(f.kind == "differs-from-script" and f.expected == "no" for f in flags)


class TestCaptionCues:
    def test_groups_words_into_cues_with_real_times(self):
        ws = words("one two three four five six seven eight", step=0.5)
        cues = captions.cues_from_words(ws, max_chars=16, max_lines=2)
        assert cues[0].start == ws[0].start
        assert cues[-1].end == ws[-1].end
        assert all(max(len(l) for l in c.text.split("\n")) <= 16 for c in cues)
        assert all(len(c.text.split("\n")) <= 2 for c in cues)

    def test_cues_never_overlap_and_stay_ordered(self):
        cues = captions.cues_from_words(words("a b c d e f g h i j k l m n o p", step=0.3), max_chars=10)
        assert all(a.end <= b.start + 1e-9 for a, b in zip(cues, cues[1:]))

    def test_all_words_preserved_in_order(self):
        text = "slash home is where your stuff lives each user gets a folder"
        cues = captions.cues_from_words(words(text), max_chars=20)
        assert " ".join(c.text.replace("\n", " ") for c in cues) == text

    def test_break_after_sentence_end(self):
        ws = words("Hello there. Next sentence here")
        cues = captions.cues_from_words(ws, max_chars=60)
        assert cues[0].text == "Hello there."

    def test_break_on_long_pause(self):
        ws = words("one two") + words("three four", start=5.0)
        cues = captions.cues_from_words(ws, max_chars=60)
        assert [c.text for c in cues] == ["one two", "three four"]

    def test_long_word_does_not_loop(self):
        cues = captions.cues_from_words(words("supercalifragilisticexpialidocious ok"), max_chars=10)
        assert cues and cues[0].text.startswith("supercali")

    def test_empty(self):
        assert captions.cues_from_words([]) == []

    def test_offset_applied_for_timeline(self):
        cues = captions.cues_from_words(words("hi there"), offset=10.0)
        assert cues[0].start == 10.0


class TestVtt:
    def test_vtt_header_and_dot_millis(self):
        cues = captions.cues_from_words(words("hi there"))
        vtt = captions.format_vtt(cues)
        assert vtt.startswith("WEBVTT\n")
        assert "00:00:00.000 --> 00:00:00.700" in vtt


class TestRealEngineTypes:
    def test_numpy_floats_from_whisper_can_be_saved(self, tmp_path):
        np = pytest.importorskip("numpy")
        ws = [Word(np.float64(0.0), np.float64(0.26), "Linux", np.float64(0.88))]
        transcribe.save(tmp_path, transcribe.Transcript("01-hook", "sha", ws))
        assert transcribe.load(tmp_path, "01-hook").words[0].end == 0.26
