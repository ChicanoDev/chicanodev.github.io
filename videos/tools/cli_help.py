"""Help text for vidkit: the command registry and the renderers for `vidkit.py` and `vidkit.py <cmd> --help`.

Standard library only (no venv, Docker, whisper or microphone needed). Keep the entries here in step
with the `_cmd_*` functions in vidkit.py; tests check that every command has an entry.
"""
import difflib
from dataclasses import dataclass

import cli_ui

PROG = "python3 tools/vidkit.py"
EP = "linux-fs/02-where-programs-live"
EPISODE_ARG = ("episode", "Episode as series/slug (e.g. " + EP + "), a bare slug, or a series name for all its episodes")

GROUPS = ("GETTING STARTED", "VIDEO PRODUCTION", "QUALITY & REVIEW", "SERIES & LEGACY TOOLS")


@dataclass(frozen=True)
class Info:
    group: str
    summary: str
    detail: str
    args: tuple = (EPISODE_ARG,)
    options: tuple = ()
    examples: tuple = ()
    optional_episode: bool = False


def _ex(name, extra=""):
    return (f"{PROG} {name} {EP}{extra}",)


COMMAND_INFO = {
    "record": Info(
        GROUPS[0], "Record narration, one segment at a time",
        "Interactive narration studio. Shows each segment's script, records from your microphone, plays the take "
        "back, and files the approved take as narration/<segment>.wav, ready for check-audio and build. Quit any time; "
        "run it again to resume. Approving a take here is separate from `approve` (the finished video).",
        options=(("--segment ID", "Record or revisit one segment, e.g. 04-local"),
                 ("--device ID|NAME", "Microphone to use (default: system input)"),
                 ("--list-devices", "List microphones and exit"),
                 ("--status", "Show approved / pending / missing segments and exit"),
                 ("--no-autoplay", "Do not play each take automatically after recording")),
        examples=_ex("record") + _ex("record", " --segment 04-local") + _ex("record", " --status")),
    "segments": Info(
        GROUPS[0], "Show the script's recording sections",
        "Lists the numbered narration segments with their exact text and whether each is recorded, and creates "
        "the narration/ folder.", examples=_ex("segments")),
    "script": Info(
        GROUPS[0], "Display the narration script",
        "Prints the voiceover text of the episode with timing headings removed.", examples=_ex("script")),
    "check-audio": Info(
        GROUPS[0], "Validate recorded audio",
        "Checks every segment recording for length, clipping, low level and too much silence, and prints the fix "
        "for each problem. Exits 1 if any segment is missing or has a problem.", examples=_ex("check-audio")),
    "transcribe": Info(
        GROUPS[1], "Generate word-timed transcripts",
        "Cleans each segment recording, then transcribes changed ones with local Whisper so captions match your "
        "voice. Prints words worth double-checking. Edit transcript/<segment>.yaml to fix words.",
        options=(("--force", "Redo transcripts even when the audio is unchanged"),),
        examples=_ex("transcribe")),
    "transcript": Info(
        GROUPS[1], "Review or manage transcript corrections",
        "Shows transcript review notes without running anything. Exits 1 if a transcript is missing.",
        examples=_ex("transcript")),
    "build": Info(
        GROUPS[1], "Create a finished branded video",
        "Runs the full pipeline (audio, transcripts, captions, render, brand, QA) and only redoes stages whose "
        "inputs changed. Needs Docker. The result is not approved until you review it.",
        options=(("--format F", "vertical, horizontal or both (default: both)"),
                 ("--brand-placement P", "Where the brand sits, or none"),
                 ("--force", "Rebuild every stage"),
                 ("--dry-run", "Show the plan; write nothing"),
                 ("-v, --verbose", "Show more detail")),
        examples=_ex("build", " --format both") + _ex("build", " --dry-run")),
    "batch-build": Info(
        GROUPS[1], "Build multiple episodes",
        "Builds every fully recorded episode of a series. Skips unrecorded episodes and ones already approved.",
        options=(("--format F", "vertical, horizontal or both"), ("--force", "Rebuild approved episodes too"),
                 ("--brand-placement P", "Where the brand sits, or none")),
        args=(("series", "Series name, e.g. linux-fs (default: all)"),),
        examples=(f"{PROG} batch-build linux-fs",), optional_episode=True),
    "render": Info(
        GROUPS[1], "Generate silent terminal recordings",
        "Renders the episode's VHS tape in both orientations using Docker. Output goes to build/.",
        examples=_ex("render")),
    "burn": Info(
        GROUPS[1], "Add captions to video",
        "Burns estimated captions from voiceover.md into the rendered clips and writes out/<orientation>/.",
        examples=_ex("burn")),
    "lint": Info(
        GROUPS[2], "Check episode scripts and metadata",
        "Checks the tape and voiceover for length, missing beats and other script problems. Exits 1 on problems.",
        optional_episode=True, examples=_ex("lint")),
    "pace": Info(
        GROUPS[2], "Estimate narration pacing",
        "Words per minute for each voiceover section; flags sections that are too fast or slow.",
        examples=_ex("pace")),
    "verify": Info(
        GROUPS[2], "Verify required rendered assets",
        "Checks rendered clips exist and have the right size and duration. Exits 1 on problems.",
        examples=_ex("verify")),
    "review": Info(
        GROUPS[2], "Preview a completed video",
        "Shows the built files, QA notes, transcript flags and a review checklist for the finished video.",
        options=(("--open", "Open the files in the default player"),), examples=_ex("review", " --open")),
    "approve": Info(
        GROUPS[2], "Mark a reviewed build as approved",
        "Approves the finished video (not a narration take) and adds it to the publish backlog. Any later change "
        "voids the approval.",
        options=(("--by NAME", "Name to record (default: git user.name)"),), examples=_ex("approve")),
    "backlog": Info(
        GROUPS[2], "Show video production status",
        "Lists approved videos ready to publish by hand, with file paths.",
        args=(), examples=(f"{PROG} backlog",)),
    "compile": Info(
        GROUPS[3], "Combine episodes into a longer video",
        "Joins a series' episodes with title cards into one long video and chapter timestamps.",
        options=(("--final", "Use the voiced, branded finished videos"),),
        args=(("series", "Series name, e.g. linux-fs"),), examples=(f"{PROG} compile linux-fs --final",),
        optional_episode=True),
    "chapters": Info(
        GROUPS[3], "Generate YouTube chapter timestamps",
        "Prints chapter lines for each series' long video, ready to paste into the description.",
        args=(("series", "Series name (default: all)"),), examples=(f"{PROG} chapters linux-fs",),
        optional_episode=True),
    "srt": Info(
        GROUPS[3], "Generate subtitle files",
        "Writes estimated subtitles from voiceover.md and prints the path.", examples=_ex("srt")),
    "mux": Info(
        GROUPS[3], "Combine legacy narration and video",
        "Older flow: one voice recording in audio/<id>.wav plus the silent render becomes a finished video with "
        "captions. New episodes should use record and build.", examples=_ex("mux")),
}

HOME_EXAMPLES = (
    ("Record an episode", f"record {EP}"),
    ("Build a finished video", f"build {EP} --format both"),
    ("Review the result", f"review {EP}"),
    ("Show all episodes", "backlog"),
)


def _plain_rows(rows, w, indent="  ", gap=2, label_w=None):
    """Two-column rows ((label, text)) wrapped to width."""
    label_w = label_w or min(max(len(r[0]) for r in rows), max(10, w // 2))
    lines = []
    for label, text in rows:
        text_lines = cli_ui.wrap(text, max(10, w - len(indent) - label_w - gap))
        if len(label) > label_w:  # long label: its own line, text underneath
            lines.append(indent + cli_ui.paint(label, cli_ui.CYAN))
            head = " " * label_w
        else:
            head = cli_ui.paint(label.ljust(label_w), cli_ui.CYAN)
        lines.append(indent + head + " " * gap + text_lines[0])
        lines.extend(indent + " " * (label_w + gap) + t for t in text_lines[1:])
    return lines


def main_help():
    w = cli_ui.width()
    out = [cli_ui.panel(["", "CHICANODEV VIDKIT", "Video Production Toolkit", "",
                         "Record > Transcribe > Build > Review > Publish", ""], w=w, center=True), ""]
    for group in GROUPS:
        out.append(cli_ui.heading(group))
        out += _plain_rows([(n, i.summary) for n, i in COMMAND_INFO.items() if i.group == group], w,
                           label_w=max(map(len, COMMAND_INFO)))
        out.append("")
    out.append(cli_ui.heading("EXAMPLES"))
    for label, cmd in HOME_EXAMPLES:
        out.append(f"  {label}:")
        out += cli_ui.wrap(f"{PROG} {cmd}", w - 4, "    ")
    out += ["", f"Run '{PROG} <command> --help'", "for command-specific help."]
    return "\n".join(out)


def command_help(name):
    info = COMMAND_INFO[name]
    w = cli_ui.width()
    ep = ""
    if info.args:
        ep = f" [{info.args[0][0]}]" if info.optional_episode else f" <{info.args[0][0]}>"
    usage = f"{PROG} {name}{ep}" + (" [options]" if info.options else "")
    out = [cli_ui.heading(f"CHICANODEV VIDKIT / {name.upper()}"), ""]
    out += cli_ui.wrap(info.detail, w) + ["", cli_ui.heading("Usage:")]
    out += cli_ui.wrap(usage, w - 2, "  ")
    if info.args:
        out += ["", cli_ui.heading("Arguments:")] + _plain_rows([(f"<{a}>", d) for a, d in info.args], w)
    out += ["", cli_ui.heading("Options:")]
    out += _plain_rows(list(info.options) + [("-h, --help", "Show this help")], w)
    out += ["", cli_ui.heading("Examples:")]
    for example in info.examples:
        out += cli_ui.wrap(example, w - 2, "  ")
    return "\n".join(out)


def unknown_command(name):
    matches = difflib.get_close_matches(name, COMMAND_INFO, n=3, cutoff=0.6)
    lines = [f"unknown command: {name}"]
    if matches:
        lines.append("Did you mean: " + ", ".join(matches) + "?")
    lines.append(f"Run '{PROG} --help' to see all commands.")
    return "\n".join(lines)
