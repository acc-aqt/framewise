# framewise

framewise helps a photographer cull a shoot. It groups near-duplicate Frames, proposes a Verdict for each one with Reasons, and lets the photographer review the result before any rating reaches Lightroom Classic.

Prose and UI text use American spelling (analyze, gray); code identifiers keep their existing names.

## Input

**Session**:
All the Frames from one shoot, culled together as one unit.
_Avoid_: Shoot, folder, import, catalog

**Frame**:
One exposure the camera captured. It is the unit framewise groups, judges and rates, whether it is backed by one file or two.
_Avoid_: Photo, image, shot, file

**JPG-only Frame**:
A Frame backed by a single JPG file.

**RAW+JPG Frame**:
A Frame backed by a RAW file and the JPG the camera saved alongside it.
_Avoid_: Pair, twin, stack

**Analysis source**:
The file whose pixels framewise judges a Frame by. It is always the Frame's JPG.
_Avoid_: Preview

**Camera rating**:
A star rating or color label that was already on a Frame's files before framewise saw them, for example stars set in-camera.
_Avoid_: Existing rating, prior rating

**Session store**:
The per-Session SQLite database in framewise's own data folder (`~/Library/Application Support/framewise/` on macOS, `~/.local/share/framewise/` on Linux and `%LOCALAPPDATA%\framewise\` on Windows by default) that holds a Session's Frames and their thumbnails. framewise never writes it into the Session folder.
_Avoid_: Cache, catalog, index

## Analysis

**Capability**:
One kind of signal framewise reads from a Frame's Analysis source, such as its fingerprint, its faces, whether those faces' eyes are open, face quality or aesthetics.
_Avoid_: Feature, model, check

**Provider**:
An interchangeable implementation of one Capability, built into framewise or installed as a plug-in. Each Capability is served by one Provider at a time.
_Avoid_: Backend, engine, analyzer, model

## Judging

**Group**:
Frames that belong to one Burst or are Near-duplicates of each other. Within a Group, Frames are judged against each other rather than in isolation.
_Avoid_: Cluster, series, stack

**Burst**:
Frames captured within moments of each other that look alike.

**Near-duplicate**:
Frames that look alike although they were captured minutes apart or have no capture time.
_Avoid_: Duplicate, copy

**Verdict**:
The outcome framewise assigns one Frame: Winner, Keeper, Reject or Unsure.
_Avoid_: Judgment, decision, flag, pick

**Winner**:
The single best Frame in a Group.
_Avoid_: Pick, best shot, hero

**Keeper**:
A Frame worth keeping that is not its Group's Winner.
_Avoid_: Alternate, second pick

**Reject**:
A Frame framewise proposes not to keep.
_Avoid_: Delete, discard

**Unsure**:
A Frame framewise can't judge confidently and leaves for the photographer to decide.
_Avoid_: Maybe, review

**Reason**:
A short, human-readable explanation attached to a Verdict, such as "eyes closed" or "weaker duplicate of another Frame".
_Avoid_: Tag, flag

**Flaw**:
A problem in a Frame, such as closed eyes or blur, that makes it Unsure or Reject whatever its Score, unless it is its Group's Winner. A Flaw is always shown as a Reason.
_Avoid_: Defect, issue, problem

**Score**:
How good a Frame is on one measure, such as sharpness or exposure, from 0 to 1, and the weighted total framewise ranks Frames by.
_Avoid_: Rating, grade

**Keeper budget**:
The share of a Session's Frames the photographer roughly wants to keep. It decides how many Frames become Keepers. Each Group's Winner is kept regardless.
_Avoid_: Quota, target, limit

**Reference rating**:
A rating the photographer gave a Frame in Lightroom during a past cull. framewise uses these only to measure how often it agrees with the photographer.
_Avoid_: Ground truth, label

**Reference benchmark**:
The photographer's own Session with Reference ratings, which `framewise-benchmark` measures agreement on and framewise's thresholds are calibrated against. Its photos are private and not in the repo.

## Review

**Proposal**:
The full set of Verdicts and Reasons for a Session, before the photographer has reviewed it. Nothing reaches disk at this stage.
_Avoid_: Suggestion, selection, result

**Review UI**:
The local web front end where the photographer confirms, changes or refines the Proposal.
_Avoid_: App, dashboard, gallery

**Override**:
A change the photographer makes to a Verdict or a Group in the Review UI. It beats framewise's own judgment and survives re-analysis.
_Avoid_: Correction, edit

**Verdict Override**:
An Override of one Frame's Verdict. When a Group has more than one Winner Override, only its first Frame's wins and the rest fall back to framewise's Verdict.

**Group Override**:
An Override that fixes which Group a Frame belongs to, made by splitting, merging or moving Frames. Frames it fixes are no longer grouped automatically.

**Trash**:
To move a Frame's files to the OS Trash and take the Frame out of the Session, after the photographer confirms. It is the only way framewise removes files, and it never deletes them outright. Unlike a Reject, a trashed Frame is gone from the Review UI.
_Avoid_: Delete, remove, discard

**Rating write-back**:
The explicit, opt-in and reversible step that writes the reviewed Verdicts into the Frames' files so Lightroom Classic can read them.
_Avoid_: Export, sync, apply

## Releases

**Release**:
A numbered version of framewise, such as `0.1.0`: a `vX.Y.Z` tag on `main` with its release notes on GitHub. Photographers still update from `main`; a Release names what they have.
_Avoid_: Build, drop, ship

**Changelog**:
The hand-written list of user-visible changes in each Release, newest first, with changes not yet in a Release under Unreleased. The Review UI shows it under What's new.
_Avoid_: Release log, history, news
