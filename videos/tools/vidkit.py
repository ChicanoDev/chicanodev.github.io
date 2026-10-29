"""vidkit: build, lint, caption and render the ChicanoDev VHS episodes."""
import re
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

_SLEEP = re.compile(r"^Sleep\s+([\d.]+)(ms|s)\b")
_SET_SPEED = re.compile(r"^Set\s+TypingSpeed\s+([\d.]+)(ms|s)\b")
_TYPE = re.compile(r'^Type(?:@([\d.]+)(ms|s))?\s+(["\'`])(.*)\3\s*$')
_BEAT = re.compile(r"^#\s*@beat\s+(\S+)\s*(.*)$")
_VO_HEADING = re.compile(r"^##\s*\[(\d+:\d+(?:\.\d+)?)-(\d+:\d+(?:\.\d+)?)\]\s*(.*)$")


def parse_timestamp(text):
    """'1:05' -> 65, '0:06.5' -> 6.5."""
    minutes, seconds = text.split(":")
    return int(minutes) * 60 + float(seconds)


def _to_seconds(value, unit):
    return float(value) / 1000 if unit == "ms" else float(value)


def estimate_duration(tape_text, default_typing_ms=70):
    """Seconds of visible recording a tape produces (Hide..Show is cut by VHS)."""
    speed = default_typing_ms / 1000
    hidden = False
    total = 0.0
    for raw in tape_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "Hide":
            hidden = True
            continue
        if line == "Show":
            hidden = False
            continue
        if m := _SET_SPEED.match(line):
            speed = _to_seconds(*m.groups())
            continue
        if hidden:
            continue
        if m := _SLEEP.match(line):
            total += _to_seconds(*m.groups())
        elif m := _TYPE.match(line):
            per_char = _to_seconds(m.group(1), m.group(2)) if m.group(1) else speed
            total += per_char * len(m.group(4))
    return total


def parse_tape_beats(tape_text):
    """[(seconds, label)] from '# @beat M:SS Label' markers."""
    beats = []
    for line in tape_text.splitlines():
        if m := _BEAT.match(line.strip()):
            beats.append((parse_timestamp(m.group(1)), m.group(2).strip()))
    return beats


@dataclass(frozen=True)
class Beat:
    start: float
    end: float
    title: str
    text: str


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def parse_voiceover(md_text):
    """Beats from '## [M:SS-M:SS] Title' sections; '>' note lines and other headings are skipped."""
    beats = []
    current = None
    for line in md_text.splitlines():
        if line.startswith("#"):
            if current:
                beats.append(current)
            current = None
            if m := _VO_HEADING.match(line):
                current = [parse_timestamp(m.group(1)), parse_timestamp(m.group(2)), m.group(3).strip(), []]
        elif current is not None and line.strip() and not line.lstrip().startswith(">"):
            current[3].append(line.strip())
    if current:
        beats.append(current)
    return [Beat(start, end, title, " ".join(lines)) for start, end, title, lines in beats]


def make_cues(beats, max_chars=32, max_lines=2):
    """Caption cues: wrapped to max_chars, max_lines per cue, timed by length inside each beat."""
    cues = []
    for beat in beats:
        lines = textwrap.wrap(beat.text, width=max_chars)
        chunks = ["\n".join(lines[i:i + max_lines]) for i in range(0, len(lines), max_lines)]
        total = sum(len(c.replace("\n", "")) for c in chunks)
        span = beat.end - beat.start
        cursor = beat.start
        for n, chunk in enumerate(chunks):
            end = beat.end if n == len(chunks) - 1 else cursor + span * len(chunk.replace("\n", "")) / total
            cues.append(Cue(cursor, end, chunk))
            cursor = end
    return cues


def _srt_time(seconds):
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def format_srt(cues):
    blocks = [
        f"{n}\n{_srt_time(c.start)} --> {_srt_time(c.end)}\n{c.text}\n"
        for n, c in enumerate(cues, 1)
    ]
    return "\n".join(blocks)


def offset_cues(cues, offset):
    return [Cue(c.start + offset, c.end + offset, c.text) for c in cues]


def _estimate_at_beat(tape_text, marker_line):
    """Estimated recording time at the line index of a beat marker."""
    return estimate_duration("\n".join(tape_text.splitlines()[:marker_line]))


def lint_episode(tape_text, voiceover_md, min_seconds=60, max_seconds=90,
                 min_words=140, max_words=230, max_typed=32, tolerance=1.0):
    """Return a list of human-readable problems; empty means the episode is ready."""
    problems = []

    total = estimate_duration(tape_text)
    if not min_seconds <= total <= max_seconds:
        problems.append(f"duration {total:.0f}s outside {min_seconds}-{max_seconds}s")

    beats = parse_voiceover(voiceover_md)
    words = sum(len(b.text.split()) for b in beats)
    if not min_words <= words <= max_words:
        problems.append(f"voiceover has {words} words, want {min_words}-{max_words}")

    hidden = False
    for raw in tape_text.splitlines():
        line = raw.strip()
        if line in ("Hide", "Show"):
            hidden = line == "Hide"
            continue
        m = _TYPE.match(line)
        if m and not hidden and len(m.group(4)) > max_typed:
            problems.append(f"typed line over {max_typed} chars: {m.group(4)[:40]!r}")

    markers = [(n, m) for n, raw in enumerate(tape_text.splitlines())
               if (m := _BEAT.match(raw.strip()))]
    if len(markers) != len(beats):
        problems.append(f"beat count: tape has {len(markers)}, voiceover has {len(beats)}")
    for (line_no, m), beat in zip(markers, beats):
        marked = parse_timestamp(m.group(1))
        if abs(marked - beat.start) > tolerance:
            problems.append(f"beat {beat.title!r}: voiceover starts at {beat.start:.0f}s, tape marker at {marked:.0f}s")
        est = _estimate_at_beat(tape_text, line_no)
        if abs(marked - est) > tolerance:
            problems.append(f"beat {beat.title!r}: marker {marked:.0f}s but estimate is {est:.1f}s")
    return problems


def build_tape(settings_text, body_text, output_path):
    return f"Output {output_path}\n{settings_text.rstrip()}\n\n{body_text.rstrip()}\n"


def scale_cues(cues, factor):
    return [Cue(c.start * factor, c.end * factor, c.text) for c in cues]


@dataclass(frozen=True)
class Pace:
    title: str
    seconds: float
    words: int
    wpm: float
    too_fast: bool
    too_slow: bool


def beat_pace(beats, fast_wpm=175, slow_wpm=90):
    """Words per minute needed to read each beat inside its window."""
    out = []
    for b in beats:
        seconds = b.end - b.start
        words = len(b.text.split())
        wpm = words / seconds * 60
        out.append(Pace(b.title, seconds, words, wpm, wpm > fast_wpm, wpm < slow_wpm))
    return out


def plan_mux(video_seconds, audio_seconds, tail=1.0):
    """(final_seconds, seconds_to_hold_the_last_frame). Video is never cut; it is held if the voice runs long."""
    final = max(video_seconds, audio_seconds + tail)
    return final, final - video_seconds


AUDIO_EXTENSIONS = (".wav", ".m4a", ".mp3", ".aiff", ".aif", ".flac", ".ogg")


def find_audio(episode_id, audio_dir):
    for ext in AUDIO_EXTENSIONS:
        candidate = Path(audio_dir) / f"{episode_id}{ext}"
        if candidate.exists():
            return candidate
    return None


def narration_text(md_text):
    """The words to read aloud, one block per beat, without notes or post copy."""
    blocks = [f"[{_fmt_ts(b.start)}-{_fmt_ts(b.end)}] {b.title}\n{b.text}" for b in parse_voiceover(md_text)]
    return "\n\n".join(blocks) + "\n"


def _fmt_ts(seconds):
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def chapter_lines(titles, durations, card=2.0):
    """YouTube chapter lines ('M:SS Title') for a compilation of [card][clip] parts."""
    lines, start = [], 0.0
    for title, duration in zip(titles, durations):
        t = int(start)
        stamp = f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"
        lines.append(f"{stamp} {title}")
        start += card + duration
    return lines


def merge_cue_sets(sets, gap=0.0):
    """Concatenate (cues, clip_duration) pairs into one timeline, `gap` seconds between clips."""
    merged = []
    offset = 0.0
    for cues, duration in sets:
        merged += cues if offset == 0 else offset_cues(cues, offset)
        offset += duration + gap
    return merged


def parse_title(md_text):
    for line in md_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


_SIZES = {"vertical": (1080, 1920), "horizontal": (1920, 1080)}


def check_clip(orient, width, height, duration, estimate, tolerance=0.04):
    """VHS renders run ~2-3% short of the estimate even serially; flag drift beyond `tolerance` (fraction)."""
    problems = []
    if (width, height) != _SIZES[orient]:
        problems.append(f"resolution {width}x{height}, want {_SIZES[orient][0]}x{_SIZES[orient][1]}")
    if abs(duration - estimate) > tolerance * estimate:
        problems.append(f"duration {duration:.1f}s vs estimate {estimate:.1f}s")
    return problems


ROOT = Path(__file__).resolve().parent.parent

EPISODES = [
    ("linux-fs", "01-no-c-drive"),
    ("linux-fs", "02-where-programs-live"),
    ("linux-fs", "03-where-things-change"),
    ("linux-fs", "04-the-weird-ones"),
    ("linux-cmds", "01-get-around"),
    ("linux-cmds", "02-move-stuff"),
    ("linux-cmds", "03-read-files"),
    ("linux-cmds", "04-find-anything"),
    ("linux-cmds", "05-pipes-and-text"),
    ("linux-cmds", "06-users-and-permissions"),
    ("linux-cmds", "07-system-health"),
    ("linux-cmds", "08-network-and-archives"),
    ("linux-cmds", "09-help-yourself"),
    ("where-code-runs", "01-bare-metal-vs-vm"),
    ("where-code-runs", "02-containers"),
    ("where-code-runs", "03-the-cloud"),
]


def episode_dir(series, slug):
    return ROOT / "series" / series / slug


def _cmd_lint(argv):
    wanted = set(argv)
    selected = set(_select(argv))
    failed = False
    for series, slug in EPISODES:
        name = f"{series}/{slug}"
        if (series, slug) not in selected:
            continue
        folder = episode_dir(series, slug)
        if not (folder / "body.tape").exists() or not (folder / "voiceover.md").exists():
            print(f"-- {name}: missing files")
            failed = failed or not wanted
            continue
        tape, voiceover = (folder / "body.tape").read_text(), (folder / "voiceover.md").read_text()
        problems = lint_episode(tape, voiceover)
        print(f"{'OK' if not problems else '!!'} {name}  ~{estimate_duration(tape):.1f}s")
        for problem in problems:
            print(f"     {problem}")
        failed = failed or bool(problems)
    return 1 if failed else 0


ORIENTATIONS = ("vertical", "horizontal")
IMAGE = "chicanodev-vhs"


def caption_force_style(height, font_px, margin_px, outline_px):
    """ASS force_style with pixel sizes scaled to libass's 288px SRT canvas."""
    k = 288 / height
    return (f"Fontname=IBM Plex Mono,Bold=1,Fontsize={font_px * k:.3f},MarginV={margin_px * k:.3f},"
            f"Outline={outline_px * k:.3f},Shadow=0,Alignment=2")


CAPTION_STYLE = {
    "vertical": caption_force_style(1920, font_px=64, margin_px=420, outline_px=5),
    "horizontal": caption_force_style(1080, font_px=44, margin_px=56, outline_px=4),
}


def episode_id(series, slug):
    return f"{series}-{slug}"


def _select(argv):
    wanted = set(argv)
    return [(s, n) for s, n in EPISODES
            if not wanted or f"{s}/{n}" in wanted or n in wanted or s in wanted or episode_id(s, n) in wanted]


def _docker(*args, entrypoint=None):
    cmd = ["docker", "run", "--rm", "-v", f"{ROOT}:/vhs"]
    if entrypoint:
        cmd += ["--entrypoint", entrypoint]
    cmd += [IMAGE, *args]
    subprocess.run(cmd, check=True)


def write_srt(series, slug, duration=None, name="captions.srt"):
    """Write captions from the voiceover; with `duration`, stretch them to the rendered clip's real length."""
    folder = episode_dir(series, slug)
    beats = parse_voiceover((folder / "voiceover.md").read_text())
    cues = make_cues(beats)
    if duration:
        cues = scale_cues(cues, duration / beats[-1].end)
    path = ROOT / "build" / episode_id(series, slug) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_srt(cues))
    return path


def _cmd_srt(argv):
    for series, slug in _select(argv):
        print(write_srt(series, slug))
    return 0


def _cmd_render(argv):
    for series, slug in _select(argv):
        eid = episode_id(series, slug)
        body = (episode_dir(series, slug) / "body.tape").read_text()
        for orient in ORIENTATIONS:
            settings = (ROOT / "common" / f"{orient}.settings.tape").read_text()
            tape = ROOT / "build" / eid / f"{orient}.tape"
            tape.parent.mkdir(parents=True, exist_ok=True)
            tape.write_text(build_tape(settings, body, f"build/{eid}/{orient}-raw.mp4"))
            _docker(f"build/{eid}/{orient}.tape")
    return 0


def _cmd_burn(argv):
    for series, slug in _select(argv):
        eid = episode_id(series, slug)
        for orient in ORIENTATIONS:
            style = CAPTION_STYLE[orient]
            raw_seconds = _probe(ROOT / "build" / eid / f"{orient}-raw.mp4")[2]
            srt = write_srt(series, slug, raw_seconds, f"captions-{orient}.srt")
            out = ROOT / "out" / orient
            out.mkdir(parents=True, exist_ok=True)
            shutil.copy(srt, out / f"{eid}.srt")
            _docker(
                "-y", "-i", f"build/{eid}/{orient}-raw.mp4",
                "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                "-vf", f"subtitles=build/{eid}/{srt.name}:force_style='{style}'",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                f"out/{orient}/{eid}.mp4",
                entrypoint="ffmpeg",
            )
    return 0


def _probe(path):
    """(width, height, duration) of a video via ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True).stdout.split()
    width, height = out[0].split(",")
    return int(width), int(height), float(out[1])


def _cmd_verify(argv):
    failed = False
    for series, slug in _select(argv):
        eid = episode_id(series, slug)
        estimate = estimate_duration((episode_dir(series, slug) / "body.tape").read_text())
        for orient in ORIENTATIONS:
            clip = ROOT / "out" / orient / f"{eid}.mp4"
            if not clip.exists():
                print(f"-- {orient:10} {eid}: not rendered")
                failed = True
                continue
            problems = check_clip(orient, *_probe(clip), estimate)
            print(f"{'OK' if not problems else '!!'} {orient:10} {eid}")
            for problem in problems:
                print(f"     {problem}")
            failed = failed or bool(problems)
    return 1 if failed else 0


CARD_SECONDS = 2.0


def _title_card(series_dir_id, index, title):
    """2s Dracula title card (1920x1080, matching clip fps) rendered in the docker image."""
    head, _, tail = title.partition(": ")
    out = f"build/{series_dir_id}/card-{index:02}.mp4"
    plex = "/usr/share/fonts/ibm-plex-mono/IBMPlexMono-Bold.ttf"
    # textfile= avoids escaping ':' and '#' inside drawtext's own filter syntax.
    (ROOT / "build" / series_dir_id / f"card-{index:02}-head.txt").write_text(head)
    (ROOT / "build" / series_dir_id / f"card-{index:02}-tail.txt").write_text(tail or head)
    text = (f"drawtext=fontfile={plex}:textfile=build/{series_dir_id}/card-{index:02}-head.txt:"
            f"fontcolor=0x8be9fd:fontsize=48:x=(w-text_w)/2:y=h/2-90,"
            f"drawtext=fontfile={plex}:textfile=build/{series_dir_id}/card-{index:02}-tail.txt:"
            f"fontcolor=0xf8f8f2:fontsize=76:x=(w-text_w)/2:y=h/2")
    _docker("-y", "-f", "lavfi", "-i", f"color=c=0x282a36:s=1920x1080:r=50:d={CARD_SECONDS}",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-vf", text, "-t", str(CARD_SECONDS),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", out, entrypoint="ffmpeg")
    return out


def _parse_srt_cues(srt_text):
    cues = []
    for block in srt_text.strip().split("\n\n"):
        lines = block.splitlines()
        a, _, b = lines[1].partition(" --> ")
        cues.append(Cue(_srt_seconds(a), _srt_seconds(b), "\n".join(lines[2:])))
    return cues


def _srt_seconds(stamp):
    hms, millis = stamp.split(",")
    h, m, sec = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(millis) / 1000


def _cmd_compile(argv):
    voiced = "--final" in argv
    wanted = set(_names(argv))
    folder = "final/horizontal" if voiced else "horizontal"
    for series in dict.fromkeys(s for s, _ in EPISODES):
        if wanted and series not in wanted:
            continue
        episodes = [(s, n) for s, n in EPISODES if s == series]
        sets, concat, hooks = [], [], []
        for index, (s, n) in enumerate(episodes, 1):
            eid = episode_id(s, n)
            clip, srt = ROOT / "out" / folder / f"{eid}.mp4", ROOT / "out" / folder / f"{eid}.srt"
            clean = None
            if voiced:
                import pipeline
                clean = pipeline.clean_source(ROOT, eid)  # new-pipeline episode: use its brand-free master
                if clean:
                    clip, srt = clean.clip, clean.srt
            hooks.append(clean.hook_end if clean else None)
            if not clip.exists():
                print(f"{series}: {clip.name} missing in out/{folder}. " + ("Record and mux every part first." if voiced else "Render and burn first."))
                return 1
            title = parse_title((episode_dir(s, n) / "voiceover.md").read_text())
            (ROOT / "build" / series).mkdir(parents=True, exist_ok=True)
            card = _title_card(series, index, title)
            concat += [f"file '/vhs/{card}'", f"file '/vhs/{clip.relative_to(ROOT)}'"]
            sets.append((_parse_srt_cues(srt.read_text()), _probe(clip)[2]))
        listing = ROOT / "build" / series / "concat.txt"
        listing.write_text("\n".join(concat) + "\n")
        (ROOT / "out" / "youtube").mkdir(parents=True, exist_ok=True)
        suffix = "-voiced" if voiced else ""
        target = ROOT / "out" / "youtube" / f"{series}-full{suffix}.mp4"
        # The brand clip goes in ONCE per compilation, and only for episodes made by the narration pipeline
        # (or when asked for explicitly), so existing legacy compilations are unchanged.
        placement = _flag(argv, "--brand-placement", "after-hook" if any(hooks) else "none") if voiced else "none"
        concat_out = ROOT / "build" / series / "compiled.mp4" if placement != "none" else target
        _docker("-y", "-f", "concat", "-safe", "0", "-i", f"build/{series}/concat.txt",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(concat_out.relative_to(ROOT)),
                entrypoint="ffmpeg")
        merged = offset_cues(merge_cue_sets(sets, gap=CARD_SECONDS), CARD_SECONDS)
        if placement != "none":
            import pipeline
            hook_end = CARD_SECONDS + (hooks[0] or 6.0)
            try:
                _, merged = pipeline.brand_compilation(concat_out, merged, placement, hook_end,
                                                       ROOT / pipeline.INTRO, ROOT / "build" / series, target)
            except ValueError as err:
                print(f"{series}: {err}")
                return 1
        (ROOT / "out" / "youtube" / f"{series}-full{suffix}.srt").write_text(format_srt(merged))
        print(f"out/youtube/{series}-full{suffix}.mp4  ({len(episodes)} parts" + (f", brand clip once: {placement}" if placement != "none" else "") + ")")
    return 0


def _cmd_script(argv):
    for series, slug in _select(argv):
        md = (episode_dir(series, slug) / "voiceover.md").read_text()
        print(f"=== {series}/{slug}: {parse_title(md)}\n")
        print(narration_text(md))
    return 0


def _cmd_pace(argv):
    flagged = False
    for series, slug in _select(argv):
        beats = parse_voiceover((episode_dir(series, slug) / "voiceover.md").read_text())
        print(f"=== {series}/{slug}")
        for p in beat_pace(beats):
            note = "  <- TOO FAST, trim words" if p.too_fast else "  <- slow, add a line or pause" if p.too_slow else ""
            print(f"  {p.title:<18} {p.seconds:>4.0f}s  {p.words:>3} words  {p.wpm:>4.0f} wpm{note}")
            flagged = flagged or p.too_fast
    return 1 if flagged else 0


def _audio_seconds(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         check=True, capture_output=True, text=True).stdout.strip()
    return float(out)


def _cmd_mux(argv):
    """Voice recording + silent render -> finished video with captions timed to the voice."""
    audio_dir = ROOT / "audio"
    missing = []
    for series, slug in _select(argv):
        eid = episode_id(series, slug)
        audio = find_audio(eid, audio_dir)
        if audio is None:
            missing.append(eid)
            continue
        voice = _audio_seconds(audio)
        for orient in ORIENTATIONS:
            raw = ROOT / "build" / eid / f"{orient}-raw.mp4"
            if not raw.exists():
                print(f"{eid}: {raw.name} missing. Run: python3 tools/vidkit.py render {series}/{slug}")
                return 1
            video = _probe(raw)[2]
            final, hold = plan_mux(video, voice)
            srt = write_srt(series, slug, voice, f"final-{orient}.srt")
            out = ROOT / "out" / "final" / orient
            out.mkdir(parents=True, exist_ok=True)
            shutil.copy(srt, out / f"{eid}.srt")
            vf = f"subtitles=build/{eid}/{srt.name}:force_style='{CAPTION_STYLE[orient]}'"
            if hold > 0.05:
                vf = f"tpad=stop_mode=clone:stop_duration={hold:.2f}," + vf
            _docker("-y", "-i", f"build/{eid}/{orient}-raw.mp4", "-i", f"audio/{audio.name}",
                    "-map", "0:v", "-map", "1:a", "-vf", vf,
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,apad", "-t", f"{final:.2f}", "-ac", "2", "-ar", "48000",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                    f"out/final/{orient}/{eid}.mp4", entrypoint="ffmpeg")
        verdict = f"video held {hold:.1f}s so your voice fits" if hold > 0.05 else "voice fits inside the video"
        print(f"{eid}: voice {voice:.1f}s, video {video:.1f}s, final {final:.1f}s ({verdict})")
    for eid in missing:
        print(f"{eid}: no recording found. Put it at audio/{eid}.wav")
    return 1 if missing and len(missing) == len(_select(argv)) else 0


def _cmd_chapters(argv):
    """Print YouTube chapter lines for each series' long video, ready to paste into the description."""
    voiced = "--final" in argv
    folder = "final/horizontal" if voiced else "horizontal"
    names = [a for a in argv if not a.startswith("--")]
    for series in dict.fromkeys(s for s, _ in EPISODES):
        if names and series not in names:
            continue
        episodes = [(s, n) for s, n in EPISODES if s == series]
        clips = [ROOT / "out" / folder / f"{episode_id(s, n)}.mp4" for s, n in episodes]
        if not all(c.exists() for c in clips):
            print(f"{series}: some clips are missing in out/{folder}")
            return 1
        titles = [parse_title((episode_dir(s, n) / "voiceover.md").read_text()).partition(": ")[2] for s, n in episodes]
        print(f"--- {series}\n" + "\n".join(chapter_lines([t.capitalize() if t.islower() else t for t in titles],
                                                         [_probe(c)[2] for c in clips], CARD_SECONDS)) + "\n")
    return 0


def _cmd_segments(argv):
    """Numbered narration chunks with the exact filename to record each one as."""
    import narration
    for series, slug in _select(argv):
        folder = episode_dir(series, slug)
        selected = narration.load_alignment(folder).get("selected") or {}
        print(f"=== {series}/{slug}: record each segment as videos/series/{series}/{slug}/narration/<name>.m4a (or .wav/.mp3)\n")
        for seg in narration.episode_segments(folder):
            try:
                state = "recorded" if narration.resolve_take(folder / "narration", seg.id, selected) else "todo"
            except narration.AmbiguousTake:
                state = "pick take"
            print(f"{seg.index:>2}. [{state}] {seg.id}  ->  narration/{seg.id}.m4a")
            print(f"      {seg.text}\n")
    return 0


def _cmd_check_audio(argv):
    """Validate every segment recording; print the fix for each problem."""
    import narration
    failed = False
    for series, slug in _select(argv):
        folder = episode_dir(series, slug)
        selected = narration.load_alignment(folder).get("selected") or {}
        print(f"=== {series}/{slug}")
        for seg in narration.episode_segments(folder):
            try:
                take = narration.resolve_take(folder / "narration", seg.id, selected)
                if take is None:
                    print(f"!! {seg.id}: not recorded. Save it as narration/{seg.id}.m4a")
                    failed = True
                    continue
                problems = narration.audio_problems(narration.measure(take))
            except (narration.AmbiguousTake, narration.BadAudio) as err:
                print(f"!! {seg.id}: {err}")
                failed = True
                continue
            print(f"{'OK' if not problems else '!!'} {seg.id}  ({take.name})")
            for problem in problems:
                print(f"     {problem}")
            failed = failed or bool(problems)
    return 1 if failed else 0


def work_dir(series, slug):
    return ROOT / "out" / "intermediate" / episode_id(series, slug)


def _print_review(segments, folder):
    """Print per-segment transcript review notes. Returns False if any transcript is missing."""
    import transcribe
    complete = True
    for seg in segments:
        if not transcribe.exists(folder / "transcript", seg.id):
            print(f"-- {seg.id}: no transcript yet. Run: python3 tools/vidkit.py transcribe <episode>")
            complete = False
            continue
        t = transcribe.load(folder / "transcript", seg.id)
        flags = transcribe.review_flags(t.words, seg.text)
        note = " (edited)" if t.has_edits else ""
        print(f"{'OK' if not flags else '??'} {seg.id}{note}  -> transcript/{seg.id}.yaml")
        for f in flags:
            if f.kind == "low-confidence":
                print(f"     {f.start:6.2f}s low-confidence: '{f.word}'")
            else:
                heard = f"'{f.word}'" if f.word else "nothing"
                print(f"     {f.start:6.2f}s differs-from-script: heard {heard}, script has '{f.expected or '(nothing)'}'")
    return complete


def _cmd_transcribe(argv):
    """Ingest takes, transcribe changed ones with local whisper, then show what to double-check."""
    import narration
    import transcribe
    engine = None
    for series, slug in _select(argv):
        folder = episode_dir(series, slug)
        segments = narration.episode_segments(folder)
        selected = narration.load_alignment(folder).get("selected") or {}
        print(f"=== {series}/{slug}")
        try:
            report = narration.prepare(segments, folder / "narration", work_dir(series, slug), selected)
        except (narration.MissingTakes, narration.AmbiguousTake, narration.BadAudio) as err:
            print(f"!! {err}")
            return 1
        for item in report:
            engine = engine or transcribe.whisper_engine()
            status = transcribe.ensure(item.segment, item.audio_sha, item.wav, folder / "transcript", engine, "--force" in argv)
            print(f"   {item.segment.id}: audio {item.status}, transcript {status}")
        _print_review(segments, folder)
    return 0


def _cmd_transcript(argv):
    """Show transcript review notes without running anything. Edit transcript/<segment>.yaml to fix words."""
    import narration
    complete = True
    for series, slug in _select(argv):
        folder = episode_dir(series, slug)
        print(f"=== {series}/{slug}")
        complete = _print_review(narration.episode_segments(folder), folder) and complete
    return 0 if complete else 1


VALUE_FLAGS = ("--format", "--brand-placement", "--by")
FORMATS = {"vertical": ["vertical"], "horizontal": ["horizontal"], "both": ["vertical", "horizontal"]}


def _flag(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def _names(argv):
    """Episode/series names: everything that is not a flag or a flag's value."""
    skip = {argv.index(f) + 1 for f in VALUE_FLAGS if f in argv}
    return [a for i, a in enumerate(argv) if not a.startswith("-") and i not in skip]


def _who(argv):
    if _flag(argv, "--by"):
        return _flag(argv, "--by")
    git = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
    return git or __import__("getpass").getuser()


def _build_one(series, slug, argv, env):
    """Build one episode and print the result. Returns (ok, message_if_not)."""
    import approval
    import compose
    import media_errors
    import pipeline
    eid = episode_id(series, slug)
    final_root = env.root / "out" / "final"
    fmt = _flag(argv, "--format", "both")
    if fmt not in FORMATS:
        return False, f"unknown --format {fmt}. Use vertical, horizontal or both."
    cfg = pipeline.Config(formats=FORMATS[fmt], placement=_flag(argv, "--brand-placement"), force="--force" in argv,
                          dry_run="--dry-run" in argv, verbose=bool({"-v", "--verbose"} & set(argv)))
    before = approval.current(final_root, eid)
    try:
        if cfg.placement:
            compose.check_placement(cfg.placement)
        result = pipeline.build_episode(series, slug, cfg, env)
    except media_errors.EXPECTED as err:
        return False, str(err)
    if cfg.dry_run:
        print(f"=== {series}/{slug} (dry run, nothing written)")
        for line in result.plan_lines:
            print(f"   {line}")
        return True, ""
    ran = sorted(k for k, v in result.stage_status.items() if v == "ran")
    print(f"=== {series}/{slug}: " + (f"ran {', '.join(ran)}" if ran else "everything cached, nothing to redo"))
    ok = True
    for orient, path in result.outputs.items():
        problems = result.qa[orient]
        print(f"{'OK' if not problems else '!!'} {orient:10} {path.relative_to(env.root)}  "
              f"({result.placements[orient]} brand)")
        for problem in problems:
            print(f"     {problem}")
        ok = ok and not problems
    state = result.status.state
    if before and before.state == "approved" and state != "approved":
        print("   Approval voided: the content changed. Review again, then approve.")
    if state == "approved":
        print("   Unchanged since you approved it.")
    elif ok:
        print(f"   NOT approved yet. Watch it on your phone, then: python3 tools/vidkit.py approve {series}/{slug}")
    return ok, ""


def _cmd_build(argv):
    import pipeline
    if not _names(argv):
        print("build needs an episode, e.g. python3 tools/vidkit.py build linux-fs/01-no-c-drive --format vertical\n"
              "(use batch-build for a whole series)")
        return 2
    env = pipeline.docker_env(log=print)
    failed = False
    for series, slug in _select(_names(argv)):
        ok, message = _build_one(series, slug, argv, env)
        if message:
            print(f"!! {series}/{slug}: {message}")
        failed = failed or not ok
    return 1 if failed else 0


def _cmd_batch_build(argv):
    """Build every complete episode of a series; skip unrecorded ones and anything already approved."""
    import approval
    import media_errors
    import narration
    import pipeline
    env = pipeline.docker_env(log=lambda m: None)
    built, skipped, failed = [], [], []
    for series, slug in _select(_names(argv)):
        eid = episode_id(series, slug)
        folder = episode_dir(series, slug)
        current = approval.current(env.root / "out" / "final", eid)
        if current and current.state == "approved" and "--force" not in argv:
            skipped.append(f"{eid} (approved, use --force to rebuild)")
            continue
        selected = narration.load_alignment(folder).get("selected") or {}
        missing = [s.id for s in narration.episode_segments(folder)
                   if _safe_take(narration, folder, s.id, selected) is None]
        if missing:
            skipped.append(f"{eid} (not fully recorded: missing {', '.join(missing)})")
            continue
        try:
            ok, message = _build_one(series, slug, argv, env)
        except media_errors.EXPECTED as err:
            ok, message = False, str(err)
        (built if ok else failed).append(eid if ok else f"{eid}: {message or 'failed checks'}")
    print("\nbatch summary")
    print(f"  built: {', '.join(built) or '-'}")
    for line in skipped:
        print(f"  skipped: {line}")
    for line in failed:
        print(f"  FAILED: {line}")
    return 1 if failed else 0


def _safe_take(narration, folder, seg_id, selected):
    try:
        return narration.resolve_take(folder / "narration", seg_id, selected)
    except narration.AmbiguousTake:
        return folder  # present but ambiguous: let the build report it


REVIEW_CHECKLIST = """Review checklist (watch the files below on your phone, with sound):
  [ ] Your voice is clear: no clipped words, steady volume
  [ ] Captions say what you said (fix words in transcript/<segment>.yaml, then rebuild)
  [ ] Each command is on screen about when you say it
  [ ] Text is readable at phone size; captions do not cover terminal output
  [ ] Narration finishes before the ChicanoDev outro/intro starts
"""


def _cmd_review(argv):
    import approval
    import compose
    import pipeline
    env = pipeline.docker_env()
    final_root = env.root / "out" / "final"
    missing = False
    for series, slug in _select(_names(argv)):
        eid = episode_id(series, slug)
        status = approval.current(final_root, eid)
        if status is None:
            print(f"{eid}: nothing built yet. Run: python3 tools/vidkit.py build {series}/{slug}")
            missing = True
            continue
        print(f"=== {series}/{slug}: {status.state}" + (f" by {status.approved_by} at {status.approved_at}" if status.approved_by else ""))
        for label, info in status.files.items():
            path = final_root / info["path"]
            length = f"{compose.seconds(path):.1f}s" if path.exists() else "MISSING"
            print(f"   {label:10} {path.relative_to(env.root)}  {length}")
            if "--open" in argv and path.exists():
                subprocess.run(["open", str(path)])
        for problem in status.qa_problems:
            print(f"   !! {problem}")
        print(f"   notes: {(final_root / f'{eid}.meta.md').relative_to(env.root)}")
        _print_review(__import__("narration").episode_segments(episode_dir(series, slug)), episode_dir(series, slug))
        print(REVIEW_CHECKLIST + f"When happy: python3 tools/vidkit.py approve {series}/{slug}")
    return 1 if missing else 0


def _cmd_approve(argv):
    import approval
    import pipeline
    env = pipeline.docker_env()
    failed = False
    for series, slug in _select(_names(argv)):
        eid = episode_id(series, slug)
        try:
            status = approval.approve(env.root / "out" / "final", eid, _who(argv))
        except approval.NotApprovable as err:
            print(f"!! {err}")
            failed = True
            continue
        print(f"approved {eid} by {status.approved_by}. It is now in the publish backlog.")
    return 1 if failed else 0


def _cmd_backlog(argv):
    import approval
    import pipeline
    env = pipeline.docker_env()
    items = approval.backlog(env.root / "out" / "final")
    if not items:
        print("Nothing approved yet. Build, review, then approve an episode.")
        return 0
    print("Approved and ready to publish manually (YouTube Studio / Meta):")
    for st in items:
        print(f"  {st.eid}  approved {st.approved_at} by {st.approved_by}")
        for label, info in st.files.items():
            print(f"      {label}: out/final/{info['path']}")
        print(f"      notes: out/final/{st.eid}.meta.md")
    return 0


COMMANDS = {"lint": _cmd_lint, "srt": _cmd_srt, "render": _cmd_render, "burn": _cmd_burn,
            "verify": _cmd_verify, "compile": _cmd_compile,
            "script": _cmd_script, "pace": _cmd_pace, "mux": _cmd_mux, "chapters": _cmd_chapters,
            "segments": _cmd_segments, "check-audio": _cmd_check_audio,
            "transcribe": _cmd_transcribe, "transcript": _cmd_transcript,
            "build": _cmd_build, "batch-build": _cmd_batch_build, "review": _cmd_review,
            "approve": _cmd_approve, "backlog": _cmd_backlog}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in COMMANDS:
        print(f"usage: vidkit.py {{{'|'.join(COMMANDS)}}} [episode ...]")
        return 2
    names = _names(argv[1:])
    if names and not _select(names):
        print(f"unknown episode or series: {' '.join(names)}. Try one like linux-fs/01-no-c-drive or linux-fs.")
        return 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main())
