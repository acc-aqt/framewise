# ADR-0004: Group Overrides

**Status:** Accepted — 2026-11-14

## Context

The photographer fixes wrong grouping in the Review UI by splitting a Group, merging two Groups or moving a Frame to another Group. Groups are recomputed from the analysed Frames on every request, a Group's id (its first Frame's id) is not stable, and Frames keep arriving while analysis runs. A fix has to survive re-runs and re-analysis, and Verdict Overrides (ADR-0003) have to keep winning after it.

## Decision

1. **A Group Override pins a Frame to a fixed Group.** It is stored in a `group_overrides` table of the Session store, keyed by JPG path, with a random Group key. Frames sharing a key form one Group. It never refers to a Group id.
2. **A fix pins every Frame of every Group it touches.**
   - Split: the selected Frames get one new key, the rest of their Group another.
   - Merge: every Frame of the merged Groups gets one new key.
   - Move: the Frame and its target Group get one new key, the rest of its old Group another.
3. **Pinned Frames are taken out of automatic grouping.** The Grouper only groups the other Frames by similarity, so re-analysis or newly analysed Frames never undo a fix. A Frame analysed after a fix that would have joined a fixed Group forms a Group with the other unpinned Frames instead; the photographer can move or merge it.
4. **Groups are shown in capture order of their first Frame,** fixed or not.
5. **The Judge re-judges each Group as usual.** Each Group gets one Winner. Verdict Overrides are kept by JPG path, so they still win after a fix. If a merge or move brings two Winner Overrides into one Group, the first in the Group wins and the other falls back to framewise's Verdict, as ADR-0003 already says; its stored Override is kept, so it wins again if the Groups are split apart.
6. **Group Overrides of Frames that vanish from the Session folder are kept**, as Verdict Overrides are.

## Consequences

- There is no "reset to framewise's grouping" yet. Clearing the `group_overrides` rows of a Group would restore it.
- Fixing a Group early during analysis freezes it; later Frames of the same burst need a manual move or merge.
