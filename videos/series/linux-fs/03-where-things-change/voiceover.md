# Linux directory structure #3: where things change

Series: Linux Directory Structure (3 of 4) · Target length ~70s · Pace ~150 wpm
Terminal beats match `body.tape` markers. Pause where the screen is busy; trim silence in edit.

> On screen: `ls /var`, `ls /var/log`, `echo hi > /tmp/note`, `uname -r`.

## [0:00-0:05] Hook
Some Linux folders sit still. These ones change every single second. Let's see which.

## [0:05-0:19] Var
Slash var is for variable data, the stuff that grows while the system runs. Logs, mail queues, caches, package databases. If a disk fills up mysteriously, look here first.

## [0:19-0:32] Var state
Var lib keeps the state of services, like databases and package records. Var cache holds data that is safe to delete, because it can always be rebuilt.

## [0:32-0:44] Tmp
Slash tmp is a scratch pad. Any user can write here, and files are usually wiped on reboot, so never keep anything important in it.

## [0:44-0:57] Boot
Slash boot holds what the machine needs to start up: the kernel and boot loader files. Leave it alone unless you know why. Uname dash r shows the kernel you are running.

## [0:57-1:10] CTA
Next time: the strange folders that are not really on disk at all. Follow along at chicanodev dot com.

## Post copy
**YouTube Shorts title:** /var, /tmp and /boot explained (Linux folders) #shorts
**Reels / Shorts caption:** Which Linux folders change while the system runs? /var, /tmp and /boot explained. Part 3 of 4.
**Hashtags:** #linux #linuxfilesystem #terminal #sysadmin #learntocode #chicanodev
