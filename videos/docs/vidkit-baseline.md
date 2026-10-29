# vidkit baseline (M0)

Captured 2026-10-29 before the narration-first pipeline work. Tests: `106 passed` (`.venv/bin/python -m pytest tests`). `verify`: all 16 episodes OK in both formats.

## Layout in the code (differs from the spec's wording)
- `ROOT` is `videos/`. VHS renders go to `build/<series>-<slug>/<orient>-raw.mp4` (gitignored), not `out/intermediate`. `out/<orient>/` holds burned silent clips; `out/final/<orient>/` holds voiced `mux` output.
- Episode IDs are `<series>-<slug>`, e.g. `linux-fs-01-no-c-drive`. `_select` accepts `series`, `series/slug`, `slug` or the full ID.
- Episodes are a hard-coded `EPISODES` list in `tools/vidkit.py`, not discovered from disk.
- Each episode has `body.tape` and `voiceover.md`. `common/{vertical,horizontal}.settings.tape` are prepended by `build_tape`.
- Beats already exist in both files: `# @beat M:SS Title` in the tape and `## [M:SS-M:SS] Title` in the voiceover. No new markup is needed for segment IDs.
- Every ffmpeg call runs inside the `chicanodev-vhs` Docker image (`_docker`). Host ffmpeg/ffprobe also exist and `_probe` uses host ffprobe.

## Legacy behaviour to preserve
- `mux`: one `audio/<eid>.{m4a,wav,mp3}`; loudnorm to -16 LUFS; holds the last video frame if the voice is longer; captions are script text scaled to the voice length (the pain point).
- `compile [--final]`: 2 s title card per part, concat re-encoded; no branding.
- `pace` flags beats whose words-per-minute is too fast for the fixed window.
- `main` rejects unknown episode names with exit 2.

## Gaps the new pipeline fills
- Captions come from the script, never from the recording.
- Tape timings are fixed; narration must be read to fit.
- No per-segment audio, caching, approval state, or branding.

## Tooling added by this work
- `videos/.venv` (gitignored): pytest, pyyaml, faster-whisper.
