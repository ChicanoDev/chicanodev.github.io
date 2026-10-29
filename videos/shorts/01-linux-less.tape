Output recordings/01-linux-less-terminal.mp4

Set Shell "bash"
Set Theme "Dracula"
Set FontSize 32
Set Width 960
Set Height 720
Set TypingSpeed 75ms

Type "clear"
Enter
Sleep 500ms

Type "echo 'Reading large logs? Try less.'"
Enter
Sleep 1s

Type "seq 1 200 > /tmp/chicanodev-demo.log"
Enter
Sleep 500ms

Type "less /tmp/chicanodev-demo.log"
Enter
Sleep 2s

Type "/150"
Enter
Sleep 2s

Type "q"
Enter
Sleep 1s

Type "rm /tmp/chicanodev-demo.log"
Enter
Sleep 1s
