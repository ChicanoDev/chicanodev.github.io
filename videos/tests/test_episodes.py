import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import vidkit  # noqa: E402


@pytest.mark.parametrize("series,slug", vidkit.EPISODES, ids=[f"{s}/{n}" for s, n in vidkit.EPISODES])
def test_episode_is_complete_and_lint_clean(series, slug):
    folder = vidkit.episode_dir(series, slug)
    tape = folder / "body.tape"
    voiceover = folder / "voiceover.md"
    assert tape.exists(), f"missing {tape}"
    assert voiceover.exists(), f"missing {voiceover}"
    assert vidkit.lint_episode(tape.read_text(), voiceover.read_text()) == []


@pytest.mark.parametrize("series,slug", vidkit.EPISODES, ids=[f"{s}/{n}" for s, n in vidkit.EPISODES])
def test_setup_leaves_the_mounted_repo_directory(series, slug):
    """Docker mounts the repo at /vhs, the start dir. Tapes must cd away before creating files."""
    tape = (vidkit.episode_dir(series, slug) / "body.tape").read_text()
    hidden = tape.split("Hide", 1)[1].split("Show", 1)[0]
    typed = [line.split('"', 1)[1].rsplit('"', 1)[0] if '"' in line else line
             for line in hidden.splitlines() if line.startswith("Type")]
    first_real = [t for t in typed if not t.startswith(("export PS1", "alias "))][0]
    assert first_real.startswith("cd "), f"first setup command is {first_real!r}, not a cd"
