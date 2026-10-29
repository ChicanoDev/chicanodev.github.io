# <Series> #<N>: <title>. <the commands this episode shows>
# Safe: runs in the chicanodev-vhs docker image as the demo user; nothing on the host is touched.
#
# New episode: copy templates/episode/ to series/<series>/<NN-slug>/, edit both files, then add
# ("<series>", "<NN-slug>") to EPISODES in tools/vidkit.py and run: python3 tools/vidkit.py lint <series>/<NN-slug>
#
# Rules the linter and tests enforce:
#   - Total visible time 60-90s; the voiceover has 140-230 words.
#   - One "# @beat M:SS Title" per voiceover section, same order, within 1s of its heading time.
#   - Typed lines are at most 32 characters (they must be readable on a phone).
#   - Setup stays inside Hide/Show and its first real command is `cd ~` (Docker starts in the mounted repo).
#   - Every beat after the first starts with `clear`.
# No Output or Set lines here: common/<orientation>.settings.tape supplies the look and the output path.
# Exact pause lengths do not matter. With narration, `vidkit.py build` retimes a copy of this tape to your voice.

# ---- hidden setup ----
Hide
Type "export PS1='$ '"
Enter
Type "cd ~"
Enter
Type "clear"
Enter
Show

# @beat 0:00 Hook
Type "# one-line hook"
Enter
Sleep 1s
Type "# second line"
Enter
Sleep 1.7s

# @beat 0:05 Example
Type "clear"
Enter
Sleep 300ms
Type "echo hello"
Enter
Sleep 3s
Type "# what just happened"
Enter
Sleep 5s

# @beat 0:17 CTA
Type "clear"
Enter
Sleep 300ms
Type "# next: the next episode"
Enter
Sleep 1s
Type "# chicanodev.com"
Sleep 3s
