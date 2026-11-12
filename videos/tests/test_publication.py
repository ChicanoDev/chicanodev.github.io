import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import approval  # noqa: E402
import narration  # noqa: E402
import publication  # noqa: E402

BUILT = "2026-10-29T12:00:00"
NOW = datetime(2026, 11, 4, 21, 0, tzinfo=timezone.utc)
URL = "https://www.youtube.com/shorts/EXAMPLE"


@pytest.fixture
def root(tmp_path):
    return tmp_path / "final"


def export(root, fmt, data):
    f = root / fmt / f"ep.mp4"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return f


def build(root, key="k1", qa=(), **formats):
    files = {fmt: export(root, fmt, data) for fmt, data in formats.items()}
    return approval.record_build(root, "ep", key, files, list(qa), now=BUILT)


def approved(root, key="k1", **formats):
    build(root, key, **(formats or {"vertical": b"v1"}))
    return approval.approve(root, "ep", "Reviewer", now=BUILT)


def pub(root, platform="youtube", fmt="vertical", **kw):
    kw.setdefault("now", NOW)
    kw.setdefault("default_by", lambda: "Git User")
    return publication.record(root, "ep", platform, fmt, **kw)


def status_bytes(root):
    p = root / "ep.status.json"
    return p.read_bytes() if p.exists() else None


class TestParseAt:
    def test_z_and_offset_normalize_to_utc(self):
        assert publication.parse_at("2026-11-04T14:00:00-06:00", NOW) == "2026-11-04T20:00:00+00:00"
        assert publication.parse_at("2026-11-04T20:00:00Z", NOW) == "2026-11-04T20:00:00+00:00"

    @pytest.mark.parametrize("bad", ["2026-11-04", "2026-11-04T14:00:00", "yesterday", ""])
    def test_rejects_date_only_naive_and_garbage_with_example(self, bad):
        with pytest.raises(publication.PublishError) as err:
            publication.parse_at(bad, NOW)
        assert err.value.code == 2 and "2026-11-04T14:00:00-06:00" in str(err.value)

    def test_rejects_future(self):
        with pytest.raises(publication.PublishError) as err:
            publication.parse_at("2026-11-04T22:00:00Z", NOW)
        assert err.value.code == 2 and "future" in str(err.value)


class TestCheckUrl:
    def test_strips_whitespace(self):
        assert publication.check_url(f"  {URL} ") == URL

    @pytest.mark.parametrize("bad", ["", "   ", "youtube.com/x", "ftp://host/x", "https://", "https://u:p@host/x",
                                     "https://user@host/x", "/shorts/x"])
    def test_rejects(self, bad):
        with pytest.raises(publication.PublishError) as err:
            publication.check_url(bad)
        assert err.value.code == 2


class TestRecord:
    def test_records_every_field_and_approval_snapshot(self, root):
        approved(root)
        entry, created = pub(root, url=URL, at="2026-11-04T14:00:00-06:00", by="Dave")
        assert created
        assert entry == {
            "platform": "youtube", "format": "vertical", "published_at": "2026-11-04T20:00:00+00:00",
            "recorded_at": "2026-11-04T21:00:00+00:00", "published_by": "Dave", "url": URL, "content_key": "k1",
            "artifact_path": "vertical/ep.mp4", "artifact_sha256": narration.file_sha(root / "vertical/ep.mp4"),
            "approved_at": BUILT, "approved_by": "Reviewer"}
        assert approval.current(root, "ep").publications == [entry]

    def test_defaults_actor_time_and_no_url(self, root):
        approved(root)
        entry, _ = pub(root)
        assert entry["published_by"] == "Git User" and entry["url"] is None
        assert entry["published_at"] == entry["recorded_at"] == "2026-11-04T21:00:00+00:00"

    def test_does_not_change_approval(self, root):
        before = approved(root)
        pub(root)
        after = approval.current(root, "ep")
        assert (after.state, after.approved_at, after.approved_by) == ("approved", before.approved_at, before.approved_by)

    @pytest.mark.parametrize("case", ["unbuilt", "unapproved", "failed-qa", "altered", "missing", "absent-format"])
    def test_refuses_without_writing(self, root, case):
        if case == "unapproved":
            build(root, vertical=b"v1")
        elif case == "failed-qa":
            build(root, qa=["silent"], vertical=b"v1")
        elif case != "unbuilt":
            approved(root)
        if case == "altered":
            (root / "vertical/ep.mp4").write_bytes(b"edited")
        if case == "missing":
            (root / "vertical/ep.mp4").unlink()
        before = status_bytes(root)
        with pytest.raises(publication.PublishError) as err:
            pub(root, fmt="horizontal" if case == "absent-format" else "vertical")
        assert err.value.code == 1
        assert status_bytes(root) == before
        hint = {"unbuilt": "build", "unapproved": "approve", "failed-qa": "rebuild", "altered": "rebuild",
                "missing": "rebuild", "absent-format": "--format horizontal"}[case]
        assert hint in str(err.value)

    def test_bad_values_rejected_before_state_checks(self, root):
        with pytest.raises(publication.PublishError) as err:
            pub(root, platform="tiktok")
        assert err.value.code == 2
        with pytest.raises(publication.PublishError) as err:
            pub(root, fmt="both")
        assert err.value.code == 2
        assert status_bytes(root) is None


class TestDuplicates:
    def test_repeat_is_noop_preserving_original(self, root):
        approved(root)
        first, _ = pub(root, url=URL, by="Dave")
        before = status_bytes(root)
        entry, created = pub(root, now=datetime(2026, 11, 5, tzinfo=timezone.utc))
        assert not created and entry == first
        assert status_bytes(root) == before

    def test_default_actor_not_consulted_for_duplicate(self, root):
        approved(root)
        pub(root, default_by=lambda: "Old Name")
        before = status_bytes(root)

        def changed_git_name():
            raise AssertionError("actor default must only be resolved for a new record")
        entry, created = pub(root, default_by=changed_git_name)
        assert not created and entry["published_by"] == "Old Name"
        assert status_bytes(root) == before

    def test_same_explicit_metadata_is_noop(self, root):
        approved(root)
        pub(root, url=URL, by="Dave", at="2026-11-04T20:00:00Z")
        _, created = pub(root, url=f" {URL} ", by="Dave", at="2026-11-04T14:00:00-06:00")
        assert not created

    @pytest.mark.parametrize("kw", [{"url": "https://example.com/other"}, {"by": "Someone"},
                                    {"at": "2026-11-01T00:00:00Z"}])
    def test_conflicting_explicit_metadata_rejected(self, root, kw):
        approved(root)
        pub(root, by="Dave", at="2026-11-04T20:00:00Z")
        before = status_bytes(root)
        with pytest.raises(publication.PublishError) as err:
            pub(root, **kw)
        assert err.value.code == 1 and "already exists" in str(err.value)
        assert status_bytes(root) == before

    def test_adding_url_later_is_a_conflict(self, root):
        approved(root)
        pub(root)
        with pytest.raises(publication.PublishError):
            pub(root, url=URL)

    def test_duplicate_recognized_when_local_file_missing(self, root):
        approved(root)
        first, _ = pub(root)
        (root / "vertical/ep.mp4").unlink()
        before = status_bytes(root)
        entry, created = pub(root)
        assert not created and entry == first and status_bytes(root) == before

    def test_duplicate_by_stored_hash_when_local_file_changed_does_not_publish_new_bytes(self, root):
        approved(root)
        pub(root)
        (root / "vertical/ep.mp4").write_bytes(b"edited after upload")
        before = status_bytes(root)
        _, created = pub(root)
        assert not created and status_bytes(root) == before
        st = approval.current(root, "ep")
        assert publication.destination_state(root, st, "youtube", "vertical")[0] == "changed-since-publish"

    def test_actual_bytes_matching_history_on_unapproved_build_is_noop_not_new_record(self, root):
        approved(root, vertical=b"v1")
        first, _ = pub(root)
        build(root, key="k2", vertical=b"v1")  # same bytes, new content key: approval kept? no, key changed
        assert approval.current(root, "ep").state == "built"
        entry, created = pub(root)
        assert not created and entry == first
        assert len(approval.current(root, "ep").publications) == 1

    def test_changed_unapproved_bytes_are_refused(self, root):
        approved(root, vertical=b"v1")
        pub(root)
        build(root, key="k2", vertical=b"v2")
        with pytest.raises(publication.PublishError) as err:
            pub(root)
        assert err.value.code == 1 and "approve" in str(err.value)


class TestIndependentDestinations:
    def test_platforms_independent(self, root):
        approved(root)
        pub(root, platform="youtube")
        _, created = pub(root, platform="instagram")
        assert created and len(approval.current(root, "ep").publications) == 2

    def test_formats_independent(self, root):
        approved(root, vertical=b"v1", horizontal=b"h1")
        pub(root, fmt="vertical")
        _, created = pub(root, fmt="horizontal")
        assert created and len(approval.current(root, "ep").publications) == 2


class TestRevisions:
    def test_same_bytes_new_content_key_stays_published(self, root):
        approved(root, vertical=b"v1")
        first, _ = pub(root)
        approved(root, key="k2", vertical=b"v1")
        st = approval.current(root, "ep")
        assert publication.destination_state(root, st, "youtube", "vertical")[0] == "published-current"
        entry, created = pub(root)
        assert not created and entry["content_key"] == "k1"

    def test_new_bytes_pending_then_appended(self, root):
        approved(root, vertical=b"v1")
        first, _ = pub(root, url=URL)
        approved(root, key="k2", vertical=b"v2")
        assert [(p.platform, p.fmt) for p in publication.pending(root)] == [("youtube", "vertical"),
                                                                              ("instagram", "vertical")]
        second, created = pub(root)
        assert created
        assert approval.current(root, "ep").publications == [first, second]
        assert [(p.platform, p.fmt) for p in publication.pending(root)] == [("instagram", "vertical")]

    def test_changing_one_orientation_does_not_requeue_other(self, root):
        approved(root, vertical=b"v1", horizontal=b"h1")
        pub(root, fmt="vertical")
        pub(root, fmt="horizontal")
        approved(root, key="k2", vertical=b"v1", horizontal=b"h2")
        pending = [(p.platform, p.fmt) for p in publication.pending(root, platform="youtube")]
        assert pending == [("youtube", "horizontal")]


class TestPendingAndStates:
    def test_unapproved_and_changed_stay_out(self, root):
        build(root, vertical=b"v1")
        assert publication.pending(root) == []
        approval.approve(root, "ep", "R", now=BUILT)
        (root / "vertical/ep.mp4").write_bytes(b"x")
        assert publication.pending(root) == []

    def test_filters(self, root):
        approved(root, vertical=b"v1", horizontal=b"h1")
        pub(root, platform="youtube", fmt="vertical")
        pairs = lambda **kw: [(p.platform, p.fmt) for p in publication.pending(root, **kw)]  # noqa: E731
        assert pairs(platform="youtube") == [("youtube", "horizontal")]
        assert pairs(fmt="vertical") == [("instagram", "vertical")]
        assert pairs(platform="youtube", fmt="vertical") == []
        assert pending_paths(root) == {"vertical/ep.mp4", "horizontal/ep.mp4"}

    def test_report_distinguishes_empty_reasons(self, root):
        assert publication.backlog_report(root).reason == "no-approved"
        approved(root, vertical=b"v1")
        assert publication.backlog_report(root, fmt="horizontal").reason == "no-match"
        pub(root, platform="youtube")
        assert publication.backlog_report(root, platform="youtube").reason == "all-published"
        assert publication.backlog_report(root, platform="instagram").reason is None

    def test_local_missing_state(self, root):
        approved(root)
        pub(root)
        (root / "vertical/ep.mp4").unlink()
        st = approval.current(root, "ep")
        label, records = publication.destination_state(root, st, "youtube", "vertical")
        assert label == "local-missing" and len(records) == 1
        assert publication.destination_state(root, st, "youtube", "horizontal")[0] == "unpublished"


def pending_paths(root):
    return {p.path for p in publication.pending(root)}


class TestSeriesProgress:
    def test_counts_include_unbuilt_and_split_ever_vs_current(self, root):
        approved(root, vertical=b"v1")
        pub(root)
        eids = ["ep", "ep2-unbuilt"]
        assert publication.series_progress(root, eids, "youtube", "vertical") == (1, 1, 2)
        approved(root, key="k2", vertical=b"v2")
        assert publication.series_progress(root, eids, "youtube", "vertical") == (1, 0, 2)
        assert publication.series_progress(root, eids + ["ep3"], "youtube", "vertical") == (1, 0, 3)
        assert publication.series_progress(root, eids, "instagram", "vertical") == (0, 0, 2)
