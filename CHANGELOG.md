# Changelog

What changed in framewise, written for photographers. The Review UI shows this list under **What's new**.

## Unreleased

- When framewise judges a Group wrongly, **Report a problem** in the Group's header or the command palette lets you say what you expected instead and send it as a **Problem report**. Open on GitHub shows a prefilled new issue that you can edit before you submit it, and nothing is sent until you do. Without a GitHub account, copy the report or save it as a Markdown file and send it any way you like.
- A **Problem report** too long to prefill a new issue is copied to your clipboard when you choose Open on GitHub, and the new issue asks you to paste it there.
- On Linux and Windows, faces now get a face quality Score, as on macOS: a blurred, badly lit or turned-away face scores lower, so within a Group the Frame whose faces are clearer ranks higher. It needs the `portable` extra; its model, about 7 MB, is downloaded on first use or with `framewise models download`.
- On Linux, Windows and macOS 14, Frames now get an aesthetics Score, as on macOS 15: a more pleasing image scores higher, which helps pick the Winner in a Group and the Keepers in a Session. It needs the `portable` extra; its model, about 180 MB, is downloaded on first use or with `framewise models download`.
- Faces are read for their expression: a smile, eyes looking into the lens and a head facing the camera. Within a Group, a Frame where everyone faces and looks at the camera ranks above one where someone does not, and a smile adds a little; expression never makes a Frame a Reject. An open Group and the loupe show a badge on each face. Needs an `expression` Provider, which the portable MediaPipe Provider serves on macOS, Linux and Windows.
- Someone who glances back over their shoulder into the lens counts as looking at the camera, whichever way their head is turned. A Frame where they do ranks above one where they look away.
- Face badges appear together with the Frame's image in the loupe, the Compare loupe and an open Group, instead of floating over an empty area while the image loads. Stepping to the next Frame no longer shows the previous Frame's badges over it.
- When `framewise review` stops, an open Review UI tab says it lost the connection and how to start it again, instead of showing broken thumbnails. It also notices when you come back to the tab. It reconnects on its own once the server is back, keeping every Override that was saved before it stopped.
- A RAW with no JPG of the same name is now a **RAW-only Frame** instead of being skipped, so a Session shot in RAW only, or a merge such as a `-Pano.dng`, is grouped, judged and reviewed like any other. framewise judges it by the largest preview JPG embedded in the RAW and marks it RAW-only in the Review UI. **Rating write-back** and Trash leave RAW-only Frames alone for now, and say how many RAW-only Frames they leave out.
- Skipped files are listed with the reason, such as a RAW without an embedded preview framewise can read.
- A **RAW-only Frame** whose embedded preview is less than 1600 px on its long edge is skipped instead of getting a misleading Verdict, and the Review UI lists it under **Skipped** with the preview's size. Change the minimum with `min_preview_long_edge` under `[raw_only]` in `config.toml`.
- A Frame that is almost black apart from a blown-out lamp or phone screen is no longer taken for a deliberate low-key shot. It gets an "Underexposed" Reason and can no longer beat a well-exposed Frame to Winner in its Group. Dark Frames with a lit subject, such as a lit face, still count as low-key. Frames analyzed by an earlier version are re-analyzed.

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
