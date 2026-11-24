# ADR-0011: RAW-only Frames are analyzed from the embedded preview

**Status:** Accepted — 2026-11-20. Amends ADR-0001's "Analysis always reads the JPG" and "RAW-only sessions are out of scope". Amended — 2026-11-24: Rating write-back and Trash handle RAW-only Frames (#151).

## Context

ADR-0001 left RAW-only Sessions out of scope and reported a RAW without a JPG of the same name as skipped. Photographers who shoot RAW only, and merged RAWs such as a `-Pano.dng`, therefore got nothing from framewise. ADR-0001 already noted the way in: every RAW framewise supports embeds at least one preview JPG, and that preview can stand in as the Analysis source. framewise has no RAW decoder and should not need one. #148 prepared for this by keying a Frame by its main file rather than its JPG.

What the photographer's cameras embed, checked on 2026-11-20 with ExifTool 13.55:
- Fujifilm X-T50 RAF: one 4416×2944 `PreviewImage`, which carries the camera's EXIF, including orientation and capture time.
- Leica Q3 DNG: a full-size 9520×6336 `JpgFromRaw` without EXIF, besides two small previews.

## Decision

1. **A RAW with no JPG of the same name in its folder is a RAW-only Frame.** Pairing is otherwise unchanged: a RAW and a JPG with the same base name still make one RAW+JPG Frame, and each RAW left over, including several sharing a base name, makes a RAW-only Frame of its own. Its main file is the RAW.
2. **A RAW-only Frame's Analysis source is the largest JPG embedded in its RAW.** framewise asks ExifTool for every `PreviewImage`, `JpgFromRaw` and `OtherImage` in the RAW, tries them largest first, and keeps the first one Pillow can read. It then copies the RAW's metadata into the preview, so orientation, capture time and focus point are read as from a camera JPG.
3. **A RAW without a usable preview is skipped, with the reason.** A preview ExifTool reports an error extracting gives way to the next largest, and a preview the RAW's metadata can't be copied into is not used, since its orientation and capture time would be wrong. The Review UI lists skipped files with their reasons.
4. **Previews are cached next to the Session store, never in the Session folder.** They live in a `<store>-previews` folder beside the Session store's database, one JPG per RAW-only Frame, recorded in the store with the RAW's size and modification time. A re-run reuses a cached preview, thumbnail and analysis while the RAW is unchanged and extracts it again when the RAW changes. A preview leaves the cache with its Frame, and `framewise reset` deletes the cache with the store.
5. **RAW+JPG Frames keep reading the camera's JPG.** Nothing changes for them.
6. **A RAW-only Frame gets the exposure leniency of a RAW+JPG Frame**, because its RAW holds detail that the preview, like a camera JPG, has clipped.
7. **Rating write-back and Trash treat a RAW-only Frame's RAW as they treat the RAW of a RAW+JPG Frame.** Write-back writes a DNG's embedded XMP and another RAW's `.xmp` sidecar, as ADR-0001 says, and records the originals so Undo write-back and Reset Session restore them. Trash moves the sidecar, then the RAW, and the Frame's cached preview leaves the cache with it, as §4 says. Since write-back changes only metadata, a re-run keeps reusing the cached preview and analysis of a DNG it wrote into.

## Considered Options

- **Decoding the RAW (rawpy, LibRaw).** Rejected: a large native dependency, slower than reading a preview, and its rendering would differ from the camera's JPG that RAW+JPG Frames are judged by.
- **Always the `PreviewImage` tag.** Rejected: on the Leica Q3 it is a small preview, while the full-size one is `JpgFromRaw`.
- **Caching previews as blobs in the Session store.** Rejected: the Providers, thumbnails and the Review UI's image endpoint read files, and full-size previews of a large Session would bloat the database.
- **Writing previews next to the RAWs.** Rejected: framewise never writes into the Session folder, except for Rating write-back.

## Consequences

- Opening a Session extracts the previews of new or changed RAW-only Frames before the Review UI starts. With ExifTool's persistent process this takes under a tenth of a second per RAW on the photographer's files.
- The preview cache holds each RAW-only Frame's largest preview, often as large as a camera JPG, in framewise's data folder.
- A small preview gives a less reliable Verdict than a camera JPG, so a RAW-only Frame whose preview is shorter than a minimum on its long edge is skipped, with the preview's size as the reason (#152). The minimum defaults to 1600 px, pending the survey of real previews in #149, and is set with `min_preview_long_edge` under `[raw_only]` in `config.toml`, which `framewise review` and `framewise-benchmark` both read.
- A Frame whose kind changes changes its main file: a RAW+JPG Frame whose JPG is deleted becomes a RAW-only Frame identified by its RAW, and exporting a JPG next to a lone RAW turns a RAW-only Frame into a RAW+JPG Frame identified by the JPG. Its Overrides and fixed Group, kept by the old main file, no longer apply to it, and it is analyzed again.
- Opening a Session store from framewise 0.2.0 upgrades it, and 0.2.0 cannot open an upgraded store. The upgrade first copies the store to a `-v0-backup.sqlite` beside it, which is the way back to 0.2.0. `framewise reset` deletes that backup with the store.
