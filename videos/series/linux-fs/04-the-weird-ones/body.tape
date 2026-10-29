# Linux directory structure #4: the weird folders
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
Type "# Folders that aren't on disk"
Enter
Sleep 1s
Type "# Meet the weird ones"
Enter
Sleep 0.50s

# @beat 0:05 Dev
Type "clear"
Enter
Sleep 0.3s
Type "ls /dev | head -6"
Enter
Sleep 3.5s
Type "echo hi > /dev/null"
Enter
Sleep 2s
Type "# devices are files"
Enter
Sleep 4.00s

# @beat 0:19 Proc
Type "clear"
Enter
Sleep 0.3s
Type "cat /proc/uptime"
Enter
Sleep 3s
Type "head -1 /proc/meminfo"
Enter
Sleep 3.5s
Type "# live kernel info"
Enter
Sleep 3.00s

# @beat 0:33 Sys
Type "clear"
Enter
Sleep 0.3s
Type "ls /sys"
Enter
Sleep 3.5s
Type "# the hardware tree"
Enter
Sleep 5.03s

# @beat 0:44 Run
Type "clear"
Enter
Sleep 0.3s
Type "ls /run"
Enter
Sleep 3s
Type "# fresh each boot"
Enter
Sleep 3.67s

# @beat 0:53 Mounts
Type "clear"
Enter
Sleep 0.3s
Type "ls /mnt /media /srv"
Enter
Sleep 3.5s
Type "# mount points + served data"
Enter
Sleep 4.56s

# @beat 1:05 CTA
Type "clear"
Enter
Sleep 0.3s
Type "# next: basic commands"
Enter
Sleep 1s
Type "# chicanodev.com"
Enter
Sleep 2.69s
