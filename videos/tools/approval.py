"""Review/approval state for finished videos.

A successful build is only 'built'. A human runs `approve` to move it to 'approved'. Any change to the
content (new build inputs) or to the exported files voids the approval.
"""
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path

import narration

PLATFORMS = ("youtube", "instagram")
PUBLISH_FORMATS = ("vertical", "horizontal")


class NotApprovable(Exception):
    """The build is not in a state that can be approved; the message says what to do."""


class CorruptStatus(Exception):
    """A status file cannot be read. It is never overwritten automatically, because it holds publication history."""


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
    # Append-only manual publication records (see publication.py). Independent of the approval state above.
    publications: list = field(default_factory=list)


def _path(root, eid):
    return Path(root) / f"{eid}.status.json"


def _now():
    return datetime.now().replace(microsecond=0).isoformat()


def _rel(root, path):
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return str(path)


def _aware_iso(value):
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None and "T" in value
    except ValueError:
        return False


_TEXT = ("published_by", "content_key", "artifact_path", "artifact_sha256")
_OPTIONAL_TEXT = ("url", "approved_at", "approved_by")


def _publication_problem(entry):
    if not isinstance(entry, dict):
        return "a publication record is not an object"
    required = {"platform", "format", "published_at", "recorded_at", *_TEXT, *_OPTIONAL_TEXT}
    missing = sorted(required - set(entry))
    if missing:
        return f"a publication record is missing {', '.join(missing)}"
    if entry["platform"] not in PLATFORMS:
        return f"unknown platform {entry['platform']!r}"
    if entry["format"] not in PUBLISH_FORMATS:
        return f"unknown format {entry['format']!r}"
    for key in ("published_at", "recorded_at"):
        if not _aware_iso(entry[key]):
            return f"{key} {entry[key]!r} is not an ISO timestamp with a timezone"
    for key in _TEXT:
        if not isinstance(entry[key], str) or not entry[key]:
            return f"{key} must be non-empty text"
    for key in _OPTIONAL_TEXT:
        if entry[key] is not None and not isinstance(entry[key], str):
            return f"{key} must be text or null"
    return None


def _load(root, eid):
    p = _path(root, eid)
    if not p.exists():
        return None
    fix = f"Fix or restore {p} by hand (e.g. from git or a backup); vidkit will not overwrite it."
    try:
        data = json.loads(p.read_text())
    except (ValueError, OSError) as err:
        raise CorruptStatus(f"{p}: unreadable status file ({err}). {fix}") from err
    if not isinstance(data, dict):
        raise CorruptStatus(f"{p}: status file is not a JSON object. {fix}")
    unknown = sorted(set(data) - {f.name for f in fields(Status)})
    if unknown:
        raise CorruptStatus(f"{p}: unknown fields {', '.join(unknown)}. {fix}")
    pubs = data.get("publications", [])
    if not isinstance(pubs, list):
        raise CorruptStatus(f"{p}: publications must be a list. {fix}")
    for i, entry in enumerate(pubs):
        problem = _publication_problem(entry)
        if problem:
            raise CorruptStatus(f"{p}: publication #{i + 1}: {problem}. {fix}")
    try:
        return Status(**data)
    except TypeError as err:
        raise CorruptStatus(f"{p}: {err}. {fix}") from err


def _save(root, status):
    """Write atomically: a crash mid-write must never truncate the only copy of publication history."""
    p = _path(root, status.eid)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(asdict(status), indent=2) + "\n")
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
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
    status = Status(eid, state, content_key, recorded, list(qa_problems), now or _now(),
                    publications=list(previous.publications) if previous else [])
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
