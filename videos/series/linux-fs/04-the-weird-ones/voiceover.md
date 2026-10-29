# Linux directory structure #4: the weird folders

Series: Linux Directory Structure (4 of 4) · Target length ~72s · Pace ~150 wpm
Terminal beats match `body.tape` markers. Pause where the screen is busy; trim silence in edit.

> On screen: `ls /dev`, `cat /proc/uptime`, `ls /sys`, `ls /run`, `ls /mnt /media /srv`.

## [0:00-0:05] Hook
Some Linux folders are not really folders at all. Meet the weird ones.

## [0:05-0:19] Dev
Slash dev holds devices as files. Your disks, your terminal, even a black hole called dev null. Write to it and the data simply vanishes. In Linux, everything is a file.

## [0:19-0:33] Proc
Slash proc is a live window into the kernel. Nothing here is stored on disk. Read proc uptime for seconds since boot, or proc meminfo for your memory. It is generated the moment you read it.

## [0:33-0:44] Sys
Slash sys is similar, but organized around hardware: buses, block devices, drivers. Tools read it to learn what your machine is made of.

## [0:44-0:53] Run
Slash run holds runtime data, like process ids and sockets. It starts empty on every boot.

## [0:53-1:05] Mounts
Last, three quiet ones. Slash mnt is where you manually mount a disk. Slash media is where USB drives show up. And slash srv is for data your server serves, like websites.

## [1:05-1:12] CTA
That is the whole map. Next, the commands to move around it. Follow along at chicanodev dot com.

## Post copy
**YouTube Shorts title:** /dev, /proc, /sys: the weird Linux folders #shorts
**Reels / Shorts caption:** /dev, /proc, /sys and /run are not really on disk. Here is what they are. Part 4 of 4.
**Hashtags:** #linux #linuxfilesystem #terminal #sysadmin #learntocode #chicanodev
