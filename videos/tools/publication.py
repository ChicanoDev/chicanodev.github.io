"""Manual publication records for finished videos.

`publish` records that a person uploaded an approved export by hand; nothing here uploads anything. A record
is a historical fact about one exported file: its identity is (platform, format, artifact_sha256). Records are
append-only and live in the episode's status file next to (but independent of) the approval state, so a
rebuild that voids approval never erases history or implies the live post disappeared.

Compiled long videos are not tracked yet: `compile` has no approved artifact record of its own.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import approval
import narration

PLATFORMS = approval.PLATFORMS
FORMATS = approval.PUBLISH_FORMATS
AT_EXAMPLE = "2026-11-04T14:00:00-06:00"


class PublishError(Exception):
    """A publish request was refused. `code` is the CLI exit code: 2 usage/value, 1 state/integrity/conflict."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def _utc(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def utc_now():
    return datetime.now(timezone.utc)


def parse_at(text, now):
    """ISO 8601 with Z or a numeric offset, not in the future -> UTC ISO string."""
    hint = f"Use a full timestamp with a timezone, e.g. --at '{AT_EXAMPLE}' or --at '2026-11-04T20:00:00Z'."
    try:
        dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00")) if "T" in text else None
    except ValueError:
        dt = None
    if dt is None or dt.tzinfo is None:
        raise PublishError(f"--at {text!r} is not a timestamp with a timezone. {hint}", 2)
    if dt > now:
        raise PublishError(f"--at {text!r} is in the future. Record a publication after it happens. {hint}", 2)
    return _utc(dt)


def check_url(text):
    url = text.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise PublishError(f"--url {text!r} is not an absolute http(s) URL, e.g. https://www.youtube.com/shorts/ID", 2)
    if parts.username is not None or parts.password is not None:
        raise PublishError("--url must not contain a username or password.", 2)
    return url


def check_platform(platform):
    if platform not in PLATFORMS:
        raise PublishError(f"unknown platform {platform!r}. Use --platform youtube or --platform instagram.", 2)


def check_format(fmt):
    if fmt not in FORMATS:
        raise PublishError(f"unknown --format {fmt!r} for a publication. Use vertical or horizontal "
                           "(record each upload separately; 'both' is not allowed).", 2)


def _actual_sha(root, info):
    if not info:
        return None
    path = Path(root) / info["path"]
    return narration.file_sha(path) if path.exists() else None


def _matching(status, platform, fmt):
    return [p for p in status.publications if p["platform"] == platform and p["format"] == fmt]


def destination_state(root, status, platform, fmt):
    """Compare the local export with history for one destination. Returns (label, records):

    published-current      the intact current export is byte-identical to a recorded publication
    changed-since-publish  a current export exists but differs from every recorded publication
    local-missing          history exists but the export (or its status entry) is missing locally
    unpublished            no record for this destination
    These describe local files, not whether the remote post is still live.
    """
    records = _matching(status, platform, fmt) if status else []
    info = status.files.get(fmt) if status else None
    actual = _actual_sha(root, info)
    if not records:
        return "unpublished", records
    if actual is None:
        return "local-missing", records
    intact = actual == info["sha"]
    if intact and any(r["artifact_sha256"] == actual for r in records):
        return "published-current", records
    return "changed-since-publish", records


def _refusal(root, eid, status, fmt, ep):
    if status is None:
        return f"{eid}: nothing built yet. Run: python3 tools/vidkit.py build {ep}, review it, then approve it."
    if status.qa_problems:
        return f"{eid}: the build failed checks; fix and rebuild, then review and approve before publishing."
    if fmt not in status.files:
        return (f"{eid}: there is no {fmt} export. Build it with --format {fmt}, review, approve, then publish.")
    if status.state == "changed" or _actual_sha(root, status.files[fmt]) != status.files[fmt]["sha"]:
        return (f"{eid}: the exported {fmt} file is missing or changed since it was built. Run build to rebuild it, then review and "
                "approve it before recording a new publication.")
    if status.state != "approved":
        return f"{eid}: the build is not approved yet. Review it, then run: python3 tools/vidkit.py approve {ep}"
    return None



def record(root, eid, platform, fmt, by=None, url=None, at=None, now=None, default_by=None, name=None):
    """Record a manual publication. `by`, `url`, `at` are None when not supplied on the command line.

    Returns (entry, created). A repeat for the same (platform, format, artifact) is a no-op that keeps the
    original record; explicitly supplied metadata that differs from it is a conflict. A new record needs a
    current, approved, intact export of that format. Validates everything before writing.
    """
    root = Path(root)
    check_platform(platform)
    check_format(fmt)
    now = now or utc_now()
    url = check_url(url) if url is not None else None
    at = parse_at(at, now) if at is not None else None
    if by is not None and not by.strip():
        raise PublishError("--by needs a name.", 2)

    status = approval.current(root, eid)
    if status is not None:
        info = status.files.get(fmt)
        hashes = {h for h in (info and info["sha"], _actual_sha(root, info)) if h}
        existing = [r for r in _matching(status, platform, fmt) if r["artifact_sha256"] in hashes]
        if existing:
            found = existing[0]
            for name, given in (("url", url), ("published_at", at), ("published_by", by)):
                if given is not None and given != found[name]:
                    raise PublishError(
                        f"{eid}: a {platform} {fmt} publication record already exists for this file "
                        f"({name} = {found[name]!r}, you gave {given!r}). Records are not edited in this "
                        "release; nothing was changed.", 1)
            return found, False

    problem = _refusal(root, eid, status, fmt, name or eid)
    if problem:
        raise PublishError(problem, 1)
    info = status.files[fmt]
    entry = {
        "platform": platform, "format": fmt, "published_at": at or _utc(now), "recorded_at": _utc(now),
        "published_by": by if by is not None else (default_by() if default_by else "unknown"),
        "url": url, "content_key": status.content_key, "artifact_path": info["path"],
        "artifact_sha256": info["sha"], "approved_at": status.approved_at, "approved_by": status.approved_by,
    }
    stored = approval._load(root, eid)  # the raw record, so a derived 'changed' state is never written
    stored.publications.append(entry)
    approval._save(root, stored)
    return entry, True


@dataclass
class Pending:
    status: object
    platform: str
    fmt: str
    path: str


def pending(root, platform=None, fmt=None):
    """Approved, intact exports not yet recorded as published, one row per (episode, platform, format).
    Separate from approval.backlog(), which still returns approved Status objects."""
    rows = []
    for st in approval.backlog(root):
        for f in (x for x in FORMATS if x in st.files and fmt in (None, x)):
            for p in (x for x in PLATFORMS if platform in (None, x)):
                if destination_state(root, st, p, f)[0] != "published-current":
                    rows.append(Pending(st, p, f, st.files[f]["path"]))
    return rows


@dataclass
class BacklogReport:
    rows: list
    reason: str  # None when rows exist; else no-approved | no-match | all-published


def backlog_report(root, platform=None, fmt=None):
    approved = approval.backlog(root)
    rows = pending(root, platform, fmt)
    if rows:
        return BacklogReport(rows, None)
    if not approved:
        return BacklogReport(rows, "no-approved")
    if not any(f in st.files for st in approved for f in FORMATS if fmt in (None, f)):
        return BacklogReport(rows, "no-match")
    return BacklogReport(rows, "all-published")


def series_progress(root, eids, platform, fmt):
    """(ever, current, n) over the registered episodes `eids`; unbuilt episodes count toward n."""
    ever = current = 0
    for eid in eids:
        st = approval.current(root, eid)
        if st is None:
            continue
        label, records = destination_state(root, st, platform, fmt)
        ever += bool(records)
        current += label == "published-current"
    return ever, current, len(eids)
