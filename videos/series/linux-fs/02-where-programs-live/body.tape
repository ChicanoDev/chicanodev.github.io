# Linux directory structure #2: where programs live
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
Type "# Where do programs live?"
Enter
Sleep 0.9s
Type "# Four places. Let's look."
Enter
Sleep 0.53s

# @beat 0:05 Bin
Type "clear"
Enter
Sleep 0.3s
Type "which ls"
Enter
Sleep 3s
Type "readlink /bin"
Enter
Sleep 2.5s
Type "readlink /sbin"
Enter
Sleep 2.5s
Type "# just links into /usr"
Enter
Sleep 3.36s

# @beat 0:21 Usr
Type "clear"
Enter
Sleep 0.3s
Type "ls /usr"
Enter
Sleep 3.5s
Type "ls /usr/bin | wc -l"
Enter
Sleep 3.5s
Type "# most software lives here"
Enter
Sleep 2.71s

# @beat 0:35 Local
Type "clear"
Enter
Sleep 0.3s
Type "ls /usr/local"
Enter
Sleep 3.5s
Type "ls /usr/local/bin"
Enter
Sleep 2.5s
Type "# your own installs"
Enter
Sleep 1.92s

# @beat 0:47 Opt
Type "clear"
Enter
Sleep 0.3s
Type "ls /opt"
Enter
Sleep 3s
Type "# one folder per app"
Enter
Sleep 5.46s

# @beat 0:58 Lib
Type "clear"
Enter
Sleep 0.3s
Type "readlink /lib"
Enter
Sleep 2.5s
Type "# shared code, linked to /usr"
Enter
Sleep 0.91s

# @beat 1:05 CTA
Type "clear"
Enter
Sleep 0.3s
Type "# next: /var /tmp /boot"
Enter
Sleep 1s
Type "# chicanodev.com"
Enter
Sleep 2.62s
