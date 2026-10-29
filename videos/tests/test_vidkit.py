import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import vidkit  # noqa: E402


class TestParseTimestamp:
    def test_minutes_and_seconds(self):
        assert vidkit.parse_timestamp("1:05") == 65

    def test_zero(self):
        assert vidkit.parse_timestamp("0:00") == 0

    def test_fractional_seconds(self):
        assert vidkit.parse_timestamp("0:06.5") == 6.5


class TestEstimateDuration:
    def test_sleep_seconds(self):
        assert vidkit.estimate_duration("Sleep 2s") == pytest.approx(2.0)

    def test_sleep_milliseconds(self):
        assert vidkit.estimate_duration("Sleep 500ms") == pytest.approx(0.5)

    def test_sleep_fractional_seconds(self):
        assert vidkit.estimate_duration("Sleep 1.5s") == pytest.approx(1.5)

    def test_type_uses_default_speed_per_character(self):
        # 5 chars * 100ms
        assert vidkit.estimate_duration('Type "hello"', default_typing_ms=100) == pytest.approx(0.5)

    def test_set_typing_speed_overrides_default(self):
        tape = 'Set TypingSpeed 200ms\nType "hi"'
        assert vidkit.estimate_duration(tape, default_typing_ms=50) == pytest.approx(0.4)

    def test_type_at_speed_overrides_set(self):
        tape = 'Set TypingSpeed 200ms\nType@10ms "hello"'
        assert vidkit.estimate_duration(tape) == pytest.approx(0.05)

    def test_hidden_section_is_not_counted(self):
        tape = 'Hide\nSleep 10s\nType "abc"\nShow\nSleep 1s'
        assert vidkit.estimate_duration(tape) == pytest.approx(1.0)

    def test_comments_and_blank_lines_ignored(self):
        assert vidkit.estimate_duration('# Sleep 9s\n\nSleep 1s') == pytest.approx(1.0)

    def test_keys_cost_nothing(self):
        assert vidkit.estimate_duration("Enter\nCtrl+C\nUp") == 0


class TestParseTapeBeats:
    def test_reads_beat_markers_with_labels(self):
        tape = "# @beat 0:00 Hook\nSleep 1s\n# @beat 0:06 Slash\n"
        assert vidkit.parse_tape_beats(tape) == [(0, "Hook"), (6, "Slash")]

    def test_no_markers_gives_empty_list(self):
        assert vidkit.parse_tape_beats("Sleep 1s") == []


VOICEOVER = """\
# Linux has no C drive

> On screen: ls /

## [0:00-0:05] Hook
Linux has no C drive.
Everything lives under one slash.

## [0:05-0:20] Root
That slash is root, the top of the tree.

## Post copy
Caption for socials. Not narration.
"""


class TestParseVoiceover:
    def test_only_timestamped_headings_become_beats(self):
        beats = vidkit.parse_voiceover(VOICEOVER)
        assert [b.title for b in beats] == ["Hook", "Root"]

    def test_beat_times(self):
        beats = vidkit.parse_voiceover(VOICEOVER)
        assert (beats[0].start, beats[0].end) == (0, 5)
        assert (beats[1].start, beats[1].end) == (5, 20)

    def test_text_joins_lines_and_drops_notes(self):
        beats = vidkit.parse_voiceover(VOICEOVER + "\n## [0:20-0:25] Next\n> note\nHi there.\n")
        assert beats[0].text == "Linux has no C drive. Everything lives under one slash."
        assert beats[2].text == "Hi there."

    def test_post_copy_section_is_excluded_from_last_beat(self):
        beats = vidkit.parse_voiceover(VOICEOVER)
        assert "Caption" not in beats[1].text


def beat(start, end, text):
    return vidkit.Beat(start=start, end=end, title="t", text=text)


class TestMakeCues:
    def test_short_text_is_one_cue_spanning_the_beat(self):
        cues = vidkit.make_cues([beat(0, 5, "Hello there")])
        assert [(c.start, c.end, c.text) for c in cues] == [(0, 5, "Hello there")]

    def test_lines_never_exceed_max_chars(self):
        text = "That slash is root, the top of the tree and every disk hangs off it."
        cues = vidkit.make_cues([beat(0, 10, text)], max_chars=20)
        for cue in cues:
            assert all(len(line) <= 20 for line in cue.text.split("\n"))

    def test_cue_has_at_most_two_lines(self):
        text = "word " * 40
        cues = vidkit.make_cues([beat(0, 10, text.strip())], max_chars=20)
        assert all(len(c.text.split("\n")) <= 2 for c in cues)

    def test_cues_tile_the_beat_without_gaps_or_overlap(self):
        text = "word " * 40
        cues = vidkit.make_cues([beat(5, 15, text.strip())], max_chars=20)
        assert cues[0].start == 5 and cues[-1].end == 15
        for a, b in zip(cues, cues[1:]):
            assert a.end == pytest.approx(b.start)

    def test_longer_cues_get_more_time(self):
        cues = vidkit.make_cues([beat(0, 10, "aaaa bbbb cccc dddd eeee ffff")], max_chars=9)
        assert len(cues) == 2
        assert cues[0].end - cues[0].start > cues[1].end - cues[1].start

    def test_multiple_beats_stay_in_their_windows(self):
        cues = vidkit.make_cues([beat(0, 5, "One"), beat(5, 9, "Two")])
        assert (cues[1].start, cues[1].end) == (5, 9)


class TestFormatSrt:
    def test_numbers_and_timestamps(self):
        out = vidkit.format_srt([vidkit.Cue(0, 5.5, "Hi"), vidkit.Cue(65.25, 70, "Bye\nnow")])
        assert out == (
            "1\n00:00:00,000 --> 00:00:05,500\nHi\n\n"
            "2\n00:01:05,250 --> 00:01:10,000\nBye\nnow\n"
        )

    def test_hours_roll_over(self):
        out = vidkit.format_srt([vidkit.Cue(3661, 3662, "x")])
        assert "01:01:01,000 --> 01:01:02,000" in out


class TestOffsetCues:
    def test_shifts_both_edges(self):
        shifted = vidkit.offset_cues([vidkit.Cue(1, 2, "a")], 10)
        assert (shifted[0].start, shifted[0].end, shifted[0].text) == (11, 12, "a")
