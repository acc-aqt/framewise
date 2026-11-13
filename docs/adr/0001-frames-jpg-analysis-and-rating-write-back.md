# ADR-0001: Frames, JPG analysis and rating write-back

**Status:** Accepted — 2026-11-13

## Context

The photographer culls in Lightroom Classic. Their portrait and event/wedding sessions are shot either JPG-only or RAW+JPG, and framewise has to support both. RAW-only sessions are out of scope for now.

## Decision

1. **Frame is the unit of work.** When framewise scans a Session, a RAW and a JPG with the same base name in the same folder become one Frame, and a JPG on its own also becomes a Frame. Grouping, scoring and shortlisting all operate on Frames, so a RAW+JPG pair is never counted twice. A RAW file with no matching JPG is reported as skipped.
2. **Analysis always reads the JPG.** There is no RAW decoding, so JPG-only and RAW+JPG Sessions share one analysis path.
3. **Rating write-back depends on the kind of Frame:**
   - JPG-only Frame: the rating is written to the JPG's embedded XMP. Lightroom Classic ignores `.xmp` sidecar files for JPGs.
   - RAW+JPG Frame: the rating is written to **both** the RAW's `.xmp` sidecar and the JPG's embedded XMP. The rating then survives whether Lightroom shows the pair as one photo or as two separate photos.
4. Write-back only changes `xmp:Rating`. Any other existing XMP, including Lightroom's develop settings in a RAW's sidecar, is kept. Write-back is opt-in, has a dry-run mode, and records each file's previous rating so it can be undone.

## Consequences

- Exposure scores come from the camera's JPG, which may clip highlight or shadow detail that the RAW still holds. framewise should flag exposure-based decisions as lower confidence.
- Writing XMP into a JPG changes that file's bytes, though not its pixels. This narrows the handover's rule of never modifying source photos to "never change image data, and change metadata only when asked".
- Adding RAW-only support later means extracting the preview JPG embedded in each RAW, which slots in as an alternative Analysis source.
