"""Review/approval state for finished videos.

A successful build is only 'built'. A human runs `approve` to move it to 'approved'. Any change to the
content (new build inputs) or to the exported files voids the approval.
"""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import narration


class NotApprovable(Exception):
    """The build is not in a state that can be approved; the message says what to do."""


@dataclass
class Status:
    eid: str
    state: str  # built | failed-qa | approved | changed
    content_key: str
    files: dict = field(default_factory=dict)  # {label: {"path": rel, "sha": sha}}
    qa_problems: list = field(default_factory=list)
    built_at: str = ""
    approved_at: str = None
    approved_by: str = None


def _path(root, eid):
    return Path(root) / f"{eid}.status.json"


def _now():
    return datetime.now().replace(microsecond=0).isoformat()


def _rel(root, path):
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return str(path)


def _load(root, eid):
    p = _path(root, eid)
    return Status(**json.loads(p.read_text())) if p.exists() else None


def _save(root, status):
    p = _path(root, status.eid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(status), indent=2) + "\n")
    return status


def _file_problems(root, status):
    problems = []
    for label, info in status.files.items():
        path = Path(root) / info["path"]
        if not path.exists():
            problems.append(f"{label}: {info['path']} is missing")
        elif narration.file_sha(path) != info["sha"]:
            problems.append(f"{label}: {info['path']} changed since it was built")
    return problems


def record_build(root, eid, content_key, files, qa_problems, now=None):
    """Record a finished build. Keeps an existing approval only if nothing changed."""
    root = Path(root)
    previous = _load(root, eid)
    recorded = {label: {"path": _rel(root, p), "sha": narration.file_sha(p)} for label, p in files.items()}
    unchanged = (previous and previous.state == "approved" and previous.content_key == content_key
                 and previous.files == recorded)
    if qa_problems:
        state = "failed-qa"
    else:
        state = "approved" if unchanged else "built"
    status = Status(eid, state, content_key, recorded, list(qa_problems), now or _now())
    if state == "approved":
        status.approved_at, status.approved_by = previous.approved_at, previous.approved_by
    return _save(root, status)


def current(root, eid):
    """The status as it is right now: an approval is void if the exported files changed."""
    status = _load(Path(root), eid)
    if status and status.state == "approved" and _file_problems(Path(root), status):
        status.state = "changed"
    return status


def approve(root, eid, who, now=None):
    root = Path(root)
    status = _load(root, eid)
    if status is None:
        raise NotApprovable(f"{eid}: nothing built yet. Run: python3 tools/vidkit.py build <episode>")
    if status.state == "failed-qa":
        raise NotApprovable(f"{eid}: failed checks, fix and rebuild first:\n  " + "\n  ".join(status.qa_problems))
    problems = _file_problems(root, status)
    if problems:
        raise NotApprovable(f"{eid}: " + "; ".join(problems) + ". Rebuild before approving.")
    status.state, status.approved_by, status.approved_at = "approved", who, now or _now()
    return _save(root, status)


def backlog(root):
    root = Path(root)
    if not root.exists():
        return []
    found = (current(root, p.name.removesuffix(".status.json")) for p in sorted(root.glob("*.status.json")))
    return [s for s in found if s and s.state == "approved"]


def is_intact(root, eid, label):
    """True if `eid` was built by the pipeline and its exported `label` file is still that exact file."""
    status = _load(Path(root), eid)
    if not status or label not in status.files:
        return False
    info = status.files[label]
    path = Path(root) / info["path"]
    return path.exists() and narration.file_sha(path) == info["sha"]
