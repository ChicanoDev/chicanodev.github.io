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
    failed = False
    for series, slug in EPISODES:
        name = f"{series}/{slug}"
        if wanted and name not in wanted and slug not in wanted:
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
    return [(s, n) for s, n in EPISODES if not wanted or f"{s}/{n}" in wanted or n in wanted or s in wanted]


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
    wanted = set(argv)
    for series in dict.fromkeys(s for s, _ in EPISODES):
        if wanted and series not in wanted:
            continue
        episodes = [(s, n) for s, n in EPISODES if s == series]
        sets, concat = [], []
        for index, (s, n) in enumerate(episodes, 1):
            eid = episode_id(s, n)
            clip = ROOT / "out" / "horizontal" / f"{eid}.mp4"
            if not clip.exists():
                print(f"{series}: {clip.name} missing, render + burn first")
                return 1
            title = parse_title((episode_dir(s, n) / "voiceover.md").read_text())
            (ROOT / "build" / series).mkdir(parents=True, exist_ok=True)
            card = _title_card(series, index, title)
            concat += [f"file '/vhs/{card}'", f"file '/vhs/out/horizontal/{clip.name}'"]
            sets.append((_parse_srt_cues((ROOT / "out" / "horizontal" / f"{eid}.srt").read_text()), _probe(clip)[2]))
        listing = ROOT / "build" / series / "concat.txt"
        listing.write_text("\n".join(concat) + "\n")
        (ROOT / "out" / "youtube").mkdir(parents=True, exist_ok=True)
        _docker("-y", "-f", "concat", "-safe", "0", "-i", f"build/{series}/concat.txt",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", f"out/youtube/{series}-full.mp4",
                entrypoint="ffmpeg")
        merged = offset_cues(merge_cue_sets(sets, gap=CARD_SECONDS), CARD_SECONDS)
        (ROOT / "out" / "youtube" / f"{series}-full.srt").write_text(format_srt(merged))
        print(f"out/youtube/{series}-full.mp4  ({len(episodes)} parts)")
    return 0


COMMANDS = {"lint": _cmd_lint, "srt": _cmd_srt, "render": _cmd_render, "burn": _cmd_burn,
            "verify": _cmd_verify, "compile": _cmd_compile}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in COMMANDS:
        print(f"usage: vidkit.py {{{'|'.join(COMMANDS)}}} [episode ...]")
        return 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main())
