# Linux directory structure #3: where things change
# Safe: runs in the chicanodev-vhs docker image as the demo user; nothing on the host is touched.

# ---- hidden setup ----
Hide
Type "export PS1='$ '"
Enter
Type "cd / && alias ls='ls --hide=vhs'"
Enter
Type "clear"
Enter
Show

# @beat 0:00 Hook
Type "# What changes while it runs?"
Enter
Sleep 1s
Type "# Let's see."
Enter
Sleep 1.13s

# @beat 0:05 Var
Type "clear"
Enter
Sleep 0.3s
Type "ls /var"
Enter
Sleep 3s
Type "ls /var/log | head -4"
Enter
Sleep 3.5s
Type "# logs live in /var/log"
Enter
Sleep 3.28s

# @beat 0:19 Var state
Type "clear"
Enter
Sleep 0.3s
Type "ls /var/lib | head -4"
Enter
Sleep 3.5s
Type "ls /var/cache"
Enter
Sleep 3s
Type "# state vs cache"
Enter
Sleep 2.35s

# @beat 0:32 Tmp
Type "clear"
Enter
Sleep 0.3s
Type "echo hi > /tmp/note"
Enter
Sleep 2.5s
Type "cat /tmp/note"
Enter
Sleep 2.5s
Type "# gone after reboot"
Enter
Sleep 2.78s

# @beat 0:44 Boot
Type "clear"
Enter
Sleep 0.3s
Type "uname -r"
Enter
Sleep 4s
Type "# kernel files live in /boot"
Enter
Sleep 5.83s

# @beat 0:57 CTA
Type "clear"
Enter
Sleep 0.3s
Type "# next: /dev /proc /sys"
Enter
Sleep 1s
Type "# chicanodev.com"
Enter
Sleep 8.62s
