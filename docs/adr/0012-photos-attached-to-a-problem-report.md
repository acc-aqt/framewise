# ADR-0012: Photos attached to a Problem report

**Status:** Accepted — 2026-11-25. Amends ADR-0002 §1: a photo leaves the machine when the photographer attaches it to a Problem report themselves.

## Context

ADR-0002 §1 says everything runs locally and no photo leaves the machine. A Problem report (#244) lets the photographer tell the maintainers that framewise judged a Group wrongly. Most judging problems can only be reproduced with the images framewise judged, so the report needs a way to carry them. framewise has no server of its own, and the photographer reviews and submits the report on a prefilled GitHub new-issue page.

## Decision

1. **A photo leaves the machine only when the photographer attaches it to a Problem report themselves.** Include images is off by default. framewise never uploads anything, and nothing else changes ADR-0002 §1.
2. **framewise copies the images to a local folder and opens it.** When Include images is ticked, framewise copies each Frame's Analysis source byte for byte, with no re-encoding or downscaling: the JPG, or a RAW-only Frame's embedded preview. The copies go into `problem-report-images` in framewise's data folder, never the Session folder, and each report replaces the previous report's folder, so copies don't pile up. framewise opens the folder in Finder, Explorer or the Linux file manager, and the photographer drags the files into the GitHub page.
3. **Each copy is named after its Frame's main file**, so it matches a row of the report. A RAW-only Frame's copy gets `.jpg` after the RAW's name, such as `DSCF0001.RAF.jpg`, so it doesn't look like a RAW. A second Frame of the same name from another subfolder gets a number, such as `DSCF0001 (2).JPG`.
4. **Files over GitHub's 10 MB image limit are flagged** in the dialog, so the photographer knows to share those another way.
5. **The report reaches GitHub through a prefilled link.** framewise opens a GitHub new-issue page with the title and body filled in, and the photographer submits it with their own account.

## Considered Options

- **A relay service that files the issue and uploads the images for the photographer.** Rejected for now: framewise would need a server to run, pay for and secure, and photos would pass through it. It may be reconsidered if demand shows up, for example from photographers without a GitHub account.
- **A GitHub token stored by framewise, to file the issue and upload the images directly.** Rejected: storing a token is a security burden for every photographer, uploading would happen out of their sight, and GitHub has no public API for uploading images into an issue.
- **Downscaled or re-encoded copies.** Rejected: the maintainers need the same input framewise judged to reproduce the problem.
- **Copying into the Session folder.** Rejected: framewise keeps the photo folders untouched except for Rating write-back and Trash (ADR-0002 §4, ADR-0006).

## Consequences

- ADR-0002 §1 now has one exception: images the photographer attaches to a Problem report.
- The copies carry the photos' metadata, including location and owner info, unless it is removed from them.
- The last report's copies stay in the data folder until the next report replaces them.
