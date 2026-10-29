# Linux directory structure #1: no C: drive. /, /home, /root, /etc
# Safe: read-only commands. `sudo ls /root` only lists a directory (demo user in docker).

# ---- hidden setup ----
Hide
Type "export PS1='$ '"
Enter
Type "alias ls='ls --hide=vhs'"
Enter
Type "cd / && clear"
Enter
Show

# @beat 0:00 Hook
Type "# Linux has no C: drive"
Sleep 700ms
Enter
Type "# just one slash: /"
Sleep 1.3s
Enter

# @beat 0:05 Root
Type "clear"
Enter
Sleep 300ms
Type "ls /"
Enter
Sleep 4.5s
Type "# top of the tree"
Enter
Sleep 5.3s

# @beat 0:17 Home
Type "clear"
Enter
Sleep 300ms
Type "ls /home"
Enter
Sleep 3s
Type "cd ~ && pwd"
Enter
Sleep 3s
Type "# your stuff lives here"
Enter
Sleep 2.4s

# @beat 0:29 Root home
Type "clear"
Enter
Sleep 300ms
Type "ls /root"
Enter
Sleep 3s
Type "sudo ls -a /root"
Enter
Sleep 3.5s
Type "# /root = the admin's home"
Enter
Sleep 4.3s

# @beat 0:44 Etc
Type "clear"
Enter
Sleep 300ms
Type "head -3 /etc/os-release"
Enter
Sleep 3.5s
Type "ls /etc | head -5"
Enter
Sleep 3.5s
Type "# config lives in /etc"
Enter
Sleep 2s

# @beat 0:58 CTA
Type "clear"
Enter
Sleep 300ms
Type "# next: where programs live"
Enter
Sleep 1s
Type "# chicanodev.com"
Sleep 3.3s
