# Where does code run? #2: containers
# Safe: runs in the chicanodev-vhs docker image as the demo user; nothing on the host is touched.

# ---- hidden setup ----
Hide
Type "export PS1='$ '"
Enter
Type "cd /vhs/series/where-code-runs/02-containers/assets"
Enter
Type "clear"
Enter
Show

# @beat 0:00 Hook
Type "# A container is not a mini VM"
Enter
Sleep 1s
Type "# Proof: we're inside one"
Enter
Sleep 1.15s

# @beat 0:06 Diagram
Type "clear"
Enter
Sleep 0.3s
Type "cat container.txt"
Enter
Sleep 9s
Sleep 7.16s

# @beat 0:24 Kernel
Type "clear"
Enter
Sleep 0.3s
Type "uname -r"
Enter
Sleep 3.5s
Type "ls -a /.dockerenv"
Enter
Sleep 3.5s
Sleep 6.60s

# @beat 0:40 Processes
Type "clear"
Enter
Sleep 0.3s
Type "ps -e | wc -l"
Enter
Sleep 4s
Sleep 4.44s

# @beat 0:50 Userland
Type "clear"
Enter
Sleep 0.3s
Type "cat /etc/os-release | head -1"
Enter
Sleep 5s
Sleep 5.32s

# @beat 1:03 Tradeoff
Type "clear"
Enter
Sleep 0.3s
Type "# light + fast"
Enter
Sleep 1.5s
Type "# shared kernel = weaker walls"
Enter
Sleep 0.77s

# @beat 1:09 CTA
Type "clear"
Enter
Sleep 0.3s
Type "# next: the cloud"
Enter
Sleep 1s
Type "# chicanodev.com"
Enter
Sleep 3.04s
