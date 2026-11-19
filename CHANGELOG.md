# Changelog

What changed in framewise, written for photographers. The Review UI shows this list under **What's new**.

## Unreleased

## 0.2.0 — 2026-11-19

- framewise runs on Windows x64 as a preview, with the same portable Providers as on Linux. Set it up with `scripts\setup.ps1`. **Rating write-back** uses the color label names from Lightroom Classic's preferences there too.
- On Windows and Linux, key hints say `Alt+` and `Delete` instead of the Mac symbols.
- framewise can be installed as one package with the Review UI built in. A machine that runs it from that package with `uvx` needs only ExifTool, with no git clone, Node.js or setup script.
- Each Release is published on PyPI as `framewise-cull` and attached to its GitHub Release. Run it with `uvx --python 3.13 --from framewise-cull framewise review`, on Linux and Windows with `framewise-cull[portable]` instead. To update, add `@latest` at the end, such as `framewise-cull[portable]@latest`.
- Without ExifTool, framewise stops at start-up with one message that says how to install it, instead of failing later at **Rating write-back**.
- A Frame without faces is judged on the sharpness of its subject rather than the whole Frame: the area the camera focused on where it recorded one (Fujifilm for now), else the main subject Apple Vision finds (macOS 14 or later). A sharp subject in front of a blurred background is no longer marked soft, and within a Burst the Frame with the sharper subject wins. The score breakdown says what sharpness was measured on.

## 0.1.0 — 2026-11-18

- Open a Session folder and framewise groups its Frames into Bursts and Near-duplicates. Everything is analyzed on your own machine; no Frame leaves it.
- Each Frame gets a proposed Verdict (Winner, Keeper, Reject or Unsure) with Reasons such as "eyes closed" or "motion blur". The Keeper budget slider sets roughly what share of the Session to keep.
- Faces are checked for closed eyes and sharpness, and a Frame with faces is judged by its faces rather than the whole image.
- Review with Lightroom Classic's shortcuts. Change any Verdict with an Override, and fix wrong grouping by splitting, moving or merging Groups. Overrides survive re-analysis.
- Trash junk Frames or whole Groups. Their files go to the OS Trash and are never deleted outright.
- **Rating write-back** writes your Verdicts as stars and color labels that Lightroom Classic reads, after showing a dry run, and can be undone.
- Runs on macOS with Apple Vision, and on Linux with the portable Providers.
- The Review UI shows which version of framewise is running, next to its name. Click it, or choose **What's new** in the command palette, to read this list. After an update, a dot on the version marks what changed until you open it.
