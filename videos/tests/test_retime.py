import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import retime  # noqa: E402
import vidkit  # noqa: E402

TAPE = """# header comment
Hide
Type "setup"
Enter
Show

# @beat 0:00 Hook
Type "# hi"
Sleep 700ms
Enter
Sleep 2s

# @beat 0:05 Root
Type "ls /"
Enter
Sleep 4s
Type "# top"
Enter
Sleep 3s
"""
# typing: 70ms/char. Hook: 4 chars=0.28 + 0.7 + 2.0 = 2.98.  Root: 4*0.07=0.28 + 4 + 5*0.07=0.35 + 3 = 7.63


def beats(tape=TAPE):
    return retime.split_beats(tape)


class TestSplit:
    def test_preamble_and_titles(self):
        pre, blocks = beats()
        assert "Hide" in "\n".join(pre)
        assert [b.title for b in blocks] == ["Hook", "Root"]

    def test_natural_seconds(self):
        _, blocks = beats()
        assert [round(b.seconds, 2) for b in blocks] == [2.98, 7.63]

    def test_hidden_preamble_not_counted(self):
        _, blocks = beats()
        assert blocks[0].seconds < 3


class TestRetime:
    def total(self, text):
        return vidkit.estimate_duration(text)

    def test_longer_narration_extends_last_hold(self):
        new, plans = retime.retime_tape(TAPE, [5.0, 7.63])
        _, blocks = retime.split_beats(new)
        assert blocks[0].seconds == pytest.approx(5.0, abs=0.01)
        assert plans[0].action == "hold"

    def test_only_last_sleep_of_beat_changes_when_extending(self):
        new, _ = retime.retime_tape(TAPE, [5.0, 7.63])
        lines = [l for l in new.splitlines() if l.startswith("Sleep")]
        assert lines[0] == "Sleep 700ms"

    def test_shorter_narration_scales_sleeps_down(self):
        new, plans = retime.retime_tape(TAPE, [2.98, 6.0])
        _, blocks = retime.split_beats(new)
        assert blocks[1].seconds == pytest.approx(6.0, abs=0.02)
        assert plans[1].action == "shrink" and 0.5 <= plans[1].scale < 1

    def test_typing_is_never_changed(self):
        new, _ = retime.retime_tape(TAPE, [2.98, 6.0])
        assert [l for l in new.splitlines() if l.startswith("Type")] == [l for l in TAPE.splitlines() if l.startswith("Type")]

    def test_exact_match_leaves_tape_identical(self):
        new, plans = retime.retime_tape(TAPE, [2.98, 7.63])
        assert new == TAPE
        assert {p.action for p in plans} == {"keep"}

    def test_too_short_narration_stops_with_actionable_report(self):
        with pytest.raises(retime.SyncError) as err:
            retime.retime_tape(TAPE, [2.98, 2.0])
        msg = str(err.value)
        assert "Root" in msg and "2.0" in msg and "7.6" in msg and "least" in msg

    def test_beat_count_mismatch_is_an_error(self):
        with pytest.raises(retime.SyncError) as err:
            retime.retime_tape(TAPE, [5.0])
        assert "2 beats" in str(err.value) and "1 narration" in str(err.value)

    def test_original_text_not_mutated(self):
        before = TAPE
        retime.retime_tape(TAPE, [9.0, 9.0])
        assert TAPE == before

    def test_no_sleep_in_beat_appends_hold(self):
        tape = '# @beat 0:00 A\nType "ab"\nEnter\n'
        new, _ = retime.retime_tape(tape, [3.0])
        assert retime.split_beats(new)[1][0].seconds == pytest.approx(3.0, abs=0.01)

    def test_applies_per_beat_deltas_without_drift(self):
        periods = [4.1, 5.2]
        new, _ = retime.retime_tape(TAPE, periods)
        _, blocks = retime.split_beats(new)
        assert sum(b.seconds for b in blocks) == pytest.approx(sum(periods), abs=0.03)


class TestPeriods:
    def test_periods_include_pause_except_last_plus_tail(self):
        assert retime.beat_periods([2.0, 3.0, 1.0], pause=0.3, tail=0.5) == pytest.approx([2.3, 3.3, 1.5])

    def test_single(self):
        assert retime.beat_periods([2.0], pause=0.3, tail=0.5) == pytest.approx([2.5])


class TestAnchorOffset:
    CLEAR = """# @beat 0:05 Root
Type "clear"
Enter
Sleep 300ms
Type "ls /"
Enter
"""

    def test_time_from_marker_to_clear_enter(self):
        _, blocks = retime.split_beats(self.CLEAR)
        assert retime.anchor_offset(blocks[0]) == pytest.approx(0.35)  # "clear" = 5 chars x 70ms

    def test_none_when_beat_does_not_start_with_clear(self):
        _, blocks = retime.split_beats('# @beat 0:00 Hook\nType "# hi"\nEnter\n')
        assert retime.anchor_offset(blocks[0]) is None
