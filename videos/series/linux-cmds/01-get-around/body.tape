# Basic Linux commands #1: get around
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
Type "# 6 commands to get around"
Enter
Sleep 1s
Type "# Let's go."
Enter
Sleep 1.41s

# @beat 0:05 Pwd
Type "clear"
Enter
Sleep 0.3s
Type "pwd"
Enter
Sleep 3.5s
Sleep 3.64s

# @beat 0:13 Ls
Type "clear"
Enter
Sleep 0.3s
Type "ls"
Enter
Sleep 2s
Type "ls -a"
Enter
Sleep 3.5s
Sleep 4.36s

# @beat 0:24 Mkdir and cd
Type "clear"
Enter
Sleep 0.3s
Type "mkdir demo"
Enter
Sleep 1.5s
Type "cd demo"
Enter
Sleep 1.5s
Type "pwd"
Enter
Sleep 2s
Type "cd .."
Enter
Sleep 1.5s
Sleep 5.10s

# @beat 0:38 Touch
Type "clear"
Enter
Sleep 0.3s
Type "touch demo/notes.txt"
Enter
Sleep 1.5s
Type "ls demo"
Enter
Sleep 3s
Sleep 2.96s

# @beat 0:48 Rmdir
Type "clear"
Enter
Sleep 0.3s
Type "rmdir demo"
Enter
Sleep 3.5s
Type "rm demo/notes.txt"
Enter
Sleep 1.5s
Type "rmdir demo"
Enter
Sleep 2s
Sleep 1.76s

# @beat 1:00 CTA
Type "clear"
Enter
Sleep 0.3s
Type "# next: cp mv rm cat"
Enter
Sleep 1s
Type "# chicanodev.com"
Enter
Sleep 3.83s
