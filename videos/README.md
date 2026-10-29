# ChicanoDev videos

Terminal videos made with [VHS](https://github.com/charmbracelet/vhs), rendered in Docker so every demo runs on a real Linux filesystem. Each episode is 60–90 seconds and ships in two shapes: vertical 1080x1920 (Shorts/Reels) and 16:9 1920x1080 (YouTube). Captions are burned in, with `.srt` sidecars.

## Series

| Series | Episodes | Topic |
| --- | --- | --- |
| `linux-fs` | 4 | Linux directory structure |
| `linux-cmds` | 9 | Basic Linux commands |
| `where-code-runs` | 3 | Bare metal, VMs, containers, the cloud |

Each episode lives in `series/<series>/<NN-slug>/`:

- `body.tape`: the commands. `# @beat M:SS Label` markers line up with the voiceover.
- `voiceover.md`: the narration script, one `## [M:SS-M:SS]` section per beat, plus post copy.
- `assets/` (optional): ASCII diagrams the tape `cat`s.

`tapes/`, `shorts/` and `scripts/render-all.sh` are the older one-off tapes and are not part of this pipeline.

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

Record against the finished video and use `voiceover.md` as the script. The `.srt` files come from that script, so re-time them if your read differs much.

## Tests

```sh
uv run --with pytest pytest tests
```

Unit tests cover `tools/vidkit.py`. `tests/test_episodes.py` checks every episode against the linter and the setup rules, for example that a tape moves out of the mounted repo directory before it creates files.
