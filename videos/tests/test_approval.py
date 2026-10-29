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
