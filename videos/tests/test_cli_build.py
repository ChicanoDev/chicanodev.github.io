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


URL = "https://www.youtube.com/shorts/EXAMPLE"


class TestPublishCommand:
    def ready(self, cli, fmt="vertical"):
        vidkit.main(["build", "demo/01-ep", "--format", fmt])
        vidkit.main(["approve", "demo/01-ep", "--by", "Reviewer"])

    def status_file(self, cli):
        return final_root(cli[0]) / "demo-01-ep.status.json"

    def test_publish_then_backlog_drops_youtube_keeps_instagram(self, cli, capsys):
        self.ready(cli)
        capsys.readouterr()
        assert vidkit.main(["publish", "demo/01-ep", "--platform", "youtube", "--url", URL, "--by", "Dave"]) == 0
        out = capsys.readouterr().out
        assert "demo/01-ep" in out and "youtube" in out and "vertical" in out and URL in out
        assert "nothing was uploaded" in out.lower()
        assert vidkit.main(["backlog", "--platform", "youtube"]) == 0
        assert "already published" in capsys.readouterr().out.lower()
        assert vidkit.main(["backlog"]) == 0
        out = capsys.readouterr().out
        assert "instagram" in out and "vertical/demo-01-ep.mp4" in out and "youtube" not in out.split("instagram")[0].split("demo-01-ep", 1)[1]

    def test_status_shows_history_and_series_counts(self, cli, capsys, monkeypatch):
        monkeypatch.setattr(vidkit, "EPISODES", [("demo", "01-ep"), ("demo", "02-todo")])
        self.ready(cli)
        vidkit.main(["publish", "demo/01-ep", "--platform", "youtube", "--url", URL, "--at", "2026-11-04T20:00:00Z"])
        capsys.readouterr()
        assert vidkit.main(["status", "demo"]) == 0
        out = capsys.readouterr().out
        assert "demo/01-ep" in out and "approved" in out and URL in out and "2026-11-04T20:00:00+00:00" in out
        assert "demo/02-todo" in out and "not built" in out
        assert "Ever published: 1/2 episodes" in out and "Current exports published: 1/2 episodes" in out
        assert "compiled" in out.lower()
        assert vidkit.main(["status", "demo", "--platform", "instagram", "--format", "vertical"]) == 0
        out = capsys.readouterr().out
        assert "Ever published: 0/2 episodes" in out and "youtube" not in out

    def test_duplicate_is_noop_even_if_git_name_changed(self, cli, capsys, monkeypatch):
        self.ready(cli)
        monkeypatch.setattr(vidkit, "_who", lambda argv: "Old Name")
        vidkit.main(["publish", "demo/01-ep", "--platform", "youtube"])
        before = self.status_file(cli).read_bytes()
        monkeypatch.setattr(vidkit, "_who", lambda argv: "New Name")
        capsys.readouterr()
        assert vidkit.main(["publish", "demo/01-ep", "--platform", "youtube"]) == 0
        assert "existing record" in capsys.readouterr().out.lower()
        assert self.status_file(cli).read_bytes() == before

    def test_conflicting_url_exits_1_without_write(self, cli, capsys):
        self.ready(cli)
        vidkit.main(["publish", "demo/01-ep", "--platform", "youtube", "--url", URL])
        before = self.status_file(cli).read_bytes()
        assert vidkit.main(["publish", "demo/01-ep", "--platform", "youtube", "--url", "https://x.example/y"]) == 1
        assert self.status_file(cli).read_bytes() == before

    def test_unapproved_exits_1(self, cli, capsys):
        vidkit.main(["build", "demo/01-ep", "--format", "vertical"])
        before = self.status_file(cli).read_bytes()
        assert vidkit.main(["publish", "demo/01-ep", "--platform", "youtube"]) == 1
        assert "approve" in capsys.readouterr().out
        assert self.status_file(cli).read_bytes() == before

    @pytest.mark.parametrize("argv", [
        ["demo/01-ep"],                                                   # no platform
        ["demo/01-ep", "--platform"],                                     # missing value
        ["demo/01-ep", "--platform", "--url", URL],                       # flag as value
        ["demo/01-ep", "--platform", "youtube", "--platform", "instagram"],
        ["demo/01-ep", "--platform", "tiktok"],
        ["demo/01-ep", "--platform", "youtube", "--format", "both"],
        ["demo/01-ep", "--platform", "youtube", "--format", "square"],
        ["demo/01-ep", "--platform", "youtube", "--url", "not a url"],
        ["demo/01-ep", "--platform", "youtube", "--url", ""],
        ["demo/01-ep", "--platform", "youtube", "--at", "2026-11-04"],
        ["demo/01-ep", "--platform", "youtube", "--at", "2099-01-01T00:00:00Z"],
        ["demo/01-ep", "--platform", "youtube", "--force"],               # unknown option
        ["demo", "--platform", "youtube"],                                # series selector
        ["demo/01-ep", "01-ep", "--platform", "youtube"],                 # multiple selectors
        ["nope/99", "--platform", "youtube"],
        ["--platform", "youtube"],                                        # no selector
    ])
    def test_usage_errors_exit_2_without_write(self, cli, capsys, argv):
        self.ready(cli)
        before = self.status_file(cli).read_bytes()
        assert vidkit.main(["publish", *argv]) == 2
        assert self.status_file(cli).read_bytes() == before

    def test_series_with_one_episode_still_rejected(self, cli, capsys):
        self.ready(cli)
        assert vidkit.main(["publish", "demo", "--platform", "youtube"]) == 2
        assert "one episode" in capsys.readouterr().out

    def test_corrupt_status_exits_1_and_keeps_file(self, cli, capsys):
        self.ready(cli)
        self.status_file(cli).write_text("{broken")
        assert vidkit.main(["publish", "demo/01-ep", "--platform", "youtube"]) == 1
        assert "demo-01-ep.status.json" in capsys.readouterr().out
        assert self.status_file(cli).read_text() == "{broken"


class TestStrictBacklogAndStatus:
    @pytest.mark.parametrize("cmd", ["backlog", "status"])
    @pytest.mark.parametrize("argv", [["--platform"], ["--platform", "tiktok"], ["--format", "both"],
                                      ["--platform", "youtube", "--platform", "youtube"], ["--bogus"]])
    def test_bad_filters_exit_2(self, cli, capsys, cmd, argv):
        assert vidkit.main([cmd, *argv]) == 2

    def test_filter_value_is_not_an_episode_selector(self, cli, capsys):
        assert vidkit.main(["backlog", "--platform", "youtube"]) == 0
        assert vidkit.main(["status", "--platform", "youtube", "--format", "vertical"]) == 0

    def test_backlog_takes_no_selector(self, cli, capsys):
        assert vidkit.main(["backlog", "demo"]) == 2

    def test_status_rejects_two_selectors_and_unknown(self, cli, capsys):
        assert vidkit.main(["status", "demo", "demo/01-ep"]) == 2
        assert vidkit.main(["status", "nope"]) == 2

    def test_backlog_empty_reasons(self, cli, capsys):
        assert vidkit.main(["backlog"]) == 0
        assert "nothing approved" in capsys.readouterr().out.lower()
        vidkit.main(["build", "demo/01-ep", "--format", "vertical"])
        vidkit.main(["approve", "demo/01-ep", "--by", "R"])
        capsys.readouterr()
        assert vidkit.main(["backlog", "--format", "horizontal"]) == 0
        assert "no approved horizontal exports" in capsys.readouterr().out.lower()


class TestReviewApproveMention:
    def test_reapprove_of_published_identical_does_not_promise_backlog(self, cli, capsys):
        vidkit.main(["build", "demo/01-ep", "--format", "vertical"])
        vidkit.main(["approve", "demo/01-ep", "--by", "R"])
        assert "pending upload" in capsys.readouterr().out.lower()
        for p in ("youtube", "instagram"):
            vidkit.main(["publish", "demo/01-ep", "--platform", p])
        vidkit.main(["build", "demo/01-ep", "--format", "vertical", "--force"])
        capsys.readouterr()
        vidkit.main(["approve", "demo/01-ep", "--by", "R"])
        out = capsys.readouterr().out.lower()
        assert "already published" in out and "pending upload" not in out

    def test_review_shows_publication_summary(self, cli, capsys):
        vidkit.main(["build", "demo/01-ep", "--format", "vertical"])
        vidkit.main(["approve", "demo/01-ep", "--by", "R"])
        vidkit.main(["publish", "demo/01-ep", "--platform", "youtube", "--url", URL])
        capsys.readouterr()
        vidkit.main(["review", "demo/01-ep"])
        out = capsys.readouterr().out
        assert "youtube" in out and URL in out and "published" in out.lower()
