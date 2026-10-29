# Making a ChicanoDev video (narration-first)

You write the script, record a few sentences at a time, and one command builds a captioned, branded Short and horizontal episode **timed to your voice**. You never read against the video and never move a subtitle.

All commands run from `videos/`. Use `.venv/bin/python` (see [Setup](../README.md#setup-for-the-narration-pipeline)); the examples write `python3 tools/vidkit.py` for short.

```text
script  ->  record segments  ->  check-audio  ->  build  ->  review on phone  ->  approve  ->  publish by hand
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

Use QuickTime (File > New Audio Recording) or iPhone Voice Memos. Record **one section at a time**, at your natural pace, then save or AirDrop each into:

```text
series/linux-fs/01-no-c-drive/narration/01-hook.m4a
                                        02-root.m4a   (.wav and .mp3 also work)
```

- Leave a beat of quiet at the start and end. Dead air is trimmed for you.
- Slip? Just say the sentence again and keep going. Re-record the whole section if it is messy; it is only 2–3 sentences.
- You do not need the video, a metronome, or to hit a time.
- Your original files are never changed.

### Replace one take

Re-record `04-root-home` and save it over `narration/04-root-home.m4a`. Only that segment is reprocessed on the next build.

If you want to keep both takes, save the new one as `04-root-home.take2.m4a`. With two files present the tools stop and ask you to choose. They never guess the newest. Pick one in `series/.../alignment.yaml`:

```yaml
selected:
  04-root-home: 04-root-home.take2.m4a
```

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
python3 tools/vidkit.py backlog                  # approved and ready to publish
```

Approval is voided if the content changes (new take, edited transcript, new tape) or if the exported file is replaced. Rebuild, review, approve again. `approve` refuses if the checks failed.

## 8. Many episodes

```sh
python3 tools/vidkit.py batch-build linux-fs --format vertical
```

Builds every fully recorded episode, **skips** the unrecorded ones (and says which segments are missing), and **leaves approved ones alone** unless you add `--force`.

## 9. Publish (by hand)

Upload from `backlog` using YouTube Studio / Meta. Titles, captions and hashtags are in `out/final/<id>.meta.md`, taken from the `## Post copy` block. Upload the `.srt` as the caption track if you want YouTube to use it.

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
