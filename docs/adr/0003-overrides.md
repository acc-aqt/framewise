# ADR-0003: Overrides

**Status:** Accepted — 2026-11-14

## Context

The photographer reviews the Proposal with Lightroom Classic's shortcuts and Overrides what framewise judged. The Judge recomputes Verdicts on every request from the Groups, and Groups change as Frames are analysed or re-analysed, so a Group's id (its first Frame's id) is not stable. Overrides have to survive closing the browser, re-running `framewise review` and re-analysis. Rating write-back (ADR-0001) is a separate step; here Overrides are only stored. Fixing Groups (split, merge, move) builds on this model.

## Decision

1. **An Override belongs to a Frame and is keyed by its JPG path** in an `overrides` table of the Session store. It never refers to a Group id. Overrides of Frames that vanish from the Session folder are kept, so they come back with the files.
2. **An Override has three independent, optional fields.** A field left empty keeps framewise's judgement.
   - `verdict`: Winner, Keeper, Reject or Unsure. `P` sets Keeper (or confirms the Winner), `X` sets Reject.
   - `stars`: 0–5, set with `1`–`5`. `0` clears it.
   - `label`: a color, set with `6` red, `7` yellow, `8` green, `9` blue. Pressing the same key again clears it.
   - `U` clears the whole Override.
3. **Stars and labels do not change the Verdict**, as in Lightroom, where flags and ratings are independent. On Rating write-back, an Override's stars and label are meant to replace the ones the Verdict maps to (ADR-0001); a field left empty uses the Verdict's.
4. **Verdict Overrides steer the Judge rather than being pasted over its result.**
   - A Frame the photographer made the Winner wins its Group, and the rest of the Group is re-judged against it, so the previous Winner becomes a Keeper or a Reject by the usual rules.
   - A Frame overridden to another Verdict cannot be framewise's Winner, so rejecting the Winner makes framewise pick another.
   - Making a Frame the Winner clears the Winner Override of any other Frame in its Group, so each Group has exactly one Winner. If Groups later merge and hold two, the first in the Group wins and the other falls back to framewise's Verdict.
   - If the photographer overrides every Frame of a Group to a non-Winner Verdict, the Group has no Winner.
5. **The API shows both sides.** Each Frame carries its shown `verdict`, whether that Verdict is an Override (`verdict_overridden`) and its raw `override`.

## Consequences

- Group Overrides (split, merge, move) can be added as further fields or a further table keyed by JPG path, without changing Verdict Overrides.
- Because stars and labels are independent of the Verdict, a Frame can be a Reject with 4 stars. Rating write-back must decide how to show such a Frame in its diff.
