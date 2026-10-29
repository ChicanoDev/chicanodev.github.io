# ChicanoDev — Linux fundamentals: pwd, ls, mkdir, and find
# Safe: uses a temporary directory; no existing files are modified.
Output recordings/01-linux-first-commands.mp4
Set Shell "bash"
Set Theme "Dracula"
Set FontSize 22
Set Width 1280
Set Height 720
Set TypingSpeed 55ms

Type "clear"
Enter
Sleep 500ms
Type "echo 'Linux basics: finding your way around'"
Enter
Sleep 1s
Type "pwd"
Enter
Sleep 1s
Type "DEMO_DIR=$(mktemp -d)"
Enter
Type "cd '$DEMO_DIR'"
Enter
Type "mkdir -p projects/chicanodev"
Enter
Type "touch projects/chicanodev/README.md"
Enter
Sleep 600ms
Type "ls -la"
Enter
Sleep 1s
Type "find . -maxdepth 3 -type f"
Enter
Sleep 2s
Type "echo 'Tip: pwd = where you are; ls = what is here; find = locate files.'"
Enter
Sleep 2s
Type "cd / && rm -rf '$DEMO_DIR'"
Enter
Sleep 1s
