# Git basics #1: your first commit. init, ls -a, status, add, commit, log
# Safe: runs in the chicanodev-vhs docker image as the demo user; nothing on the host is touched.

# ---- hidden setup ----
Hide
Type "export PS1='$ '"
Enter
Type "cd ~"
Enter
Type "git config --global user.name 'ChicanoDev Demo'"
Enter
Type "git config --global user.email 'demo@example.invalid'"
Enter
Type "git config --global init.defaultBranch main"
Enter
Type "git config --global log.decorate no"
Enter
Type "clear"
Enter
Show

# @beat 0:00 Hook
Type "# Git saves snapshots."
Enter
Sleep 1s
Type "# Let's make one."
Enter
Sleep 1270ms

# @beat 0:05 Init
Type "clear"
Enter
Sleep 300ms
Type "mkdir demo && cd demo"
Enter
Sleep 1s
Type "git init"
Enter
Sleep 2s
Type "ls -a"
Enter
Sleep 5970ms

# @beat 0:17 Status
Type "clear"
Enter
Sleep 300ms
Type "echo '# My app' > README.md"
Enter
Sleep 1s
Type "git status -s"
Enter
Sleep 2s
Type "# ?? means untracked"
Enter
Sleep 6150ms

# @beat 0:31 Add
Type "clear"
Enter
Sleep 300ms
Type "git add README.md"
Enter
Sleep 1s
Type "git status -s"
Enter
Sleep 2s
Type "# A means staged"
Enter
Sleep 6130ms

# @beat 0:44 Commit
Type "clear"
Enter
Sleep 300ms
Type "git commit -m 'Add README'"
Enter
Sleep 2.5s
Type "git status -s"
Enter
Sleep 2s
Type "# clean: nothing left"
Enter
Sleep 4650ms

# @beat 0:58 Log
Type "clear"
Enter
Sleep 300ms
Type "git log --oneline"
Enter
Sleep 3s
Type "# one commit, one snapshot"
Enter
Sleep 4340ms

# @beat 1:09 CTA
Type "clear"
Enter
Sleep 300ms
Type "# next: branches"
Enter
Sleep 1s
Type "# chicanodev.com"
Sleep 3110ms
