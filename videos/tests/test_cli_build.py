import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import approval  # noqa: E402
import pipeline  # noqa: E402
import vidkit  # noqa: E402
from test_pipeline_integration import world, intro, FakeVhs, FakeEngine, fake_burn, SPOKEN  # noqa: E402,F401


@pytest.fixture
def cli(world, monkeypatch):
    env, folder, vhs, engine = world
    monkeypatch.setattr(pipeline, "docker_env", lambda *a, **k: env)
    return env, folder, vhs, engine


def final_root(env):
    return env.root / "out" / "final"


class TestBuildCommand:
    def test_builds_and_says_not_approved(self, cli, capsys):
        env, *_ = cli
        assert vidkit.main(["build", "demo/01-ep", "--format", "vertical"]) == 0
        out = capsys.readouterr().out
        assert "out/final/vertical/demo-01-ep.mp4" in out and "NOT approved" in out
        assert (final_root(env) / "vertical" / "demo-01-ep.mp4").exists()

    def test_format_both_builds_two_files(self, cli):
        env, *_ = cli
        assert vidkit.main(["build", "demo/01-ep", "--format", "both"]) == 0
        assert (final_root(env) / "horizontal" / "demo-01-ep.mp4").exists()

    def test_flag_values_are_not_mistaken_for_episode_names(self, cli):
        assert vidkit.main(["build", "demo/01-ep", "--format", "vertical", "--brand-placement", "none"]) == 0

    def test_bad_placement_is_a_readable_error(self, cli, capsys):
        assert vidkit.main(["build", "demo/01-ep", "--format", "vertical", "--brand-placement", "middle"]) == 1
        assert "outro" in capsys.readouterr().out

    def test_missing_take_names_the_file_to_record(self, cli, capsys):
        env, folder, *_ = cli
        (folder / "narration" / "02-root.wav").unlink()
        assert vidkit.main(["build", "demo/01-ep", "--format", "vertical"]) == 1
        assert "02-root" in capsys.readouterr().out

    def test_sync_failure_exits_1_with_report_path(self, cli, capsys):
        env, folder, vhs, engine = cli
        vhs.fixed = [1.0, 2.0]
        assert vidkit.main(["build", "demo/01-ep", "--format", "vertical"]) == 1
        assert "sync-report.md" in capsys.readouterr().out

    def test_dry_run_prints_plan_and_writes_nothing(self, cli, capsys):
        env, *_ = cli
        assert vidkit.main(["build", "demo/01-ep", "--dry-run"]) == 0
        assert "WOULD RUN" in capsys.readouterr().out
        assert not (env.root / "out").exists()

    def test_unknown_episode_rejected_like_other_commands(self, cli):
        assert vidkit.main(["build", "nope/99"]) == 2


class TestReviewApproveBacklog:
    def built(self, cli):
        vidkit.main(["build", "demo/01-ep", "--format", "vertical"])

    def test_review_shows_checklist_and_status(self, cli, capsys):
        self.built(cli)
        capsys.readouterr()
        assert vidkit.main(["review", "demo/01-ep"]) == 0
        out = capsys.readouterr().out
        assert "built" in out and "phone" in out.lower() and "demo-01-ep.mp4" in out

    def test_review_before_build_says_what_to_run(self, cli, capsys):
        assert vidkit.main(["review", "demo/01-ep"]) == 1
        assert "build" in capsys.readouterr().out

    def test_approve_then_backlog_lists_it(self, cli, capsys):
        env, *_ = cli
        self.built(cli)
        assert vidkit.main(["approve", "demo/01-ep", "--by", "Dave"]) == 0
        capsys.readouterr()
        assert vidkit.main(["backlog"]) == 0
        out = capsys.readouterr().out
        assert "demo-01-ep" in out and "Dave" in out
        assert approval.current(final_root(env), "demo-01-ep").state == "approved"

    def test_approve_without_build_refuses(self, cli, capsys):
        assert vidkit.main(["approve", "demo/01-ep", "--by", "Dave"]) == 1
        assert "build" in capsys.readouterr().out

    def test_backlog_empty_message(self, cli, capsys):
        assert vidkit.main(["backlog"]) == 0
        assert "nothing approved" in capsys.readouterr().out.lower()

    def test_rebuild_after_new_take_says_approval_voided(self, cli, capsys):
        env, folder, *_ = cli
        from test_narration import synth
        self.built(cli)
        vidkit.main(["approve", "demo/01-ep", "--by", "Dave"])
        synth(folder / "narration" / "03-home.wav", 5.5, lead=0.5, tail=0.5, freq=500, volume=4)
        capsys.readouterr()
        vidkit.main(["build", "demo/01-ep", "--format", "vertical"])
        assert "approval" in capsys.readouterr().out.lower()
        assert approval.current(final_root(env), "demo-01-ep").state == "built"


class TestBatchBuild:
    def test_skips_incomplete_episodes_and_summarizes(self, cli, capsys, monkeypatch):
        env, folder, *_ = cli
        other = env.root / "series" / "demo" / "02-todo"
        other.mkdir(parents=True)
        (other / "voiceover.md").write_text((folder / "voiceover.md").read_text())
        (other / "body.tape").write_text((folder / "body.tape").read_text())
        monkeypatch.setattr(vidkit, "EPISODES", [("demo", "01-ep"), ("demo", "02-todo")])
        assert vidkit.main(["batch-build", "demo", "--format", "vertical"]) == 0
        out = capsys.readouterr().out
        assert "built: demo-01-ep" in out and "skipped" in out and "02-todo" in out

    def test_does_not_touch_approved_unless_forced(self, cli, capsys):
        env, *_ = cli
        vidkit.main(["build", "demo/01-ep", "--format", "vertical"])
        vidkit.main(["approve", "demo/01-ep", "--by", "Dave"])
        stamp = (final_root(env) / "vertical" / "demo-01-ep.mp4").stat().st_mtime_ns
        capsys.readouterr()
        vidkit.main(["batch-build", "demo", "--format", "vertical", "--force"])  # --force rebuilds
        capsys.readouterr()
        vidkit.main(["approve", "demo/01-ep", "--by", "Dave"])
        capsys.readouterr()
        vidkit.main(["batch-build", "demo", "--format", "vertical"])
        out = capsys.readouterr().out
        assert "approved" in out and "skipped" in out


class TestBuildNeedsAName:
    def test_bare_build_refuses_instead_of_building_everything(self, cli, capsys):
        env, folder, vhs, engine = cli
        assert vidkit.main(["build"]) == 2
        assert "episode" in capsys.readouterr().out and vhs.calls == []
