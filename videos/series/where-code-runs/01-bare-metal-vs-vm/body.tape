# Where does code run? #1: bare metal vs virtual machines
# Safe: runs in the chicanodev-vhs docker image as the demo user; nothing on the host is touched.

# ---- hidden setup ----
Hide
Type "export PS1='$ '"
Enter
Type "cd /vhs/series/where-code-runs/01-bare-metal-vs-vm/assets"
Enter
Type "clear"
Enter
Show

# @beat 0:00 Hook
Type "# Where does code run?"
Enter
Sleep 1s
Type "# Bare metal vs VM"
Enter
Sleep 3.20s

# @beat 0:07 Bare metal
Type "clear"
Enter
Sleep 0.3s
Type "cat bare-metal.txt"
Enter
Sleep 9s
Sleep 5.09s

# @beat 0:23 Virtual machine
Type "clear"
Enter
Sleep 0.3s
Type "cat vm.txt"
Enter
Sleep 9s
Sleep 6.65s

# @beat 0:40 Slices
Type "clear"
Enter
Sleep 0.3s
Type "nproc"
Enter
Sleep 3s
Type "free -h | head -2"
Enter
Sleep 5s
Sleep 4.81s

# @beat 0:55 Tradeoff
Type "clear"
Enter
Sleep 0.3s
Type "# VM: isolated, but heavy"
Enter
Sleep 1.5s
Type "# bare metal: fast, but one job"
Enter
Sleep 6.93s

# @beat 1:08 CTA
Type "clear"
Enter
Sleep 0.3s
Type "# next: containers"
Enter
Sleep 1s
Type "# chicanodev.com"
Enter
Sleep 3.97s
