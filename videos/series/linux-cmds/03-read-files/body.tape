# Basic Linux commands #3: read files
# Safe: runs in the chicanodev-vhs docker image as the demo user; nothing on the host is touched.

# ---- hidden setup ----
Hide
Type "export PS1='$ '"
Enter
Type "seq 1 200 | sed 's/^/line /' > log.txt"
Enter
Type `printf 'a\nb\n' > one`
Enter
Type `printf 'a\nc\n' > two`
Enter
Type "(while true; do date +%T >> app.log; sleep 1; done) >/dev/null 2>&1 &"
Enter
Type "clear"
Enter
Show

# @beat 0:00 Hook
Type "# 200 lines. Read 3."
Enter
Sleep 1s
Type "# Here's how."
Enter
Sleep 1.69s

# @beat 0:05 Head
Type "clear"
Enter
Sleep 0.3s
Type "head -3 log.txt"
Enter
Sleep 3.5s
Sleep 4.80s

# @beat 0:15 Tail
Type "clear"
Enter
Sleep 0.3s
Type "tail -3 log.txt"
Enter
Sleep 3.5s
Sleep 6.80s

# @beat 0:27 Follow
Type "clear"
Enter
Sleep 0.3s
Type "tail -f app.log"
Enter
Sleep 7s
Ctrl+C
Sleep 1.5s
Sleep 5.80s

# @beat 0:43 Diff
Type "clear"
Enter
Sleep 0.3s
Type "diff one two"
Enter
Sleep 4s
Type "# < first file  > second"
Enter
Sleep 6.83s

# @beat 0:57 Less
Type "clear"
Enter
Sleep 0.3s
Type "# big file? use less"
Enter
Sleep 1.5s
Type "# see my less short"
Enter
Sleep 2.12s

# @beat 1:04 CTA
Type "clear"
Enter
Sleep 0.3s
Type "# next: find locate grep"
Enter
Sleep 1s
Type "# chicanodev.com"
Enter
Sleep 1.55s
