# Making a ChicanoDev video (narration-first)

You write the script, record a few sentences at a time, and one command builds a captioned, branded Short and horizontal episode **timed to your voice**. You never read against the video and never move a subtitle.

All commands run from `videos/`, written as `python3 tools/vidkit.py ...`. Do the one-time [setup](../README.md#setup-for-the-narration-pipeline) first; after that the tool switches to the project's `.venv` by itself, so plain `python3` works. If the setup is missing it tells you the exact command to run.

```text
script  ->  record (vidkit record)  ->  check-audio  ->  build  ->  review on phone  ->  approve  ->  upload by hand  ->  publish (record it)  ->  status / backlog
```

## 1. Script

Each episode already has `series/<series>/<episode>/voiceover.md` (script, `## [0:00-0:05] Title` per section, and a `## Post copy` block) and `body.tape` (the terminal, with one `# @beat` per section). **Each timed heading is one segment.** The `[0:05-0:17]` times are only a rough guide now; your recording decides the real timing.

Starting a new episode? Copy `templates/episode/` to `series/<series>/<NN-slug>/`, fill in both files, add the episode to `EPISODES` in `tools/vidkit.py`, and run `python3 tools/vidkit.py lint <series>/<NN-slug>`. The template lists the rules the linter enforces.

## 2. See what to record

```sh
python3 tools/vidkit.py segments linux-fs/01-no-c-drive
```

Prints each section's text and the exact filename to save it as, with `[todo]` / `[recorded]`:

```text
 2. [todo] 02-root  ->  narration/02-root.m4a
      That slash is called root, the very top of the file tree...
```

The segment name comes from the heading (`Root home` becomes `02-root-home`). Don't rename a heading after recording or the file stops matching.

## 3. Record

```sh
python3 tools/vidkit.py record linux-fs/02-where-programs-live
```

The studio shows each segment's script, records from your microphone, plays the take back, and files it for you. Nothing to name, export or move. The normal path per segment is three Enters:

```text
Enter  start recording  ->  read the script  ->  Enter  stop  ->  (take plays)  ->  Enter  approve
```

| At the prompt | Keys |
|---|---|
| script | `Enter` record, `s` skip for now, `q` save and quit |
| after a take | `Enter` approve, `p` play again, `r` record again, `b`/`n` earlier/later take, `q` save and quit |
| start screen | `Enter` continue where you left off, `l` pick any segment, `q` quit |
| script panel | `Up`/`Down`/`PgUp`/`PgDn` scroll a script too long for the window |

The current segment's script stays pinned at the top of the screen while you record, review, play back, retry, switch takes and resume, so you never need to scroll or open `voiceover.md`. It uses the terminal's alternate screen (like `vim`), so nothing lands in scrollback, and it redraws when you resize the window or tmux pane. On a pipe or `TERM=dumb` it falls back to plain line-by-line output that prints the script with every screen.

- **Quit any time.** Run the same command tomorrow and it resumes at the first segment that is not approved. A take you recorded but did not approve is offered first, so a good recording is never lost.
- **Approved** means `narration/<segment>.wav` exists (48 kHz, mono, 16-bit). That is the file `check-audio`, `transcribe` and `build` read, so there is no extra step.
- **Retakes are safe.** Every recording is kept in `narration/takes/<segment>.takeN.wav`. Replacing an approved take archives the old audio there first (`<segment>.prevN.<ext>`), and a failure partway never touches the take you had.
- **Recording one segment:** `record <episode> --segment 04-local` (`04` or `local` also work). Choosing an approved segment asks before recording over it.
- `record <episode> --status` lists approved / waiting / missing segments without touching the microphone. `record --list-devices` shows microphones; pick one with `--device <id or name>`. `--no-autoplay` turns off playback after each take.
- Narration approval here is separate from `approve` (the finished video, step 7). Approving a take never builds or approves a video.
- Check the microphone name on the start screen. A Bluetooth headset runs at 8-16 kHz and sounds thin, so the studio warns; choose the real mic with `--device`.
- macOS asks for microphone permission for your terminal app the first time. If the take comes out silent, allow it under System Settings > Privacy & Security > Microphone and record again.
- A recording is trimmed, loudness-normalised and checked later; your take files are never modified.

When every segment is approved the studio runs the audio checks and prints the next two commands.

### Recording in another app

Still works: QuickTime (File > New Audio Recording) or iPhone Voice Memos, one section at a time, saved into:

```text
series/linux-fs/01-no-c-drive/narration/01-hook.m4a
                                        02-root.m4a   (.wav and .mp3 also work)
```

- Leave a beat of quiet at the start and end. Dead air is trimmed for you.
- Slip? Say the sentence again and keep going, or re-record the section; it is only 2-3 sentences.
- Files you save by hand count as approved. `record` shows them as Approved and archives them (never deletes) if you replace them.

### Replace one take (manual files)

Re-record `04-root-home` and save it over `narration/04-root-home.m4a`. Only that segment is reprocessed on the next build.

If you save a second file as `04-root-home.take2.m4a`, the tools stop and ask you to choose. They never guess the newest. Pick one in `series/.../alignment.yaml`:

```yaml
selected:
  04-root-home: 04-root-home.take2.m4a
```

`record` will not overwrite a segment pinned this way; remove the `selected:` entry first.

### Manual acceptance test (macOS, real microphone)

Use an episode with no narration yet, or back up first: `cp -R series/linux-fs/02-where-programs-live/narration ~/narration-02.bak`. (Replacing a take archives the old audio and never deletes it, but a backup costs nothing.) Then:

1. `record --list-devices` shows your microphone. `record <episode> --status` shows the segments.
2. `record <episode> --device <your mic>`: the start screen names it; a Bluetooth headset triggers the warning.
3. Enter, speak, Enter: the take plays back through the speakers/headphones, then Enter approves. `narration/<segment>.wav` appears.
4. On another segment press `r` after a take: a second take is recorded, `b` replays the first, and Enter approves the one you chose.
5. Press `q` mid-episode, run the command again: it resumes at the first unapproved segment, and an unapproved take is offered first.
6. Unplug the microphone while recording (or deny permission): you get a plain message, no traceback, and earlier approved takes are untouched.
7. Finish the episode, then `check-audio <episode>` passes and `build <episode> --dry-run` lists every segment.

## 4. Check the recordings

```sh
python3 tools/vidkit.py check-audio linux-fs/01-no-c-drive
```

Flags missing, empty, unreadable, clipped, too-quiet, mostly-silent or too-long takes and says how to fix each.

## 5. Build

```sh
python3 tools/vidkit.py build linux-fs/01-no-c-drive --format vertical    # the Short/Reel
python3 tools/vidkit.py build linux-fs/01-no-c-drive --format both        # plus 16:9
python3 tools/vidkit.py build linux-fs/01-no-c-drive --dry-run            # what would run, nothing written
```

One command does all of this, and skips whatever has not changed:

1. Trims and levels each take (48 kHz mono working copy) and stitches them with a 0.3 s pause.
2. Transcribes each take locally (faster-whisper `small.en`, CPU) into **word-timed, editable** `transcript/<segment>.yaml`.
3. Makes a retimed **copy** of `body.tape` so each section's visuals last as long as your voice. Typing speed is never touched; only the pauses after commands stretch or shrink. The original tape is never edited.
4. Renders it with VHS, then **measures** when each section's screen really starts (VHS runs a little short of its own arithmetic) and re-renders with a correction if it is off by more than 0.3 s. Still off after two corrections? It stops and writes `out/intermediate/<episode>/sync-report.md`. It never ships out-of-sync video.
5. Adds your voice, burns captions from **what you said**, and adds the ChicanoDev animation.
6. Checks the result (size, 30 fps, h264/yuv420p, AAC audio, not silent, expected length, brand clip not doubled).

Outputs:

```text
out/final/vertical/<id>.mp4   .srt   .vtt
out/final/horizontal/<id>.mp4 .srt   .vtt
out/final/<id>.meta.md        title, caption, hashtags, transcript
out/final/<id>.status.json    built / approved
```

### Branding

`--brand-placement outro|after-hook|none|both`

| format | default |
|---|---|
| vertical | `outro`: 5 s after the lesson. The first frame is your hook. |
| horizontal | `after-hook`: after the opening line, before the lesson |

The 16:9 animation is shown whole on a dark 1080×1920 canvas for vertical (never cropped or stretched). It lives at `assets/branding/chicanodev-intro.mp4`. Narration and captions always end before an outro starts.

### If the build stops

| message | do this |
|---|---|
| `missing narration: 03-home.m4a` | record it, save it as that name |
| `N takes (...). Pick one under selected:` | choose in `alignment.yaml` or move the extras out |
| `beat 2 'Root': narration needs 3.1s but the visuals run 7.6s and cannot go below 4.1s` | say more in that section, or shorten the commands in a copy of the tape |
| `video and narration are out of sync ... see sync-report.md` | open the report; re-record the flagged section or re-run (VHS can run slowly) |

## 6. Fix wrong words (no re-recording)

```sh
python3 tools/vidkit.py transcript linux-fs/01-no-c-drive
```

Lists words to double-check: low confidence, or different from the script (`heard 'et cetera', script has 'etc'`). The script is a spelling reference only; what you said is never silently replaced.

To fix one, edit its `text` in `transcript/<segment>.yaml`:

```yaml
- {text: et, start: 0.5, end: 0.62, conf: 0.41, asr: et}   # change text: etc
```

Then `build` again. Corrections stay until you **replace that recording**; then the old file is kept as `<segment>.stale.yaml` and a fresh transcript is made.

## 7. Review, then approve

A build is **never** automatically approved.

```sh
python3 tools/vidkit.py review linux-fs/01-no-c-drive --open     # lists files, opens them
```

Watch it on your phone, with sound. The command prints the checklist (voice clear, captions right, commands appear when spoken, readable at phone size, narration ends before the outro). Then:

```sh
python3 tools/vidkit.py approve linux-fs/01-no-c-drive
python3 tools/vidkit.py backlog                  # approved exports still to upload, per platform
```

Approval is voided if the content changes (new take, edited transcript, new tape) or if the exported file is replaced. Rebuild, review, approve again. `approve` refuses if the checks failed.

## 8. Many episodes

```sh
python3 tools/vidkit.py batch-build linux-fs --format vertical
```

Builds every fully recorded episode, **skips** the unrecorded ones (and says which segments are missing), and **leaves approved ones alone** unless you add `--force`.

## 9. Publish (by hand)

Upload from `backlog` using YouTube Studio / Meta. Titles, captions and hashtags are in `out/final/<id>.meta.md`, taken from the `## Post copy` block. Upload the `.srt` as the caption track if you want YouTube to use it.

## 10. Record the upload, track progress

```
build  ->  review  ->  approve  ->  upload manually  ->  publish  ->  status / backlog
```

`publish` **records** an upload you already did. It never uploads, schedules or calls any platform API.

```sh
python3 tools/vidkit.py publish linux-fs/02-where-programs-live --platform youtube --url 'https://www.youtube.com/shorts/ID'
python3 tools/vidkit.py publish linux-fs/02-where-programs-live --platform instagram          # URL is optional
python3 tools/vidkit.py publish linux-fs/02-where-programs-live --platform youtube --format horizontal \
  --at '2026-11-04T14:00:00-06:00' --by 'Dave Vigil'
python3 tools/vidkit.py backlog --platform youtube      # what still needs uploading
python3 tools/vidkit.py status linux-fs                 # history and series progress
```

- **One episode, one destination per call.** `--platform` is required. `--format` defaults to `vertical`, and `both` is refused. Series names are refused, so nothing is bulk-marked.
- **Destinations are separate.** A YouTube record removes that format from YouTube's backlog only. Instagram stays pending until you record it.
- **Records are tied to the exact file bytes** (SHA-256) and are append-only. Re-running `publish` for the same file is a no-op and keeps the original time, URL and name. If you pass a different `--url`, `--at` or `--by` for an existing record, it is refused and nothing changes. Adding a URL later counts as an edit too, and this release does not edit records.
- **`--at`** needs a timezone (`Z` or `-06:00`). It is stored in UTC and must not be in the future. If you leave it out, it defaults to now.
- **Rebuilds keep history.** A changed export voids approval as before. The old publication stays in `status`, labelled "changed since publish". After you approve the new export, it shows up in `backlog` again as a new revision. If only the horizontal file changes, the already-published vertical file is not re-queued. If the bytes are identical but the content key is new, the export still counts as published.
- **`status`** shows, per series, `Ever published X/N` (any upload, ever) and `Current exports published Y/N` (the current local file matches an upload). N counts every registered episode, including ones not built yet. These labels compare local files only and do not check whether a post is still live.
- **Compiled long videos are not tracked yet.** Publishing every episode does not mark the compilation published.
- History lives in `out/final/<id>.status.json`, which is written atomically. If that file is corrupt, vidkit names it and stops. It never overwrites it.

## Files you edit vs. files that are generated

| you edit / record | generated, safe to delete |
|---|---|
| `voiceover.md`, `body.tape` | `out/intermediate/**` (audio, tapes, renders) |
| `narration/*.m4a` | `out/final/**` (rebuild any time) |
| `transcript/*.yaml` (word fixes) | |
| `alignment.yaml` (`selected`, optional `ids`) | |

`transcript/` and `narration/` belong with the episode; `out/` is gitignored.

## Still works as before

`lint`, `render`, `burn`, `verify`, `compile`, `script`, `pace`, `mux`, `chapters` and the single-recording flow are unchanged.
