import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import measure  # noqa: E402


def fake_terminal(path, seconds=12, clears=(4.0, 8.0), fps=25, size="320x180"):
    """Dark screen where 'text' (a white box) grows after t=0.5 and vanishes at each clear time."""
    edges = [0.0, *clears, seconds]
    parts = []
    for a, b in zip(edges, edges[1:]):
        start = a + 0.4
        # two 'lines' appear 0.5s apart after each clear, like typed output
        parts.append(f"drawbox=x=iw*0.06:y=ih*0.10:w=iw*0.6:h=ih*0.04:color=white:t=fill:enable='between(t,{start},{b - 0.0001})'")
        parts.append(f"drawbox=x=iw*0.06:y=ih*0.20:w=iw*0.8:h=ih*0.04:color=white:t=fill:enable='between(t,{start + 0.5},{b - 0.0001})'")
    vf = ",".join(parts)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=0x282a36:s={size}:r={fps}:d={seconds}",
                    "-vf", vf, "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


class TestInkSeries:
    def test_one_value_per_frame(self, tmp_path):
        series = measure.ink_series(fake_terminal(tmp_path / "t.mp4"), fps=25)
        assert len(series) == pytest.approx(12 * 25, abs=2)

    def test_ink_rises_after_text_appears_and_falls_on_clear(self, tmp_path):
        series = measure.ink_series(fake_terminal(tmp_path / "t.mp4"), fps=25)
        assert series[int(3.9 * 25)] > series[int(0.2 * 25)]
        assert series[int(4.05 * 25)] < series[int(3.9 * 25)]


class TestFindClears:
    def test_finds_clear_times_within_a_frame_or_two(self, tmp_path):
        series = measure.ink_series(fake_terminal(tmp_path / "t.mp4", clears=(4.0, 8.0)), fps=25)
        found = measure.find_clears(series, 25, [4.0, 8.0])
        assert found[0] == pytest.approx(4.0, abs=0.1)
        assert found[1] == pytest.approx(8.0, abs=0.1)

    def test_searches_near_expected_not_globally(self, tmp_path):
        series = measure.ink_series(fake_terminal(tmp_path / "t.mp4", clears=(4.0, 8.0)), fps=25)
        found = measure.find_clears(series, 25, [4.4])  # slightly off guess
        assert found[0] == pytest.approx(4.0, abs=0.1)

    def test_missing_clear_is_none(self, tmp_path):
        series = measure.ink_series(fake_terminal(tmp_path / "t.mp4", clears=(4.0,)), fps=25)
        assert measure.find_clears(series, 25, [10.5], window=1.0) == [None]

    def test_late_render_is_measured_not_assumed(self, tmp_path):
        series = measure.ink_series(fake_terminal(tmp_path / "t.mp4", clears=(4.6,)), fps=25)
        assert measure.find_clears(series, 25, [4.0], window=1.5)[0] == pytest.approx(4.6, abs=0.1)

    def test_early_render_is_still_found_when_the_error_has_piled_up(self, tmp_path):
        # a render that is 2.4s ahead of the guess (drift adds up over beats) must still be measured, or
        # that beat never gets corrected
        series = measure.ink_series(fake_terminal(tmp_path / "t.mp4", clears=(4.0, 12.0)), fps=25)
        assert measure.find_clears(series, 25, [6.4])[0] == pytest.approx(4.0, abs=0.1)

    def test_each_search_follows_the_shift_found_so_far(self, tmp_path):
        # the render runs shorter than the tape estimate, so the gap grows beat by beat (2s, 3.5s, 5s here).
        # Searching each clear around the previous one's shift keeps finding them; a fixed guess loses them.
        series = measure.ink_series(fake_terminal(tmp_path / "t.mp4", seconds=28, clears=(4.0, 12.0, 20.0)), fps=25)
        found = measure.find_clears_chained(series, 25, [6.0, 15.5, 25.0])
        assert found == [pytest.approx(4.0, abs=0.1), pytest.approx(12.0, abs=0.1), pytest.approx(20.0, abs=0.1)]
        assert measure.find_clears(series, 25, [6.0, 15.5, 25.0])[1:] == [None, None]

    def test_chained_search_keeps_going_after_a_miss(self, tmp_path):
        series = measure.ink_series(fake_terminal(tmp_path / "t.mp4", seconds=28, clears=(4.0, 20.0)), fps=25)
        found = measure.find_clears_chained(series, 25, [6.0, 13.0, 22.0])
        assert found[0] == pytest.approx(4.0, abs=0.1)
        assert found[1] is None
        assert found[2] == pytest.approx(20.0, abs=0.1)


class TestDrift:
    def test_reports_each_beat_against_target(self):
        rep = measure.drift_report(measured=[0.0, 5.2, 9.0], targets=[0.0, 5.0, 9.5], total=(14.0, 14.0))
        assert [round(r.drift, 2) for r in rep.beats] == [0.0, 0.2, -0.5]

    def test_within_tolerance_passes(self):
        rep = measure.drift_report([0.0, 5.2], [0.0, 5.0], total=(10.0, 10.0))
        assert rep.ok

    def test_beat_over_tolerance_fails(self):
        rep = measure.drift_report([0.0, 5.5], [0.0, 5.0], total=(10.0, 10.0), beat_tol=0.3)
        assert not rep.ok and "beat 2" in rep.problems[0]

    def test_total_over_tolerance_fails(self):
        rep = measure.drift_report([0.0, 5.0], [0.0, 5.0], total=(10.7, 10.0), total_tol=0.5)
        assert not rep.ok and "overall" in rep.problems[0]

    def test_unmeasured_beat_fails_with_hint(self):
        rep = measure.drift_report([0.0, None], [0.0, 5.0], total=(10.0, 10.0))
        assert not rep.ok and "could not find" in rep.problems[0]

    def test_markdown_report_names_segments_and_numbers(self):
        rep = measure.drift_report([0.0, 5.5], [0.0, 5.0], total=(10.0, 10.0), titles=["Hook", "Root"])
        md = rep.markdown()
        assert "Root" in md and "5.50" in md and "5.00" in md


class TestCorrections:
    def test_late_beat_shortens_previous_period_by_half_the_error(self):
        # beat 1 was planned 5.0s but actually took 5.4s. The render jitters, so only half the 0.4s error is
        # corrected per pass (full correction chased the noise and overshot).
        new = measure.corrected_periods([5.0, 6.0], measured=[0.0, 5.4], total_end=11.4)
        assert new[0] == pytest.approx(4.8)

    def test_last_period_uses_total_length(self):
        new = measure.corrected_periods([5.0, 6.0], measured=[0.0, 5.0], total_end=11.5)
        assert new[1] == pytest.approx(5.75)

    def test_beat_that_hits_the_narration_target_is_left_alone_on_later_passes(self):
        # first pass asked for 5.0s, render came out 0.4s short, so pass 2 asked for 5.4s and got exactly 5.0s.
        # Judged against the narration (5.0s) that is done; judged against the 5.4s request it looks 0.4s short.
        new = measure.corrected_periods([5.4, 6.0], measured=[0.0, 5.0], total_end=11.0, targets=[5.0, 6.0])
        assert new[0] == pytest.approx(5.4)

    def test_repeated_corrections_converge_despite_render_jitter(self):
        # a render that always runs 0.4s long, plus jitter of +-0.3s: full gain swings, damped gain settles
        jitter = [0.3, -0.3, 0.3, -0.3]
        period = 5.0
        for noise in jitter:
            actual = period + 0.4 + noise
            period = measure.corrected_periods([period], [0.0], total_end=actual, targets=[5.0])[0]
        # half of the final +-0.3 jitter stays in the period; full gain left it 1.2s off
        assert abs((period + 0.4) - 5.0) < 0.5

    def test_on_target_unchanged(self):
        assert measure.corrected_periods([5.0, 6.0], [0.0, 5.0], 11.0) == pytest.approx([5.0, 6.0])


    def test_unmeasured_beat_leaves_neighbouring_periods_alone(self):
        assert measure.corrected_periods([5.0, 6.0, 4.0], [0.0, None, 11.0], 15.0) == pytest.approx([5.0, 6.0, 4.0])
