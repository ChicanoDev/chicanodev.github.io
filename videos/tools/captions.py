"""Captions from word timings: short 1-2 line cues that follow the actual speech."""
import vidkit

SENTENCE_END = (".", "?", "!")


def cues_from_words(words, max_chars=32, max_lines=2, offset=0.0, pause=0.6):
    cues, lines, group = [], [], []

    def flush():
        nonlocal lines, group
        if group:
            cues.append(vidkit.Cue(group[0].start + offset, group[-1].end + offset,
                                   "\n".join(" ".join(w.text for w in line) for line in lines)))
        lines, group = [], []

    for i, word in enumerate(words):
        fits = lines and len(" ".join(w.text for w in lines[-1])) + 1 + len(word.text) <= max_chars
        if fits:
            lines[-1].append(word)
        elif len(lines) < max_lines:
            lines.append([word])
        else:
            flush()
            lines.append([word])
        group.append(word)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if word.text.endswith(SENTENCE_END) or (nxt and nxt.start - word.end > pause):
            flush()
    flush()
    # a cue must not run into the next one
    return [vidkit.Cue(c.start, min(c.end, n.start), c.text) for c, n in zip(cues, cues[1:])] + cues[-1:]


def format_vtt(cues):
    body = "\n".join(
        f"{vidkit._srt_time(c.start).replace(',', '.')} --> {vidkit._srt_time(c.end).replace(',', '.')}\n{c.text}\n"
        for c in cues)
    return "WEBVTT\n\n" + body
