"""Narration-first build: takes -> transcripts -> timed tape -> measured render -> captioned, branded video.

Every stage is cached by the content of its own inputs, so replacing one take only redoes that take's
audio and transcript, then whatever depends on the changed timing.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import approval
import captions
import compose
import measure
import narration
import retime
import transcribe
import vidkit

CAPTION_CHARS = {"vertical": 32, "horizontal": 48}
INTRO = Path("assets") / "branding" / "chicanodev-intro.mp4"


class SyncFailed(Exception):
    """The render could not be brought into sync with the narration; a report was written."""


@dataclass
class Config:
    formats: list = field(default_factory=lambda: ["vertical", "horizontal"])
    placement: str = None  # None = per-format default
    pause: float = 0.3
    tail: float = 0.6
    pad: float = 0.12
    force: bool = False
    dry_run: bool = False
    verbose: bool = False
    beat_tol: float = 0.3
    total_tol: float = 0.5
    max_corrections: int = 2


@dataclass
class Env:
    root: Path
    render: object  # (tape_text, orient, tape_path, raw_path) -> None
    burn: object  # (master, srt, dst, orient) -> None
    engine: object = None  # wav -> [Word]; None = local faster-whisper, loaded on first use
    log: object = print


@dataclass
class BuildResult:
    eid: str
    outputs: dict = field(default_factory=dict)
    expected: dict = field(default_factory=dict)
    placements: dict = field(default_factory=dict)
    stage_status: dict = field(default_factory=dict)
    segment_status: dict = field(default_factory=dict)
    sync: dict = field(default_factory=dict)
    qa: dict = field(default_factory=dict)
    plan_lines: list = field(default_factory=list)
    status: object = None


def post_copy(md_text):
    """{'YouTube Shorts title': ..., 'Hashtags': ...} from the '## Post copy' section's **Label:** lines."""
    section = md_text.split("## Post copy", 1)[-1] if "## Post copy" in md_text else ""
    return {m.group(1).strip(): m.group(2).strip() for m in re.finditer(r"^\*\*(.+?):\*\*\s*(.+)$", section, re.M)}


def _fresh(out, key):
    stamp = Path(out).with_name(Path(out).name + ".key")
    return Path(out).exists() and stamp.exists() and stamp.read_text() == key


def _lazy_engine(env):
    if env.engine is None:
        env.engine = transcribe.whisper_engine()
    return env.engine


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def build_episode(series, slug, cfg, env):
    compose.check_placement(cfg.placement or "outro")
    eid = vidkit.episode_id(series, slug)
    folder = env.root / "series" / series / slug
    work = env.root / "out" / "intermediate" / eid
    final_root = env.root / "out" / "final"
    result = BuildResult(eid)
    log = env.log

    voiceover = (folder / "voiceover.md").read_text()
    segments = narration.episode_segments(folder)
    selected = narration.load_alignment(folder).get("selected") or {}

    if cfg.dry_run:
        return _dry_run(result, folder, work, segments, selected, cfg, env)

    # 1. audio: only changed takes are ingested and transcribed
    report = narration.prepare(segments, folder / "narration", work, selected, pad=cfg.pad, force=cfg.force)
    for item in report:
        status = transcribe.ensure(item.segment, item.audio_sha, item.wav, folder / "transcript",
                                   _lazy_engine(env), cfg.force)
        result.segment_status[item.segment.id] = (item.status, status)
        log(f"   {item.segment.id}: audio {item.status}, transcript {status}")
    voice = work / "narration.wav"
    before = voice.stat().st_mtime_ns if voice.exists() else None
    narration.stitch(report, voice, cfg.pause, cfg.force)
    result.stage_status["narration"] = "cached" if before and voice.stat().st_mtime_ns == before else "ran"

    spans = narration.timeline([r.duration for r in report], cfg.pause)
    periods = retime.beat_periods([r.duration for r in report], cfg.pause, cfg.tail)
    expected_total = spans[-1][1] + cfg.tail
    hook_end = spans[0][1] + cfg.pause / 2

    # 2. captions come from the (possibly hand-corrected) transcripts, timed by the recording
    transcripts = {r.segment.id: transcribe.load(folder / "transcript", r.segment.id) for r in report}
    keys = [item.audio_sha for item in report]
    body = (folder / "body.tape").read_text()

    intro = env.root / INTRO
    content_parts = [cfg.pause, cfg.tail, *keys]
    for orient in cfg.formats:
        placement = cfg.placement or compose.default_placement(orient)
        result.placements[orient] = placement
        slots = compose.brand_slots(placement)

        timed_periods, sync, raw, raw_status = _synced_render(
            orient, body, periods, spans, expected_total, titles=[s.title for s in segments],
            work=work, env=env, cfg=cfg, voiceover_key=keys)
        result.sync[orient] = sync
        result.stage_status[f"{orient}:render"] = raw_status

        master_path = work / f"{orient}-master.mp4"
        result.stage_status[f"{orient}:master"] = narration.run_stage(
            master_path, narration.cache_key(raw, voice, expected_total, "master-v1"),
            lambda: compose.master(raw, voice, master_path, min_seconds=expected_total), cfg.force)

        cues = []
        for r in report:
            cues += captions.cues_from_words(transcripts[r.segment.id].words, CAPTION_CHARS[orient], 2, spans[r.segment.index - 1][0])
        burn_srt = _write(work / f"{orient}-captions.srt", vidkit.format_srt(cues))
        captioned = work / f"{orient}-captioned.mp4"
        result.stage_status[f"{orient}:captions"] = narration.run_stage(
            captioned, narration.cache_key(master_path, burn_srt, vidkit.CAPTION_STYLE[orient], "burn-v1"),
            lambda: env.burn(master_path, burn_srt, captioned, orient), cfg.force)

        brand_path = work / f"{orient}-brand.mp4"
        brand_seconds = 0.0
        if slots:
            result.stage_status[f"{orient}:brand"] = narration.run_stage(
                brand_path, narration.cache_key(intro, orient, "brand-v1"),
                lambda: compose.brand_clip(intro, brand_path, orient), cfg.force)
            brand_seconds = compose.seconds(brand_path)

        final = final_root / orient / f"{eid}.mp4"
        final.parent.mkdir(parents=True, exist_ok=True)
        brand_key = narration.file_sha(brand_path) if slots else ""
        result.stage_status[f"{orient}:final"] = narration.run_stage(
            final, narration.cache_key(captioned, brand_key, placement, round(hook_end, 3), "final-v1"),
            lambda: compose.assemble(captioned, brand_path, final, placement, hook_end), cfg.force)

        shifted = compose.shift_cues(cues, placement, hook_end, brand_seconds)
        final.with_suffix(".srt").write_text(vidkit.format_srt(shifted))
        final.with_suffix(".vtt").write_text(captions.format_vtt(shifted))

        result.outputs[orient] = final
        result.expected[orient] = compose.seconds(captioned) + brand_seconds * len(slots)
        result.qa[orient] = compose.qa_problems(final, orient, result.expected[orient], len(slots), brand_seconds)
        content_parts += [orient, placement, narration.file_sha(final)]

    _write(work / "timing.json", json.dumps({"hook_end": hook_end, "narration_end": spans[-1][1], "expected_total": expected_total}))
    _write(final_root / f"{eid}.meta.md", _metadata(eid, voiceover, segments, transcripts))
    qa_flat = [f"{o}: {p}" for o, ps in result.qa.items() for p in ps]
    result.status = approval.record_build(final_root, eid, narration.cache_key(*content_parts), result.outputs, qa_flat)
    return result


def _synced_render(orient, body, periods, spans, expected_total, titles, work, env, cfg, voiceover_key):
    """Render the retimed tape, measure real beat starts, and re-render with corrections until in sync."""
    settings = (env.root / "common" / f"{orient}.settings.tape").read_text()
    tape_path, raw = work / f"{orient}.tape", work / f"{orient}-raw.mp4"
    state = work / f"{orient}-sync.json"
    sync_key = narration.cache_key(body, settings, expected_total, tuple(periods), "sync-v1")
    targets = [s for s, _ in spans]

    saved = json.loads(state.read_text()) if state.exists() and not cfg.force else None
    if saved and saved["key"] == sync_key:
        timed, _ = retime.retime_tape(body, saved["periods"])
        if _fresh(raw, narration.cache_key(timed, settings, "vhs-v1")):
            env.log(f"   {orient}: render cached (in sync)")
            report = measure.drift_report(saved["measured"], targets, (saved["raw_len"], expected_total), titles=titles,
                                          beat_tol=cfg.beat_tol, total_tol=cfg.total_tol)
            return saved["periods"], report, raw, "cached"

    current, status = list(periods), "ran"
    for attempt in range(cfg.max_corrections + 1):
        timed, plans = retime.retime_tape(body, current)  # SyncError = narration too short for the visuals
        key = narration.cache_key(timed, settings, "vhs-v1")
        env.log(f"   {orient}: rendering ({'first pass' if not attempt else f'correction {attempt}'})")
        narration.run_stage(raw, key, lambda: env.render(timed, orient, tape_path, raw), cfg.force)
        measured, raw_len = _measure_starts(raw, timed)
        report = measure.drift_report(measured, targets, (raw_len, expected_total), titles=titles,
                                      beat_tol=cfg.beat_tol, total_tol=cfg.total_tol)
        if cfg.verbose:
            env.log(report.markdown())
        if report.ok:
            _write(state, json.dumps({"key": sync_key, "periods": current, "measured": measured, "raw_len": raw_len}))
            return current, report, raw, status
        nxt = measure.corrected_periods(current, measured, raw_len)
        if max(abs(a - b) for a, b in zip(nxt, current)) < 0.001:
            break  # nothing left to correct: further renders would be identical
        current = nxt
    path = _write(work / "sync-report.md", report.markdown() + "\n" + _suggestion(report))
    raise SyncFailed(f"{orient}: video and narration are out of sync after {cfg.max_corrections} corrections. "
                     f"See {path} for the per-beat numbers.")


def _measure_starts(raw, timed):
    _, blocks = retime.split_beats(timed)
    starts, t = [], 0.0
    for b in blocks:
        starts.append(t)
        t += b.seconds
    offsets = [retime.anchor_offset(b) for b in blocks]
    series = measure.ink_series(raw, 25)
    expected = [starts[i] + (offsets[i] or 0) for i in range(1, len(blocks))]
    found = measure.find_clears(series, 25, expected)
    measured = [0.0] + [None if f is None else f - offsets[i] for i, f in zip(range(1, len(blocks)), found)]
    return measured, compose.seconds(raw)


def _suggestion(report):
    return ("## What to try\n\n- Re-record the flagged segment so its length is closer to what the on-screen commands need.\n"
            "- If a beat is `could not find`, open the raw render in `out/intermediate/` and check it starts with `clear`.\n"
            "- A render far off from the tape means VHS is running slowly; re-run the build.\n")


def _metadata(eid, voiceover, segments, transcripts):
    copy = post_copy(voiceover)
    lines = [f"# {eid}", "", "Status: built, NOT approved. Review on a phone, then `vidkit.py approve`.", ""]
    for label, value in copy.items():
        lines += [f"**{label}:** {value}", ""]
    lines += ["## Transcript", ""]
    for seg in segments:
        lines += [" ".join(w.text for w in transcripts[seg.id].words), ""]
    return "\n".join(lines)


def _dry_run(result, folder, work, segments, selected, cfg, env):
    """What a build would do, without creating or changing anything."""
    takes = {s.id: narration.resolve_take(folder / "narration", s.id, selected) for s in segments}
    missing = [s.id for s in segments if takes[s.id] is None]
    if missing:
        raise narration.MissingTakes("missing narration: " + ", ".join(f"{m}.m4a" for m in missing))
    for s in segments:
        sha = narration.file_sha(takes[s.id])
        wav = work / f"{s.id}.wav"
        fresh = _fresh(wav, narration.cache_key(sha, cfg.pad, narration.WORK_RATE, narration.SILENCE_DB, "ingest-v1"))
        t_path = folder / "transcript" / f"{s.id}.yaml"
        t_fresh = t_path.exists() and transcribe.load(folder / "transcript", s.id).audio_sha == sha
        result.plan_lines.append(f"{s.id}: ingest {'cached' if fresh else 'WOULD RUN'}, "
                                 f"transcribe {'cached' if t_fresh else 'WOULD RUN'}")
    result.plan_lines.append(f"then: sync-render, master, captions, brand and assemble for {', '.join(cfg.formats)}")
    return result


def docker_env(root=None, log=print):
    """Real collaborators: VHS and caption burning run in the chicanodev-vhs image, ASR is local whisper."""
    root = Path(root or vidkit.ROOT)

    def rel(path):
        return str(Path(path).relative_to(root))

    def render(tape_text, orient, tape_path, raw_path):
        settings = (root / "common" / f"{orient}.settings.tape").read_text()
        _write(tape_path, vidkit.build_tape(settings, tape_text, rel(raw_path)))
        vidkit._docker(rel(tape_path))

    def burn(master, srt, dst, orient):
        vidkit._docker("-y", "-i", rel(master), "-vf", f"subtitles={rel(srt)}:force_style='{vidkit.CAPTION_STYLE[orient]}'",
                       "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(compose.FPS),
                       "-c:a", "copy", "-movflags", "+faststart", rel(dst), entrypoint="ffmpeg")

    return Env(root=root, render=render, burn=burn, engine=None, log=log)


@dataclass(frozen=True)
class CleanSource:
    clip: Path
    srt: Path
    hook_end: float


def clean_source(root, eid):
    """Brand-free captioned master of a pipeline-built episode, for compilations. None for legacy episodes
    (never built here, or whose exported file was since replaced by `mux`)."""
    root = Path(root)
    work = root / "out" / "intermediate" / eid
    clip, srt, timing = work / "horizontal-captioned.mp4", work / "horizontal-captions.srt", work / "timing.json"
    if not (clip.exists() and srt.exists() and timing.exists()):
        return None
    if not approval.is_intact(root / "out" / "final", eid, "horizontal"):
        return None
    return CleanSource(clip, srt, json.loads(timing.read_text())["hook_end"])


def brand_compilation(compiled, cues, placement, hook_end, intro, work_dir, out_path):
    """Add the brand clip ONCE to a whole compiled video. Returns (path, cues_for_the_new_timeline)."""
    if placement == "both":
        raise ValueError("a compilation gets the brand clip once: use after-hook, outro or none, not both")
    compose.check_placement(placement)
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    brand = compose.brand_clip(intro, Path(work_dir) / "brand-compilation.mp4", "horizontal")
    compose.assemble(compiled, brand, out_path, placement, hook_end)
    return Path(out_path), compose.shift_cues(cues, placement, hook_end, compose.seconds(brand) if compose.brand_slots(placement) else 0)
