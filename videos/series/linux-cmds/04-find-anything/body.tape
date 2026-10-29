# Basic Linux commands #4: find anything
# Safe: runs in the chicanodev-vhs docker image as the demo user; nothing on the host is touched.

# ---- hidden setup ----
Hide
Type "export PS1='$ '"
Enter
Type "mkdir -p proj/src proj/docs"
Enter
Type "echo 'TODO fix login' > proj/src/app.py"
Enter
Type "echo done > proj/src/util.py"
Enter
Type "echo 'TODO write docs' > proj/docs/readme.md"
Enter
Type "sudo updatedb"
Enter
Type "clear"
Enter
Show

# @beat 0:00 Hook
Type "# It's in there somewhere..."
Enter
Sleep 1s
Type "# find  locate  grep"
Enter
Sleep 0.64s

# @beat 0:05 Find
Type "clear"
Enter
Sleep 0.3s
Type "find proj -name '*.py'"
Enter
Sleep 4s
Type "find proj -type d"
Enter
Sleep 3.5s
Sleep 3.12s

# @beat 0:19 Locate
Type "clear"
Enter
Sleep 0.3s
Type "locate os-release"
Enter
Sleep 3.5s
Type "# fast: uses an index"
Enter
Sleep 6.19s

# @beat 0:32 Grep
Type "clear"
Enter
Sleep 0.3s
Type "grep -rn TODO proj"
Enter
Sleep 4.5s
Sleep 6.59s

# @beat 0:45 Grep options
Type "clear"
Enter
Sleep 0.3s
Type "grep -ril todo proj"
Enter
Sleep 4.5s
Type "# -i case  -l names only"
Enter
Sleep 4.84s

# @beat 0:58 Recap
Type "clear"
Enter
Sleep 0.3s
Type "# find = names"
Enter
Sleep 1s
Type "# locate = speed"
Enter
Sleep 1s
Type "# grep = contents"
Enter
Sleep 1.06s

# @beat 1:05 CTA
Type "clear"
Enter
Sleep 0.3s
Type "# next: pipes and text"
Enter
Sleep 1s
Type "# chicanodev.com"
Enter
Sleep 2.69s
