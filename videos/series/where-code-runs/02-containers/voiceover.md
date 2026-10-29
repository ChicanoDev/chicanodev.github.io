# Where does code run? #2: containers

Series: Where Does Code Run? (2 of 3) · Target length ~76s · Pace ~150 wpm
Terminal beats match `body.tape` markers. Pause where the screen is busy; trim silence in edit.

> On screen: `cat container.txt`, `uname -r`, `ls -a /.dockerenv`, `ps -e | wc -l`, `os-release`.

## [0:00-0:06] Hook
A container is not a tiny virtual machine. Here is proof, from inside one.

## [0:06-0:24] Diagram
A virtual machine carries its own whole operating system. A container does not. Containers share the host's kernel, and only package the app and its files. That is why they start in a blink, and why you can run dozens on one machine.

## [0:24-0:40] Kernel
Check the kernel version. This container reports the kernel of the machine it runs on, because it has none of its own. And this file is a giveaway that Docker started it.

## [0:40-0:50] Processes
Look at the process list. Four processes in total. A container only sees its own app, not the whole machine.

## [0:50-1:03] Userland
What it does carry is its own userland: its own files and libraries. This one is Debian, running on top of whatever kernel the host has.

## [1:03-1:09] Tradeoff
So: lighter and faster than a virtual machine, but weaker isolation, since the kernel is shared.

## [1:09-1:16] CTA
Last up: what people really mean by the cloud. Follow along at chicanodev dot com.

## Post copy
**YouTube Shorts title:** Containers vs VMs: what's the difference? #shorts
**Reels / Shorts caption:** Containers vs virtual machines: a container shares the host kernel. Here is the proof. Part 2 of 3.
**Hashtags:** #devops #cloud #docker #virtualmachine #learntocode #chicanodev
