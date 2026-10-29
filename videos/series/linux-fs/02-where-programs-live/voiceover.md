# Linux directory structure #2: where programs live

Series: Linux Directory Structure (2 of 4) · Target length ~72s · Pace ~150 wpm
Terminal beats match `body.tape` markers. Pause where the screen is busy; trim silence in edit.

> On screen: `which ls`, `readlink /bin`, `ls /usr`, `ls /usr/local`, `ls /opt`.

## [0:00-0:05] Hook
Where do your programs actually live on Linux? Four main places. Let's look.

## [0:05-0:21] Bin
Run which ls and you get slash usr slash bin. Slash bin and slash sbin used to hold the essential commands, one for everyone, one for admins. On modern distros they are just shortcuts that point into usr.

## [0:21-0:35] Usr
Slash usr is where most software really lives. Its bin folder has the programs everybody can run, sbin has the admin tools, lib holds libraries, and share holds data like docs and icons.

## [0:35-0:47] Local
Slash usr slash local is for software you install yourself, outside the package manager. Your own scripts and builds go here, so system updates never overwrite them.

## [0:47-0:58] Opt
Slash opt is for big third party apps that bring everything with them, like Chrome or Zoom. Each app gets its own folder, nicely self contained.

## [0:58-1:05] Lib
And lib holds the shared code that programs depend on. Same story, it is linked into usr.

## [1:05-1:12] CTA
Next up: the folders that change while Linux is running. Follow along at chicanodev dot com.

## Post copy
**YouTube Shorts title:** Where do Linux programs live? /bin /usr /opt explained #shorts
**Reels / Shorts caption:** Where do programs actually live on Linux? /bin, /sbin, /usr, /usr/local and /opt in 60 seconds. Part 2 of 4.
**Hashtags:** #linux #linuxfilesystem #terminal #sysadmin #learntocode #chicanodev
