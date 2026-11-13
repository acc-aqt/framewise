# framewise

framewise helps a photographer cull a shoot. It groups near-duplicate Frames, proposes a Verdict for each one with Reasons, and lets the photographer review the result before any rating reaches Lightroom Classic.

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

## Judging

**Group**:
Frames that are near-duplicates of each other or come from one burst. Within a Group, Frames are judged against each other rather than in isolation.
_Avoid_: Burst, cluster, series, stack

**Verdict**:
framewise's judgement of one Frame: Winner, Keeper, Reject or Unsure.
_Avoid_: Decision, flag, pick

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

**Keeper budget**:
The share of a Session's Frames the photographer roughly wants to keep. It decides how many Frames become Keepers. Each Group's Winner is kept regardless.
_Avoid_: Quota, target, limit

**Reference rating**:
A rating the photographer gave a Frame in Lightroom during a past cull. framewise uses these only to measure how often it agrees with the photographer.
_Avoid_: Ground truth, label

## Review

**Proposal**:
The full set of Verdicts and Reasons for a Session, before the photographer has reviewed it. Nothing reaches disk at this stage.
_Avoid_: Suggestion, selection, result

**Review UI**:
The local web front end where the photographer confirms, changes or refines the Proposal.
_Avoid_: App, dashboard, gallery

**Override**:
A change the photographer makes to a Verdict or a Group in the Review UI. An Override always beats framewise's own judgement.
_Avoid_: Correction, edit

**Rating write-back**:
The explicit, opt-in and reversible step that writes the reviewed Verdicts into the Frames' files so Lightroom Classic can read them.
_Avoid_: Export, sync, apply
