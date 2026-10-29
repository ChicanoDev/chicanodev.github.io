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
