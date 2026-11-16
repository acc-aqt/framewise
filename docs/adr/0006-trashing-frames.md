# ADR-0006: Trashing Frames

**Status:** Accepted — 2026-11-16

## Context

While reviewing, the photographer wants to get rid of junk Frames, one at a time or a whole Group at once, without leaving the Review UI. Until now framewise changed the photo folders only through Rating write-back (ADR-0002 §4). Every other step was read-only or reversible. A Reject is only a proposal, so a Frame marked Reject stays on disk.

Lightroom Classic imports a RAW and its JPG as two separate photos (ADR-0001), and photos it has already imported show as missing once their files are gone.

## Decision

1. **Trash moves files to the OS Trash and never deletes them.**
   - framewise uses `send2trash`: the macOS Trash, or the freedesktop Trash on Linux.
   - Where a volume has no Trash, such as some network or external drives, the Frame is reported as failed and stays as it is. framewise never falls back to a permanent delete.
2. **A Frame is trashed whole.** That means its RAW, its JPG and, for a RAW written to through one, its `.xmp` sidecar. Trashing a Group trashes every Frame in it, the Winner included. The JPG goes last, and a Frame leaves the Session once its JPG is in the Trash.
3. **The photographer always confirms.** The confirmation counts the Frames and files, and warns that Frames already imported into Lightroom will show as missing there. It is the same for one Frame as for a Group.
4. **There is no undo inside framewise.** To bring a Frame back, the photographer restores its files from the Trash and runs `framewise review` again. The scan finds the Frame again, and its Overrides and Group Override come back, because those are kept for vanished Frames (ADR-0003, ADR-0004). Trashing removes only the Frame's row, thumbnail and analysis from the Session store.
5. **Rating write-back keeps the originals of trashed files.** Undo write-back skips files that are not in the Session folder, so the undo still works once they are restored.
6. **Trash is allowed while analysis runs.** A Frame trashed during its analysis is skipped without a warning.
7. **The Review UI offers Trash in three places:**
   - `⌫` or `Delete` on the current Frame, as in Lightroom Classic;
   - "Trash Group" in the open Group and in the command palette;
   - "Trash N selected" next to "Split off N selected".

   Afterwards it shows the next Frame left in the Group, else the previous one, else the next Group's first Frame. If none of those is left, it returns to All Groups.

## Considered Options

- **Deleting files permanently.** Rejected: one wrong key would lose photos for good.
- **Hiding Frames from the Session without touching the files.** Rejected: Reject already covers "don't keep this". The photographer asked to get rid of the files.
- **A "Trash all Rejects" action.** Deferred: a Session-wide bulk trash is the riskiest action framewise could offer. Selecting the Rejects of a Group and trashing them covers the burst cleanup for now.

## Consequences

- ADR-0002 §4 now has two exceptions: Rating write-back and Trash.
- A hard reset (`framewise reset`) deletes the Session store. After that, the write-back originals of files still in the Trash are lost, and a restored file keeps the rating write-back gave it.
- If the RAW goes to the Trash but the JPG fails to, the Frame stays in the Session as a JPG-only Frame from the next scan on. The failure is reported, so the photographer can trash the JPG again.
