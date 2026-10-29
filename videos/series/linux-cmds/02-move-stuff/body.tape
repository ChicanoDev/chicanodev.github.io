# Basic Linux commands #2: move stuff around
# Safe: runs in the chicanodev-vhs docker image as the demo user; nothing on the host is touched.

# ---- hidden setup ----
Hide
Type "export PS1='$ '"
Enter
Type "cd ~ && mkdir -p play && cd play"
Enter
Type "clear"
Enter
Show

# @beat 0:00 Hook
Type "# cp  mv  rm  cat"
Enter
Sleep 1s
Type "# and one big warning"
Enter
Sleep 1.34s

# @beat 0:05 Cat
Type "clear"
Enter
Sleep 0.3s
Type "echo hello > a.txt"
Enter
Sleep 2s
Type "cat a.txt"
Enter
Sleep 3s
Sleep 2.46s

# @beat 0:15 Cp
Type "clear"
Enter
Sleep 0.3s
Type "cp a.txt b.txt"
Enter
Sleep 1.5s
Type "ls"
Enter
Sleep 3.5s
Sleep 4.23s

# @beat 0:26 Mv
Type "clear"
Enter
Sleep 0.3s
Type "mv b.txt c.txt"
Enter
Sleep 1.5s
Type "ls"
Enter
Sleep 2s
Type "mkdir box"
Enter
Sleep 1s
Type "mv c.txt box/"
Enter
Sleep 1.5s
Type "ls box"
Enter
Sleep 2.5s
Sleep 3.77s

# @beat 0:42 Rm
Type "clear"
Enter
Sleep 0.3s
Type "rm a.txt"
Enter
Sleep 1.5s
Type "ls"
Enter
Sleep 2s
Type "# no trash can!"
Enter
Sleep 5.10s

# @beat 0:53 Rm -r
Type "clear"
Enter
Sleep 0.3s
Type "rm -r box"
Enter
Sleep 1.5s
Type "ls"
Enter
Sleep 2s
Sleep 5.08s

# @beat 1:03 CTA
Type "clear"
Enter
Sleep 0.3s
Type "# next: head tail diff"
Enter
Sleep 1s
Type "# chicanodev.com"
Enter
Sleep 2.69s
