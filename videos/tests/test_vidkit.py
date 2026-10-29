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
