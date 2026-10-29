# Basic Linux commands #8: network and archives
# Safe: runs in the chicanodev-vhs docker image as the demo user; nothing on the host is touched.

# ---- hidden setup ----
Hide
Type "export PS1='$ '"
Enter
Type "mkdir stuff && touch stuff/a stuff/b"
Enter
Type "clear"
Enter
Show

# @beat 0:00 Hook
Type "# reach it. download it."
Enter
Sleep 1s
Type "# bundle it."
Enter
Sleep 1.48s

# @beat 0:05 Ping
Type "clear"
Enter
Sleep 0.3s
Type "ping -c 2 1.1.1.1"
Enter
Sleep 4.5s
Sleep 6.66s

# @beat 0:18 Curl
Type "clear"
Enter
Sleep 0.3s
Type "curl -sI example.com | head -1"
Enter
Sleep 4s
Sleep 5.25s

# @beat 0:30 Wget
Type "clear"
Enter
Sleep 0.3s
Type "wget -q example.com"
Enter
Sleep 2.5s
Type "ls"
Enter
Sleep 3s
Sleep 5.38s

# @beat 0:43 Tar
Type "clear"
Enter
Sleep 0.3s
Type "tar -czf s.tgz stuff"
Enter
Sleep 2.5s
Type "tar -tzf s.tgz"
Enter
Sleep 4s
Sleep 4.47s

# @beat 0:57 Zip
Type "clear"
Enter
Sleep 0.3s
Type "zip -rq s.zip stuff"
Enter
Sleep 2.5s
Type "unzip -l s.zip"
Enter
Sleep 4.5s
Sleep 4.04s

# @beat 1:11 CTA
Type "clear"
Enter
Sleep 0.3s
Type "# next: help yourself"
Enter
Sleep 1s
Type "# chicanodev.com"
Enter
Sleep 4.76s
