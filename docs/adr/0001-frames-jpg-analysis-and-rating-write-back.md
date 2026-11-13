# ADR-0001: Frames, JPG analysis and rating write-back

**Status:** Accepted — 2026-11-13

## Context

The photographer culls in Lightroom Classic 15.5. Their sessions are shot either JPG-only or RAW+JPG; the RAWs are mainly Leica Q3 DNGs and Fujifilm X-T50 RAFs. framewise has to support both kinds of Session. RAW-only sessions are out of scope for now.

Facts about the photographer's Lightroom setup, checked on 2026-11-13:
- "Treat JPEG files next to raw files as separate photos" is **on**, so Lightroom imports a RAW and its JPG as two separate photos.
- "Automatically write changes into XMP" is **off**, so ratings live only in the catalog.
- Some files already carry a Camera rating: in-camera 1★ on both the DNG and the JPG, and in-file color labels.
- Lightroom's Pick and Reject flags exist only in the catalog. They can't be set through files.

## Decision

1. **Frame is the unit of work.**
   - framewise scans a Session's root folder recursively, including subfolders.
   - A RAW and a JPG with the same base name **in the same folder** become one RAW+JPG Frame. A JPG on its own becomes a JPG-only Frame.
   - Grouping, judging and rating all operate on Frames, so a RAW+JPG pair is never counted twice.
   - A RAW file with no matching JPG (for example a `-Pano.dng` merge) is reported as skipped.
   - Groups can span subfolders.
2. **Analysis always reads the JPG.** There is no RAW decoding, so JPG-only and RAW+JPG Sessions share one analysis path.
3. **Each Verdict maps to Lightroom metadata as follows:**

   | Verdict | Stars | Color label |
   |---|---|---|
   | Winner | 3 | none |
   | Keeper | 2 | none |
   | Reject | 0 | Red |
   | Unsure | 0 | Yellow |

   - Stars 4 and 5 are left free for the photographer's final selection in Lightroom.
   - Reject doesn't use 1★, because the camera already writes 1★.
   - Label names are read from the photographer's active Lightroom color label set rather than hard-coded, because labels are matched as text (for example `Rot` and `Gelb` in German).
4. **Where the metadata is written depends on the file type.** Every file of a Frame is written:

   | File | Written to |
   |---|---|
   | JPG | Embedded XMP, because Lightroom ignores sidecars for JPGs |
   | DNG | Embedded XMP, because Lightroom ignores sidecars for DNGs |
   | Other RAW (RAF, ARW, NEF, CR3, …) | `.xmp` sidecar |

5. **Write-back is narrow and reversible.**
   - Only the rating and the color label change. All other existing metadata is kept, including develop settings in sidecars and Leica crop data.
   - Write-back is opt-in, runs as a dry run first and shows a diff.
   - It records each file's previous values so the change can be undone.
6. **Camera ratings count.**
   - They are shown in the Review UI and act as a mild hint during judging.
   - On write-back they are overwritten, and the old value is recorded so it can be restored.
7. **The supported workflow is "cull before import".** The photographer copies the card, runs framewise, reviews, writes back, then imports into Lightroom, which reads the metadata during import. Writing back to files that are already in a catalog is not supported. The *Read Metadata from Files* command would overwrite any catalog changes that aren't in the files.

## Consequences

- Exposure judgements come from the camera's JPG, which may clip highlight or shadow detail that the RAW still holds. RAW+JPG Frames are therefore treated more leniently on exposure than JPG-only Frames.
- Writing XMP into JPGs and DNGs changes those files' bytes, though not their image data. This narrows the handover's rule of never modifying source photos to "never change image data, and change metadata only after review".
- Adding RAW-only support later means extracting the preview JPG embedded in each RAW, which slots in as an alternative Analysis source.
