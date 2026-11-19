# ADR-0011: RAW-only Frames are analyzed from the embedded preview

**Status:** Accepted — 2026-11-20. Amends ADR-0001's "Analysis always reads the JPG" and "RAW-only sessions are out of scope".

## Context

ADR-0001 left RAW-only Sessions out of scope and reported a RAW without a JPG of the same name as skipped. Photographers who shoot RAW only, and merged RAWs such as a `-Pano.dng`, therefore got nothing from framewise. ADR-0001 already noted the way in: every RAW framewise supports embeds at least one preview JPG, and that preview can stand in as the Analysis source. framewise has no RAW decoder and should not need one. #148 prepared for this by keying a Frame by its main file rather than its JPG.

What the photographer's cameras embed, checked on 2026-11-20 with ExifTool 13.55:
- Fujifilm X-T50 RAF: one 4416×2944 `PreviewImage`, which carries the camera's EXIF, including orientation and capture time.
- Leica Q3 DNG: a full-size 9520×6336 `JpgFromRaw` without EXIF, besides two small previews.

## Decision

1. **A RAW with no JPG of the same name in its folder is a RAW-only Frame.** Pairing is otherwise unchanged: a RAW and a JPG with the same base name still make one RAW+JPG Frame, and each RAW left over, including several sharing a base name, makes a RAW-only Frame of its own. Its main file is the RAW.
2. **A RAW-only Frame's Analysis source is the largest JPG embedded in its RAW.** framewise asks ExifTool for every `PreviewImage`, `JpgFromRaw` and `OtherImage` in the RAW, tries them largest first, and keeps the first one Pillow can read. It then copies the RAW's metadata into the preview, so orientation, capture time and focus point are read as from a camera JPG.
3. **A RAW without a usable preview is skipped, with the reason.** The Review UI lists skipped files with their reasons.
4. **Previews are cached next to the Session store, never in the Session folder.** They live in a `<store>-previews` folder beside the Session store's database, one JPG per RAW-only Frame, recorded in the store with the RAW's size and modification time. A re-run reuses a cached preview, thumbnail and analysis while the RAW is unchanged and extracts it again when the RAW changes. A preview leaves the cache with its Frame, and `framewise reset` deletes the cache with the store.
5. **RAW+JPG Frames keep reading the camera's JPG.** Nothing changes for them.
6. **A RAW-only Frame gets the exposure leniency of a RAW+JPG Frame**, because its RAW holds detail that the preview, like a camera JPG, has clipped.
7. **Rating write-back and Trash leave RAW-only Frames alone for now.** The write-back dry run says how many RAW-only Frames it leaves out, and trashing a RAW-only Frame is refused with a message. Writing and trashing them is #151.

## Considered Options

- **Decoding the RAW (rawpy, LibRaw).** Rejected: a large native dependency, slower than reading a preview, and its rendering would differ from the camera's JPG that RAW+JPG Frames are judged by.
- **Always the `PreviewImage` tag.** Rejected: on the Leica Q3 it is a small preview, while the full-size one is `JpgFromRaw`.
- **Caching previews as blobs in the Session store.** Rejected: the Providers, thumbnails and the Review UI's image endpoint read files, and full-size previews of a large Session would bloat the database.
- **Writing previews next to the RAWs.** Rejected: framewise never writes into the Session folder, except for Rating write-back.

## Consequences

- Opening a Session extracts the previews of new or changed RAW-only Frames before the Review UI starts. With ExifTool's persistent process this takes under a tenth of a second per RAW on the photographer's files.
- The preview cache holds each RAW-only Frame's largest preview, often as large as a camera JPG, in framewise's data folder.
- A small preview gives a less reliable Verdict than a camera JPG. Skipping Frames whose preview is too small to judge is #152; the preview's size is recorded in the store for that.
