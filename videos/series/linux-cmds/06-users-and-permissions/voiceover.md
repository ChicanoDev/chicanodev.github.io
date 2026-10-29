# Basic Linux commands #6: users and permissions

Series: Basic Linux Commands (6 of 9) · Target length ~78s · Pace ~150 wpm
Terminal beats match `body.tape` markers. Pause where the screen is busy; trim silence in edit.

> On screen: `whoami`, `sudo`, `stat`, `chmod`, `useradd`, `id`, `chown`.

## [0:00-0:05] Hook
Permission denied. Every Linux user has seen it. Here is how permissions actually work.

## [0:05-0:16] Whoami
Whoami tells you who you are. Put sudo in front of any command and it runs as the administrator instead.

## [0:16-0:30] Permissions
Every file has permissions for three groups: the owner, the group, and everyone else. Each can read, write, or execute. Dash r w dash means read and write, but not execute.

## [0:30-0:42] Chmod
Chmod changes those permissions. Plus x makes the file executable, and now an x appears in all three groups.

## [0:42-0:54] Useradd
Useradd creates a new user, and id shows who they are. You would then use passwd to set their password.

## [0:54-1:06] Chown
Chown changes who owns a file. Now ana owns run dot sh, and the owner column has changed.

## [1:06-1:12] Su
Su switches to another user entirely. Here, sudo dash u runs just one command as ana.

## [1:12-1:18] CTA
Next: checking on your system's health. Follow along at chicanodev dot com.

## Post copy
**YouTube Shorts title:** sudo, chmod, chown: Linux permissions explained #shorts
**Reels / Shorts caption:** Linux users and permissions: whoami, sudo, chmod, chown and useradd. Part 6 of 9.
**Hashtags:** #linux #linuxcommands #terminal #bash #learntocode #chicanodev
