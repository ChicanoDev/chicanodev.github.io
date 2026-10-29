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


def make_episode(seconds=70, words=180, typed="ls", beat_at=0):
    """A minimal valid (tape, voiceover) pair; override pieces to break one rule."""
    tape = f"# @beat 0:00 Hook\nType \"{typed}\"\nSleep {seconds}s\n"
    vo = f"## [0:00-1:10] Hook\n{' '.join(['word'] * words)}\n"
    return tape, vo


class TestLintEpisode:
    def test_valid_episode_has_no_problems(self):
        tape, vo = make_episode(seconds=70)
        assert vidkit.lint_episode(tape, vo) == []

    def test_too_short(self):
        tape, vo = make_episode(seconds=30)
        assert any("duration" in p for p in vidkit.lint_episode(tape, vo))

    def test_too_long(self):
        tape, vo = make_episode(seconds=120)
        assert any("duration" in p for p in vidkit.lint_episode(tape, vo))

    def test_voiceover_too_few_words(self):
        tape, vo = make_episode(words=50)
        assert any("words" in p for p in vidkit.lint_episode(tape, vo))

    def test_voiceover_too_many_words(self):
        tape, vo = make_episode(words=400)
        assert any("words" in p for p in vidkit.lint_episode(tape, vo))

    def test_typed_line_too_wide_for_vertical(self):
        tape, vo = make_episode(typed="x" * 40)
        assert any("32" in p for p in vidkit.lint_episode(tape, vo))

    def test_hidden_setup_lines_are_exempt_from_width_limit(self):
        tape, vo = make_episode()
        tape = "Hide\nType \"" + "x" * 80 + "\"\nShow\n" + tape
        assert vidkit.lint_episode(tape, vo) == []

    def test_beat_count_mismatch(self):
        tape, vo = make_episode()
        tape += "# @beat 0:30 Extra\n"
        assert any("beat count" in p for p in vidkit.lint_episode(tape, vo))

    def test_beat_marker_must_match_voiceover_start(self):
        tape, vo = make_episode()
        tape = tape.replace("# @beat 0:00", "# @beat 0:10")
        assert any("starts at" in p for p in vidkit.lint_episode(tape, vo))

    def test_beat_marker_must_match_estimated_time(self):
        tape = 'Sleep 5s\n# @beat 0:20 Late\nSleep 60s\n'
        vo = f"## [0:20-1:20] Late\n{' '.join(['word'] * 180)}\n"
        assert any("estimate" in p for p in vidkit.lint_episode(tape, vo))


class TestBuildTape:
    def test_output_then_settings_then_body(self):
        out = vidkit.build_tape("Set FontSize 46", "Type \"ls\"", "build/x/v.mp4")
        assert out.splitlines()[0] == "Output build/x/v.mp4"
        assert out.index("Set FontSize 46") < out.index('Type "ls"')


class TestCaptionStyle:
    """libass treats SRT as a 288px-tall canvas, so pixel sizes must be scaled down."""

    def parse(self, style):
        return dict(part.split("=", 1) for part in style.split(","))

    def test_288px_video_keeps_pixel_values(self):
        style = self.parse(vidkit.caption_force_style(288, font_px=20, margin_px=10, outline_px=2))
        assert float(style["Fontsize"]) == pytest.approx(20)
        assert float(style["MarginV"]) == pytest.approx(10)
        assert float(style["Outline"]) == pytest.approx(2)

    def test_taller_video_scales_values_down(self):
        style = self.parse(vidkit.caption_force_style(1920, font_px=96, margin_px=480, outline_px=6))
        assert float(style["Fontsize"]) == pytest.approx(96 * 288 / 1920)
        assert float(style["MarginV"]) == pytest.approx(480 * 288 / 1920)

    def test_caption_is_bottom_centered(self):
        style = self.parse(vidkit.caption_force_style(1080, font_px=40, margin_px=48, outline_px=3))
        assert style["Alignment"] == "2"


class TestMergeCueSets:
    def test_second_clip_is_shifted_by_first_duration_plus_gap(self):
        a = [vidkit.Cue(0, 5, "a1")]
        b = [vidkit.Cue(0, 4, "b1"), vidkit.Cue(4, 8, "b2")]
        merged = vidkit.merge_cue_sets([(a, 60.0), (b, 70.0)], gap=2.0)
        assert [(c.start, c.end, c.text) for c in merged] == [(0, 5, "a1"), (62, 66, "b1"), (66, 70, "b2")]

    def test_third_clip_accumulates_both_earlier_offsets(self):
        sets = [([vidkit.Cue(0, 1, "x")], 10.0)] * 3
        merged = vidkit.merge_cue_sets(sets, gap=1.0)
        assert [c.start for c in merged] == [0, 11, 22]

    def test_single_clip_is_unchanged(self):
        cues = [vidkit.Cue(1, 2, "only")]
        assert vidkit.merge_cue_sets([(cues, 30.0)]) == cues


class TestParseTitle:
    def test_first_h1(self):
        assert vidkit.parse_title("# Linux has no C drive\n\n## [0:00-0:05] Hook\n") == "Linux has no C drive"


class TestCheckClip:
    def test_good_vertical_clip(self):
        assert vidkit.check_clip("vertical", 1080, 1920, 70.4, 70.0) == []

    def test_good_horizontal_clip(self):
        assert vidkit.check_clip("horizontal", 1920, 1080, 69.0, 70.0) == []

    def test_wrong_resolution(self):
        problems = vidkit.check_clip("vertical", 1920, 1080, 70.0, 70.0)
        assert any("resolution" in p for p in problems)

    def test_duration_drift_beyond_tolerance(self):
        problems = vidkit.check_clip("horizontal", 1920, 1080, 75.0, 70.0)
        assert any("duration" in p for p in problems)

    def test_drift_within_tolerance_is_fine(self):
        assert vidkit.check_clip("horizontal", 1920, 1080, 71.4, 70.0) == []


class TestScaleCues:
    def test_scales_both_edges_by_factor(self):
        scaled = vidkit.scale_cues([vidkit.Cue(10, 20, "a")], 0.9)
        assert scaled[0].start == pytest.approx(9.0)
        assert scaled[0].end == pytest.approx(18.0)
        assert scaled[0].text == "a"

    def test_last_cue_ends_at_clip_duration(self):
        beats = [beat(0, 40, "one two"), beat(40, 80, "three four")]
        cues = vidkit.make_cues(beats)
        scaled = vidkit.scale_cues(cues, 77.0 / 80.0)
        assert scaled[-1].end == pytest.approx(77.0)


class TestCheckClipRelativeTolerance:
    def test_three_percent_shortfall_is_normal_render_drift(self):
        assert vidkit.check_clip("horizontal", 1920, 1080, 72.1, 74.3) == []

    def test_ten_percent_is_a_real_problem(self):
        assert any("duration" in p for p in vidkit.check_clip("horizontal", 1920, 1080, 68.0, 76.0))
