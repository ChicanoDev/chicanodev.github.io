# Basic Linux commands #9: help yourself
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
Type "# Nobody memorizes it all."
Enter
Sleep 1s
Type "# Look it up."
Enter
Sleep 1.27s

# @beat 0:05 Man
Type "clear"
Enter
Sleep 0.3s
Type "man ls"
Enter
Sleep 5s
Type "q"
Sleep 1s
Sleep 6.86s

# @beat 0:19 Help
Type "clear"
Enter
Sleep 0.3s
Type "ls --help | head -5"
Enter
Sleep 4s
Sleep 5.02s

# @beat 0:30 History
Type "clear"
Enter
Sleep 0.3s
Type "history | tail -3"
Enter
Sleep 4s
Sleep 7.16s

# @beat 0:43 Alias
Type "clear"
Enter
Sleep 0.3s
Type "alias ll='ls -la'"
Enter
Sleep 2s
Type "ll"
Enter
Sleep 3.5s
Sleep 5.52s

# @beat 0:56 Echo
Type "clear"
Enter
Sleep 0.3s
Type "echo $HOME"
Enter
Sleep 2.5s
Type "echo $SHELL"
Enter
Sleep 2.5s
Sleep 2.88s

# @beat 1:06 CTA
Type "clear"
Enter
Sleep 0.3s
Type "# now go practice"
Enter
Sleep 1s
Type "# chicanodev.com"
Enter
Sleep 4.04s
