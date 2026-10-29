# Where does code run? #1: bare metal vs virtual machines

Series: Where Does Code Run? (1 of 3) · Target length ~76s · Pace ~150 wpm
Terminal beats match `body.tape` markers. Pause where the screen is busy; trim silence in edit.

> On screen: ASCII stacks via `cat bare-metal.txt` / `cat vm.txt`, then `nproc` and `free -h`.

## [0:00-0:07] Hook
Where does your code run? Four answers: bare metal, VMs, containers, the cloud. We start with two.

## [0:07-0:23] Bare metal
Bare metal is the simple one. A real physical computer, with one operating system, running your apps directly on the hardware. Fast, and you get every bit of the machine. But it does one job, and if it dies, everything on it dies.

## [0:23-0:40] Virtual machine
A virtual machine adds a layer called the hypervisor. It slices one physical box into many pretend computers, each with its own full operating system. To the software inside, it looks like real hardware.

## [0:40-0:55] Slices
Each virtual machine gets a fixed slice: some cores, some memory. This terminal is itself running inside one. Ask how many cores and how much memory it was given.

## [0:55-1:08] Tradeoff
The trade: virtual machines are isolated and easy to snapshot, but every one carries a whole operating system, so they are heavy and slower to start.

## [1:08-1:16] CTA
Next: containers, the lightweight option. Follow along at chicanodev dot com.

## Post copy
**YouTube Shorts title:** Bare metal vs virtual machine, explained #shorts
**Reels / Shorts caption:** Bare metal vs virtual machine: what is the difference? A hypervisor explains it. Part 1 of 3.
**Hashtags:** #devops #cloud #docker #virtualmachine #learntocode #chicanodev
