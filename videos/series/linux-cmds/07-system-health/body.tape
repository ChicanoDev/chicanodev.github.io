# Basic Linux commands #7: system health
# Safe: runs in the chicanodev-vhs docker image as the demo user; nothing on the host is touched.

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
Type "# Is the disk full?"
Enter
Sleep 1s
Type "# What's eating the CPU?"
Enter
Sleep 0.99s

# @beat 0:05 Df
Type "clear"
Enter
Sleep 0.3s
Type "df -h /"
Enter
Sleep 4s
Sleep 5.86s

# @beat 0:16 Du
Type "clear"
Enter
Sleep 0.3s
Type "du -sh /usr/bin"
Enter
Sleep 4s
Sleep 5.30s

# @beat 0:27 Ps
Type "clear"
Enter
Sleep 0.3s
Type "ps -eo pid,comm | head -4"
Enter
Sleep 4.5s
Sleep 5.10s

# @beat 0:39 Top
Type "clear"
Enter
Sleep 0.3s
Type "top -bn1 | head -4"
Enter
Sleep 5s
Sleep 6.09s

# @beat 0:52 Kill
Type "clear"
Enter
Sleep 0.3s
Type "sleep 300 &"
Enter
Sleep 1.5s
Type "pgrep sleep"
Enter
Sleep 2s
Type "kill $(pgrep sleep)"
Enter
Sleep 2s
Type "pgrep sleep || echo gone"
Enter
Sleep 2.5s
Sleep 0.80s

# @beat 1:06 Uname
Type "clear"
Enter
Sleep 0.3s
Type "uname -sr"
Enter
Sleep 2s
Type "hostname"
Enter
Sleep 2s
Sleep 0.16s

# @beat 1:12 CTA
Type "clear"
Enter
Sleep 0.3s
Type "# next: network + archives"
Enter
Sleep 1s
Type "# chicanodev.com"
Enter
Sleep 1.41s
