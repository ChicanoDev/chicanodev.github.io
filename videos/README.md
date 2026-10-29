# ChicanoDev videos

Terminal videos made with [VHS](https://github.com/charmbracelet/vhs), rendered in Docker so every demo runs on a real Linux filesystem. Each episode is 60–90 seconds and ships in two shapes: vertical 1080x1920 (Shorts/Reels) and 16:9 1920x1080 (YouTube). Captions are burned in, with `.srt` sidecars.

## Series

| Series | Episodes | Topic |
| --- | --- | --- |
| `linux-fs` | 4 | Linux directory structure |
| `linux-cmds` | 9 | Basic Linux commands |
| `where-code-runs` | 3 | Bare metal, VMs, containers, the cloud |
| `git-basics` | 1 | Your first commit |

Each episode lives in `series/<series>/<NN-slug>/`:

- `body.tape`: the commands. `# @beat M:SS Label` markers line up with the voiceover.
- `voiceover.md`: the narration script, one `## [M:SS-M:SS]` section per beat, plus post copy.
- `assets/` (optional): ASCII diagrams the tape `cat`s.
- `narration/`, `transcript/`, `alignment.yaml`: your recordings, editable word fixes and take choices (see the workflow guide).

## Layout

| Path | Purpose |
| --- | --- |
| `series/` | the episodes |
| `templates/episode/` | start a new episode here (copy, edit, register in `EPISODES`) |
| `ideas/` | parked drafts that are not episodes yet |
| `common/` | VHS look per orientation |
| `assets/branding/` | the 5 s ChicanoDev animation used for the outro/intro |
| `tools/`, `tests/` | `vidkit.py` and its modules; the test suite |
| `docker/` | the `chicanodev-vhs` render image (VHS, Plex Mono, git) |
| `docs/` | the production guide and the pre-pipeline baseline |
| `audio/` | legacy single full-episode recordings for `mux` (gitignored) |
| `out/`, `build/` | generated, gitignored |

## Workflow

```sh
docker build -t chicanodev-vhs docker      # once: VHS + Plex Mono + man pages
python3 tools/vidkit.py lint               # timing, word count, beat alignment
python3 tools/vidkit.py render             # both orientations -> build/
python3 tools/vidkit.py burn               # captions -> out/vertical, out/horizontal
python3 tools/vidkit.py verify             # resolution and length of every clip
python3 tools/vidkit.py compile            # one long video per series -> out/youtube
```

Every command takes optional episode names (`linux-fs`, `01-no-c-drive`, or `linux-fs/01-no-c-drive`).

**Render one at a time.** VHS records in real time. Several renders in parallel drop frames and produce clips up to 10% short. A serial render lands about 2–3% short, and `burn` stretches the captions to each clip's real length.

## Voiceover

**Preferred: narration-first.** Record 2–3 sentences per section, build, review, approve. The video is timed to your voice and the captions come from what you actually said. See [docs/video-production-workflow.md](docs/video-production-workflow.md).

```sh
python3 tools/vidkit.py segments linux-fs/01-no-c-drive      # what to record, and the filenames
python3 tools/vidkit.py build linux-fs/01-no-c-drive         # transcribe, sync, caption, brand
python3 tools/vidkit.py approve linux-fs/01-no-c-drive       # after watching it on your phone
```

**Legacy:** record one take against the finished silent video and run `mux`. The `.srt` files then come from the script, so re-time them if your read differs much. Both flows keep working.

## Setup for the narration pipeline

Python 3.12 (3.13+ has no wheels for faster-whisper's dependencies):

```sh
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python tools/vidkit.py segments linux-fs/01-no-c-drive
```

The first `transcribe` downloads the `small.en` whisper model (about 500 MB, once). Everything runs locally.

## Tests

```sh
.venv/bin/python -m pytest tests
```

The integration tests (`test_pipeline_integration.py`, `test_cli_build.py`) run the whole pipeline on synthetic media and take a few minutes. They need `ffmpeg`/`ffprobe` on the host but not Docker or the whisper model.

Unit tests cover `tools/vidkit.py`. `tests/test_episodes.py` checks every episode against the linter and the setup rules, for example that a tape moves out of the mounted repo directory before it creates files.
