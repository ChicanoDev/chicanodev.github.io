# Basic Linux commands #5: pipes and text tools

Series: Basic Linux Commands (5 of 9) · Target length ~76s · Pace ~150 wpm
Terminal beats match `body.tape` markers. Pause where the screen is busy; trim silence in edit.

> On screen: `cut`, `sort`, pipe `|`, `sed`, `awk`, `tee`.

## [0:00-0:05] Hook
Linux commands do one small thing each. The pipe is how you chain them together.

## [0:05-0:14] Data
Here is a little data file: names and favorite languages, separated by commas. Four people, three languages.

## [0:14-0:26] Cut
Cut pulls out columns. Dash d sets the separator, dash f picks the field. Field two is the language.

## [0:26-0:40] Sort and pipe
Now the pipe, that vertical bar. It feeds the output of one command into the next. Cut the column, pipe it to sort, and the list comes out alphabetical.

## [0:40-0:52] Sed
Sed edits text as it flows past. This one replaces go with golang, everywhere it finds it.

## [0:52-1:03] Awk
Awk is a tiny language for columns. Print dollar one means print the first field.

## [1:03-1:11] Tee
And tee does two things at once: it shows output on screen, and saves a copy to a file. Great for keeping logs.

## [1:11-1:16] CTA
Next: users, sudo and permissions. Follow along at chicanodev dot com.

## Post copy
**YouTube Shorts title:** Linux pipes: cut, sort, sed, awk, tee #shorts
**Reels / Shorts caption:** The Linux pipe and text tools: cut, sort, sed, awk and tee in about a minute. Part 5 of 9.
**Hashtags:** #linux #linuxcommands #terminal #bash #learntocode #chicanodev
