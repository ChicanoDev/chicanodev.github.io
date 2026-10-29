# Basic Linux commands #6: users and permissions
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
Type "# Permission denied?"
Enter
Sleep 1s
Type "# Here's how it works."
Enter
Sleep 1.06s

# @beat 0:05 Whoami
Type "clear"
Enter
Sleep 0.3s
Type "whoami"
Enter
Sleep 2s
Type "sudo whoami"
Enter
Sleep 3s
Sleep 4.16s

# @beat 0:16 Permissions
Type "clear"
Enter
Sleep 0.3s
Type "touch run.sh"
Enter
Sleep 1s
Type "stat -c '%A %U' run.sh"
Enter
Sleep 4s
Sleep 5.97s

# @beat 0:30 Chmod
Type "clear"
Enter
Sleep 0.3s
Type "chmod +x run.sh"
Enter
Sleep 1.5s
Type "stat -c '%A %U' run.sh"
Enter
Sleep 4s
Sleep 3.26s

# @beat 0:42 Useradd
Type "clear"
Enter
Sleep 0.3s
Type "sudo useradd ana"
Enter
Sleep 2s
Type "id ana"
Enter
Sleep 3.5s
Sleep 4.31s

# @beat 0:54 Chown
Type "clear"
Enter
Sleep 0.3s
Type "sudo chown ana run.sh"
Enter
Sleep 2s
Type "stat -c '%A %U' run.sh"
Enter
Sleep 3.5s
Sleep 2.84s

# @beat 1:06 Su
Type "clear"
Enter
Sleep 0.3s
Type "sudo -u ana whoami"
Enter
Sleep 3.5s
Sleep 0.59s

# @beat 1:12 CTA
Type "clear"
Enter
Sleep 0.3s
Type "# next: system health"
Enter
Sleep 1s
Type "# chicanodev.com"
Enter
Sleep 1.76s
