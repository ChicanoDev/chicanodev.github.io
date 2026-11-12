import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import approval  # noqa: E402

NOW = "2026-10-29T12:00:00"


@pytest.fixture
def files(tmp_path):
    f = tmp_path / "final" / "vertical" / "ep.mp4"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"video-v1")
    return {"vertical": f}


def built(tmp_path, files, key="k1", qa=()):
    return approval.record_build(tmp_path, "ep", key, files, list(qa), now=NOW)


class TestRecordBuild:
    def test_new_build_is_built_not_approved(self, tmp_path, files):
        st = built(tmp_path, files)
        assert st.state == "built" and st.approved_by is None

    def test_status_file_is_written_as_json(self, tmp_path, files):
        built(tmp_path, files)
        data = json.loads((tmp_path / "ep.status.json").read_text())
        assert data["state"] == "built" and data["content_key"] == "k1"

    def test_build_with_qa_problems_is_marked_failed(self, tmp_path, files):
        assert built(tmp_path, files, qa=["bad aspect"]).state == "failed-qa"


class TestApprove:
    def test_approve_marks_approved_with_who_and_when(self, tmp_path, files):
        built(tmp_path, files)
        st = approval.approve(tmp_path, "ep", "Dave", now=NOW)
        assert (st.state, st.approved_by, st.approved_at) == ("approved", "Dave", NOW)

    def test_cannot_approve_something_never_built(self, tmp_path):
        with pytest.raises(approval.NotApprovable) as err:
            approval.approve(tmp_path, "ep", "Dave")
        assert "build" in str(err.value)

    def test_cannot_approve_failed_qa(self, tmp_path, files):
        built(tmp_path, files, qa=["video is silent"])
        with pytest.raises(approval.NotApprovable) as err:
            approval.approve(tmp_path, "ep", "Dave")
        assert "silent" in str(err.value)

    def test_cannot_approve_if_file_missing(self, tmp_path, files):
        built(tmp_path, files)
        files["vertical"].unlink()
        with pytest.raises(approval.NotApprovable):
            approval.approve(tmp_path, "ep", "Dave")

    def test_cannot_approve_file_changed_since_build(self, tmp_path, files):
        built(tmp_path, files)
        files["vertical"].write_bytes(b"someone re-exported this")
        with pytest.raises(approval.NotApprovable) as err:
            approval.approve(tmp_path, "ep", "Dave")
        assert "changed" in str(err.value)


class TestInvalidation:
    def approved(self, tmp_path, files):
        built(tmp_path, files)
        approval.approve(tmp_path, "ep", "Dave", now=NOW)

    def test_rebuild_with_same_content_keeps_approval(self, tmp_path, files):
        self.approved(tmp_path, files)
        assert built(tmp_path, files, key="k1").state == "approved"

    def test_rebuild_with_new_content_resets_to_built(self, tmp_path, files):
        self.approved(tmp_path, files)
        files["vertical"].write_bytes(b"video-v2")
        st = built(tmp_path, files, key="k2")
        assert st.state == "built" and st.approved_by is None

    def test_file_edited_after_approval_voids_it(self, tmp_path, files):
        self.approved(tmp_path, files)
        files["vertical"].write_bytes(b"tampered")
        assert approval.current(tmp_path, "ep").state == "changed"

    def test_unchanged_files_stay_approved(self, tmp_path, files):
        self.approved(tmp_path, files)
        assert approval.current(tmp_path, "ep").state == "approved"


class TestBacklog:
    def test_lists_only_valid_approvals(self, tmp_path, files):
        built(tmp_path, files)
        assert approval.backlog(tmp_path) == []
        approval.approve(tmp_path, "ep", "Dave", now=NOW)
        assert [s.eid for s in approval.backlog(tmp_path)] == ["ep"]
        files["vertical"].write_bytes(b"x")
        assert approval.backlog(tmp_path) == []

    def test_current_of_unknown_is_none(self, tmp_path):
        assert approval.current(tmp_path, "nope") is None


PUB = {"platform": "youtube", "format": "vertical", "published_at": "2026-11-04T20:00:00+00:00",
       "recorded_at": "2026-11-04T20:05:00+00:00", "published_by": "Dave", "url": None, "content_key": "k1",
       "artifact_path": "vertical/ep.mp4", "artifact_sha256": "abc", "approved_at": NOW, "approved_by": "Dave"}


def with_history(tmp_path, files, entries=(PUB,)):
    built(tmp_path, files)
    p = tmp_path / "ep.status.json"
    data = json.loads(p.read_text())
    data["publications"] = [dict(e) if isinstance(e, dict) else e for e in entries]
    p.write_text(json.dumps(data))
    return p


class TestPublicationHistory:
    def test_legacy_status_without_publications_loads_empty(self, tmp_path, files):
        built(tmp_path, files)
        p = tmp_path / "ep.status.json"
        data = json.loads(p.read_text())
        data.pop("publications", None)
        p.write_text(json.dumps(data))
        assert approval.current(tmp_path, "ep").publications == []

    def test_reads_do_not_rewrite_legacy_file(self, tmp_path, files):
        built(tmp_path, files)
        p = tmp_path / "ep.status.json"
        data = json.loads(p.read_text())
        data.pop("publications", None)
        p.write_text(json.dumps(data))
        before = p.read_bytes()
        approval.current(tmp_path, "ep")
        approval.backlog(tmp_path)
        assert p.read_bytes() == before

    @pytest.mark.parametrize("change", ["same", "changed", "failed"])
    def test_rebuilds_keep_history(self, tmp_path, files, change):
        with_history(tmp_path, files)
        if change == "changed":
            files["vertical"].write_bytes(b"video-v2")
        st = built(tmp_path, files, key="k1" if change == "same" else "k2", qa=["bad"] if change == "failed" else ())
        assert st.publications == [PUB]
        assert approval.current(tmp_path, "ep").publications == [PUB]

    def test_approve_keeps_history(self, tmp_path, files):
        with_history(tmp_path, files)
        assert approval.approve(tmp_path, "ep", "Dave", now=NOW).publications == [PUB]


class TestCorruptStatus:
    def assert_corrupt(self, tmp_path, p):
        before = p.read_bytes()
        with pytest.raises(approval.CorruptStatus) as err:
            approval.current(tmp_path, "ep")
        assert "ep.status.json" in str(err.value)
        assert p.read_bytes() == before

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "ep.status.json"
        p.write_text("{not json")
        self.assert_corrupt(tmp_path, p)

    def test_unknown_field(self, tmp_path, files):
        p = with_history(tmp_path, files, ())
        data = json.loads(p.read_text())
        data["surprise"] = 1
        p.write_text(json.dumps(data))
        self.assert_corrupt(tmp_path, p)

    def test_publications_not_a_list(self, tmp_path, files):
        p = with_history(tmp_path, files, ())
        data = json.loads(p.read_text())
        data["publications"] = {"x": 1}
        p.write_text(json.dumps(data))
        self.assert_corrupt(tmp_path, p)

    @pytest.mark.parametrize("bad", [
        {"platform": None}, {"platform": "tiktok"}, {"format": "both"}, {"published_at": "yesterday"},
        {"published_at": "2026-11-04T20:00:00"}, {"recorded_at": 5}, {"url": 7}, {"artifact_sha256": ""},
        {"published_by": None}, "missing:artifact_path", "not-a-dict"])
    def test_invalid_record(self, tmp_path, files, bad):
        if bad == "not-a-dict":
            entry = "oops"
        elif isinstance(bad, str):
            entry = {k: v for k, v in PUB.items() if k != bad.split(":")[1]}
        else:
            entry = {**PUB, **bad}
        p = with_history(tmp_path, files, [entry])
        self.assert_corrupt(tmp_path, p)

    def test_corrupt_history_is_not_replaced_by_rebuild(self, tmp_path, files):
        p = tmp_path / "ep.status.json"
        p.write_text("{not json")
        with pytest.raises(approval.CorruptStatus):
            built(tmp_path, files)
        assert p.read_text() == "{not json"


class TestAtomicWrite:
    def test_failed_replace_keeps_original_and_cleans_temp(self, tmp_path, files, monkeypatch):
        p = with_history(tmp_path, files)
        before = p.read_bytes()

        def boom(*a):
            raise OSError("disk full")
        monkeypatch.setattr(approval.os, "replace", boom)
        with pytest.raises(OSError):
            approval.approve(tmp_path, "ep", "Dave", now=NOW)
        assert p.read_bytes() == before
        assert sorted(x.name for x in tmp_path.iterdir()) == ["ep.status.json", "final"]
