# ChicanoDev — Git fundamentals in a temporary local repository
# No remote and no push. Requires git installed.
Output recordings/02-git-first-commit.mp4
Set Shell "bash"
Set Theme "Dracula"
Set FontSize 22
Set Width 1280
Set Height 720
Set TypingSpeed 55ms

Type "clear"
Enter
Type "echo 'Git basics: your first local commit'"
Enter
Sleep 1s
Type "DEMO_DIR=$(mktemp -d) && cd '$DEMO_DIR'"
Enter
Type "git init -q"
Enter
Type "git config user.name 'ChicanoDev Demo'"
Enter
Type "git config user.email 'demo@example.invalid'"
Enter
Type "printf '# My first project\\n' > README.md"
Enter
Type "git status --short"
Enter
Sleep 1s
Type "git add README.md"
Enter
Type "git commit -qm 'docs: add README'"
Enter
Type "git log --oneline -1"
Enter
Sleep 2s
Type "echo 'A commit is a snapshot of your project.'"
Enter
Sleep 2s
Type "cd / && rm -rf '$DEMO_DIR'"
Enter
Sleep 1s
