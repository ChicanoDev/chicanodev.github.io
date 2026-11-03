import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import vidkit  # noqa: E402


@pytest.fixture(autouse=True)
def plain(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")


def run(capsys, *argv):
    code = vidkit.main(list(argv))
    return code, capsys.readouterr().out


@pytest.mark.parametrize("argv", [[], ["--help"], ["-h"], ["help"]])
def test_main_help_exits_zero_and_lists_every_command(capsys, argv):
    code, out = run(capsys, *argv)
    assert code == 0
    for name in vidkit.COMMANDS:
        assert name in out
    for group in ("GETTING STARTED", "VIDEO PRODUCTION", "QUALITY & REVIEW", "SERIES & LEGACY", "EXAMPLES"):
        assert group in out


def test_every_command_is_described():
    assert set(vidkit.COMMAND_INFO) == set(vidkit.COMMANDS)


@pytest.mark.parametrize("name", sorted(vidkit.COMMANDS))
@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_command_help_exits_zero_with_usage_and_example(capsys, name, flag):
    code, out = run(capsys, name, flag)
    assert code == 0
    assert f"vidkit.py {name}" in out
    assert "Examples" in out


def test_command_help_does_not_need_the_venv(monkeypatch, capsys):
    def boom(command):
        raise AssertionError("help must not switch to the venv")
    monkeypatch.setattr(vidkit, "_ensure_env", boom)
    code, _ = run(capsys, "transcribe", "--help")
    assert code == 0


def test_unknown_command_suggests_close_match(capsys):
    code, out = run(capsys, "buidl")
    assert code == 2
    assert "build" in out
    assert "Traceback" not in out


def test_unknown_command_without_match_points_to_help(capsys):
    code, out = run(capsys, "zzzzzz")
    assert code == 2
    assert "--help" in out


def test_no_ansi_when_no_color_or_piped(capsys):
    _, out = run(capsys)
    assert "\x1b" not in out


def test_help_works_without_rich(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "rich", None)
    code, out = run(capsys)
    assert code == 0 and "vidkit" in out.lower()


def test_help_survives_dumb_terminal(monkeypatch, capsys):
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setenv("COLUMNS", "40")
    code, out = run(capsys, "build", "--help")
    assert code == 0
    assert all(len(line) <= 40 for line in out.splitlines())
