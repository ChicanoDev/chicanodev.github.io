# Basic Linux commands #5: pipes and text tools
# Safe: runs in the chicanodev-vhs docker image as the demo user; nothing on the host is touched.

# ---- hidden setup ----
Hide
Type "export PS1='$ '"
Enter
Type "cd ~"
Enter
Type `printf 'name,lang\nana,python\nbo,go\ncy,rust\ndee,go\n' > people.csv`
Enter
Type "clear"
Enter
Show

# @beat 0:00 Hook
Type "# small tools + pipes"
Enter
Sleep 1s
Type "# = superpowers"
Enter
Sleep 1.48s

# @beat 0:05 Data
Type "clear"
Enter
Sleep 0.3s
Type "cat people.csv"
Enter
Sleep 3.5s
Sleep 3.87s

# @beat 0:14 Cut
Type "clear"
Enter
Sleep 0.3s
Type "cut -d, -f2 people.csv"
Enter
Sleep 4s
Sleep 5.81s

# @beat 0:26 Sort and pipe
Type "clear"
Enter
Sleep 0.3s
Type "cut -d, -f2 people.csv | sort"
Enter
Sleep 5s
Sleep 6.32s

# @beat 0:40 Sed
Type "clear"
Enter
Sleep 0.3s
Type "sed 's/go/golang/' people.csv"
Enter
Sleep 4.5s
Sleep 4.82s

# @beat 0:52 Awk
Type "clear"
Enter
Sleep 0.3s
Type "awk -F, '{print $1}' people.csv"
Enter
Sleep 4.5s
Sleep 3.68s

# @beat 1:03 Tee
Type "clear"
Enter
Sleep 0.3s
Type "ls | tee list.txt"
Enter
Sleep 3.5s
Sleep 2.66s

# @beat 1:11 CTA
Type "clear"
Enter
Sleep 0.3s
Type "# next: users + permissions"
Enter
Sleep 1s
Type "# chicanodev.com"
Enter
Sleep 0.34s
