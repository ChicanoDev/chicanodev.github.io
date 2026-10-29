# ChicanoDev Short #1: "tmux for beginners: sessions, splits, detach"
# Vertical 1080x1920, ~55s. Beats match voiceover.md.
# Render: cd this folder; PATH=/workspace/bin:$PATH vhs tmux-for-beginners.tape
# Safe: uses a throwaway tmux config (demo.tmux.conf) and /tmp. Kills the tmux server at the end.

Output tmux-for-beginners.mp4
Output tmux-for-beginners.gif

Set Shell "bash"
Set FontFamily "IBM Plex Mono"
Set FontSize 46
Set Width 1080
Set Height 1920
Set Padding 50
Set LineHeight 1.3
Set TypingSpeed 70ms
Set WindowBar Colorful
Set WindowBarSize 60
Set BorderRadius 24
Set Margin 30
Set MarginFill "#1e1f29"
# Brand: Dracula (same as chicanodev.com)
Set Theme { "name": "ChicanoDev", "black": "#21222c", "red": "#ff5555", "green": "#50fa7b", "yellow": "#f1fa8c", "blue": "#bd93f9", "magenta": "#ff79c6", "cyan": "#8be9fd", "white": "#f8f8f2", "brightBlack": "#6272a4", "brightRed": "#ff6e6e", "brightGreen": "#69ff94", "brightYellow": "#ffffa5", "brightBlue": "#d6acff", "brightMagenta": "#ff92df", "brightCyan": "#a4ffff", "brightWhite": "#ffffff", "background": "#282a36", "foreground": "#f8f8f2", "selection": "#44475a", "cursor": "#f8f8f2" }

# ---- hidden setup ----
Hide
Type "tmux kill-server 2>/dev/null"
Enter
Type "export PS1='$ '"
Enter
Type "cp demo.tmux.conf /tmp/demo.tmux.conf && cd /tmp"
Enter
Type "alias tmux='tmux -f /tmp/demo.tmux.conf'"
Enter
Type `printf '#!/bin/bash\nfor i in $(seq 1 600); do echo "step $i: still running"; sleep 1; done\n' > longjob && chmod +x longjob`
Enter
Type "clear"
Enter
Show

# ---- 0:00-0:05 HOOK ----
Sleep 400ms
Type "# Lost your work?"
Sleep 700ms
Enter
Type "# tmux fixes that."
Sleep 700ms
Enter
Sleep 400ms

# ---- 0:05-0:12 start a named session, run something long ----
Type "clear"
Enter
Type "tmux new -s demo"
Sleep 600ms
Enter
Sleep 1.5s
Type "./longjob"
Sleep 500ms
Enter
Sleep 3.3s

# ---- 0:12-0:22 split the screen (prefix = Ctrl+A) ----
Ctrl+A
Sleep 900ms
Type '"'
Sleep 1.4s
Ctrl+A
Sleep 700ms
Up
Sleep 1.2s
Ctrl+A
Sleep 700ms
Down
Sleep 1s
Type "echo hi from pane 2"
Sleep 400ms
Enter
Sleep 1.5s

# ---- 0:22-0:32 the config: prefix, mouse ----
Type "clear"
Enter
Type "head -4 demo.tmux.conf"
Sleep 400ms
Enter
Sleep 7s

# ---- 0:32-0:44 detach, job keeps running, reattach ----
Ctrl+A
Sleep 800ms
Type "d"
Sleep 2.5s
Type "tmux ls"
Sleep 500ms
Enter
Sleep 2.5s
Type "tmux attach"
Sleep 500ms
Enter
Sleep 4s

# ---- 0:44-0:55 CTA ----
Ctrl+A
Sleep 500ms
Type "d"
Sleep 1s
Type "clear"
Enter
Sleep 800ms
Type "# my tmux config + guide:"
Enter
Sleep 600ms
Type "# chicanodev.com"
Sleep 5s

Hide
Type "tmux kill-server"
Enter
Sleep 1s
Show
