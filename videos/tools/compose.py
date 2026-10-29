"""FFmpeg composition: master (voice + video), brand clip, intro/outro assembly, and output QA."""
import json
import re
import subprocess
from pathlib import Path

import vidkit

FPS, RATE = 30, 48000
CANVAS = {"vertical": (1080, 1920), "horizontal": (1920, 1080)}
PLACEMENTS = ("outro", "after-hook", "none", "both")
BG, ACCENT = "0x282a36", "0xbd93f9"
ENCODE = ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(FPS),
          "-c:a", "aac", "-b:a", "192k", "-ar", str(RATE), "-ac", "2", "-movflags", "+faststart"]


class MediaError(Exception):
    """ffmpeg/ffprobe could not do what we asked."""


def default_placement(orient):
    return "outro" if orient == "vertical" else "after-hook"


def check_placement(placement):
    if placement not in PLACEMENTS:
        raise ValueError(f"unknown brand placement '{placement}'. Choose one of: {', '.join(PLACEMENTS)}")
    return placement


def brand_slots(placement):
    return {"outro": ["end"], "after-hook": ["hook"], "none": [], "both": ["hook", "end"]}[check_placement(placement)]


def run_ffmpeg(*args):
    result = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-nostdin", "-v", "error", *map(str, args)],
                            capture_output=True, text=True)
    if result.returncode:
        raise MediaError(result.stderr.strip() or "ffmpeg failed")


def probe(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                            capture_output=True, text=True)
    try:
        data = json.loads(result.stdout)
        data["format"]["duration"]
    except (ValueError, KeyError):
        raise MediaError(f"{Path(path).name}: not a readable media file") from None
    return data


def seconds(path):
    return float(probe(path)["format"]["duration"])


def _has_audio(path):
    return any(s["codec_type"] == "audio" for s in probe(path)["streams"])


def brand_clip(src, dst, orient):
    """The brand animation as a standard clip: canvas-sized (contained, never cropped or stretched),
    30 fps, yuv420p, 48 kHz stereo audio (silent if the source has none)."""
    w, h = CANVAS[orient]
    length = seconds(src)
    if orient == "vertical":
        top = f"ih/2-{round(w * 9 / 16 / 2) + 4}"
        bottom = f"ih/2+{round(w * 9 / 16 / 2)}"
        video = (f"color=c={BG}:s={w}x{h}:r={FPS}[bg];[0:v]scale={w}:-2:flags=lanczos,fps={FPS},format=yuv420p[fg];"
                 f"[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,"
                 f"drawbox=x=0:y={top}:w=iw:h=4:color={ACCENT}@0.8:t=fill,"
                 f"drawbox=x=0:y={bottom}:w=iw:h=4:color={ACCENT}@0.8:t=fill[v]")
    else:
        video = (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={BG},"
                 f"fps={FPS},format=yuv420p[v]")
    if _has_audio(src):
        audio, extra = f"[0:a]aresample={RATE},aformat=channel_layouts=stereo[a]", []
    else:
        audio, extra = f"[1:a]atrim=0:{length:.3f}[a]", ["-f", "lavfi", "-i", f"anullsrc=r={RATE}:cl=stereo"]
    run_ffmpeg("-i", src, *extra, "-filter_complex", f"{video};{audio}", "-map", "[v]", "-map", "[a]",
               "-t", f"{length:.3f}", *ENCODE, dst)
    return Path(dst)


def master(raw, voice, dst, min_seconds=None):
    """Clean master: silent terminal render + narration, 30 fps, no captions. The video is held on its
    last frame if the narration (or `min_seconds`) runs longer than the render."""
    raw_len = seconds(raw)
    total = max(raw_len, seconds(voice), min_seconds or 0)
    hold = total - raw_len
    video = f"[0:v]fps={FPS},tpad=stop_mode=clone:stop_duration={hold:.3f},format=yuv420p[v]"
    audio = f"[1:a]aformat=sample_rates={RATE}:channel_layouts=stereo,apad[a]"
    run_ffmpeg("-i", raw, "-i", voice, "-filter_complex", f"{video};{audio}", "-map", "[v]", "-map", "[a]",
               "-t", f"{total:.3f}", *ENCODE, dst)
    return Path(dst)


def assemble(main, brand, dst, placement, hook_end):
    """Insert the brand clip per `placement`. The (already captioned) main video is only cut, never re-captioned."""
    slots = brand_slots(placement)
    if not slots:
        run_ffmpeg("-i", main, "-c", "copy", "-movflags", "+faststart", dst)
        return Path(dst)
    total = seconds(main)
    cut = min(max(hook_end, 0.1), total - 0.1)
    pieces = []  # ("m", start, end) or ("b",)
    if "hook" in slots:
        pieces += [("m", 0, cut), ("b",), ("m", cut, None)]
    else:
        pieces += [("m", 0, None)]
    if "end" in slots:
        pieces += [("b",)]
    masters = [p for p in pieces if p[0] == "m"]
    inputs, graph, labels = ["-i", main], [], []
    if len(masters) > 1:
        graph += [f"[0:v]split={len(masters)}" + "".join(f"[mv{i}]" for i in range(len(masters))),
                  f"[0:a]asplit={len(masters)}" + "".join(f"[ma{i}]" for i in range(len(masters)))]
    brand_n, master_n = 0, 0
    for piece in pieces:
        n = len(labels)
        if piece[0] == "b":
            brand_n += 1
            inputs += ["-i", brand]
            idx = brand_n
            graph += [f"[{idx}:v]setpts=PTS-STARTPTS[v{n}]", f"[{idx}:a]asetpts=PTS-STARTPTS[a{n}]"]
        else:
            _, start, end = piece
            vin = f"[mv{master_n}]" if len(masters) > 1 else "[0:v]"
            ain = f"[ma{master_n}]" if len(masters) > 1 else "[0:a]"
            span = f"start={start}" + (f":end={end}" if end is not None else "")
            graph += [f"{vin}trim={span},setpts=PTS-STARTPTS[v{n}]", f"{ain}atrim={span},asetpts=PTS-STARTPTS[a{n}]"]
            master_n += 1
        labels.append(n)
    joined = "".join(f"[v{n}][a{n}]" for n in labels)
    graph.append(f"{joined}concat=n={len(labels)}:v=1:a=1[v][a]")
    run_ffmpeg(*inputs, "-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]", *ENCODE, dst)
    return Path(dst)


def shift_cues(cues, placement, hook_end, brand_seconds):
    """Sidecar captions for the final timeline: later cues move by the length of a brand clip inserted after the hook."""
    if "hook" not in brand_slots(placement):
        return list(cues)
    out = []
    for c in cues:
        if c.start >= hook_end:
            out.append(vidkit.Cue(c.start + brand_seconds, c.end + brand_seconds, c.text))
        else:
            out.append(vidkit.Cue(c.start, min(c.end, hook_end), c.text))
    return out


def qa_problems(path, orient, expected_seconds, brand_slots, brand_seconds, tolerance=0.5):
    """Everything wrong with a finished file; an empty list means it passes the automatic checks."""
    try:
        data = probe(path)
    except MediaError as err:
        return [str(err)]
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    problems = []
    w, h = CANVAS[orient]
    if not video:
        return ["no video stream"]
    if (video["width"], video["height"]) != (w, h):
        problems.append(f"expected {w}x{h}, got {video['width']}x{video['height']}")
    if video["codec_name"] != "h264" or video["pix_fmt"] != "yuv420p":
        problems.append(f"expected h264/yuv420p, got {video['codec_name']}/{video['pix_fmt']}")
    if video["r_frame_rate"] != f"{FPS}/1":
        problems.append(f"expected {FPS} fps, got {video['r_frame_rate']}")
    if not audio or audio["codec_name"] != "aac":
        problems.append("expected AAC audio")
    else:
        log = subprocess.run(["ffmpeg", "-nostdin", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                             capture_output=True, text=True).stderr
        peak = re.search(r"max_volume:\s*(-?[\d.]+) dB", log)
        if not peak or float(peak.group(1)) < -60:
            problems.append("output is silent (no narration audible)")
    actual = float(data["format"]["duration"])
    if abs(actual - expected_seconds) > tolerance:
        hint = ""
        if brand_seconds and abs(abs(actual - expected_seconds) - brand_seconds) <= tolerance:
            hint = " (looks like the brand clip was added twice or not at all)"
        problems.append(f"duration {actual:.1f}s but expected {expected_seconds:.1f}s{hint}")
    return problems
