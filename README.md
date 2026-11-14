# <picture><source media="(prefers-color-scheme: dark)" srcset="docs/brand/mark-dark.svg" /><img src="docs/brand/mark-light.svg" alt="" width="32" height="32" /></picture> framewise

## Running it

The repo has two parts:

- `backend/`: the Python 3.13 FastAPI backend and the `framewise` command, managed with [`uv`](https://docs.astral.sh/uv/). `uv` installs and pins its own Python 3.13, so the system Python is untouched.
- `frontend/`: the Angular 22 Review UI. Angular 22 needs Node.js 22.22.3+, 24.15+ or 26+.

Build the Review UI once, so the backend can serve it:

```sh
cd frontend
npm install
npx ng build
```

Then review a Session:

```sh
cd backend
uv run framewise review /path/to/session-folder
```

Or leave out the folder (`uv run framewise review`) and choose it in the Review UI: **Choose Session folder…** opens the Finder folder dialog. To review another Session, restart framewise. framewise scans subfolders too; put an empty `.framewise-ignore` file in a folder to leave it and everything under it out of the Session.

This scans the folder, starts the server on `http://127.0.0.1:8765/` and opens the browser straight away. It then analyses each Frame's JPG with Apple Vision (so it runs on macOS only), using every core. The Review UI shows progress and fills in with Groups of near-duplicate and burst Frames as analysis runs. Each Frame gets a proposed Verdict (Winner, Keeper, Reject or Unsure) with Reasons, judged from its sharpness, motion blur, exposure and, on macOS 15 or later, Apple Vision's aesthetics score. In Frames with faces, every face is checked for closed eyes, sharpness and Apple Vision's face capture quality, and sharpness is judged on the faces rather than the whole image. A Camera rating, such as in-camera stars, nudges a Frame up a little but never past a technical flaw. The Keeper budget slider sets roughly what share of the Session's Frames to keep (40% to start, stored per Session): each Group's Winner always stays, then the best Frames without flaws become Keepers until the budget is spent, and the slider shows how many Keepers result. The Review UI filters by Verdict and by Reason, and an open Group and the loupe show a badge on each face. Results are kept in the Session store under `~/Library/Application Support/framewise/`, so a re-run only analyses new or changed Frames.

- `--port` picks another port.
- `--background` analyses on a quarter of the cores at background priority, so apps like Lightroom stay responsive.
- `--allow-sleep` lets the Mac sleep during analysis. By default framewise keeps it awake until analysis finishes. `FRAMEWISE_DATA_DIR` overrides the Session store folder. If the Review UI has not been built, `framewise review` warns you to run `npx ng build` in `frontend/`.

In an open Group, review with Lightroom Classic's shortcuts: `1`–`5` set stars (`0` clears them), `6`–`9` set color labels, `P` / `X` / `U` keep, reject and clear, `←` / `→` move between Frames and `⌥←` / `⌥→` step through the current Group. `E` opens the loupe, `Z` zooms to 100% and `Esc` closes it. Overrides are saved in the Session store as you go (ADR-0003). The Keeper budget never changes them, and the Frames you keep count towards it. Fix wrong grouping in an open Group: split it at a Frame or split off the selected Frames, move a Frame to the previous or next Group, or merge the Group with its neighbour. Fixed Groups are kept on later re-runs (ADR-0004); "Reset grouping" hands a fixed Group back to framewise's grouping.

## Rating write-back

Nothing is written to the photos until you ask. Once analysis has finished, **Rating write-back…** in the Review UI shows a dry run: every file with its current and new rating and color label. Only after you confirm does framewise write the Verdicts (ADR-0001): Winner 3★, Keeper 2★, Reject 0★ with the red label, Unsure 0★ with the yellow label. Overrides count: an Override's Verdict replaces framewise's, and stars or a color label set with the shortcuts replace the ones the Verdict maps to. JPGs and DNGs get embedded XMP; other RAWs get an `.xmp` sidecar, merged into any existing one. Label names come from Lightroom Classic's active color label set (for example `Rot` and `Gelb`). The previous values are kept in the Session store, so **Undo write-back** restores them and removes sidecars framewise created. Write back before importing into Lightroom. Writing takes a while for large Sessions, because each DNG is rewritten in full, and the screen shows how many files are done. Reloading the page doesn't stop it.

**Reset Session…** on the same screen starts the review over: it undoes the write-back and clears all Overrides, fixed Groups and the Keeper budget. The analysis is kept, so nothing is analysed again. Stars and labels framewise didn't write, such as in-camera ratings, stay as they are.

For development and demos, `uv run framewise reset /path/to/session-folder` resets harder: it undoes the write-back, then deletes the Session store, so the next `framewise review` analyses every Frame again. Quit `framewise review` first. If a file can't be restored, the store is kept so you can retry.

Write-back needs [ExifTool](https://exiftool.org) (`brew install exiftool`).

## Tests

```sh
cd backend && uv run pytest && uv run ruff check .
cd frontend && npx ng test --watch=false
```

Most backend tests use a fake Frame analyzer. `tests/test_vision_analyzer.py` runs the real Apple Vision analyzer on generated images and the public-domain reference faces in `tests/fixtures/faces/`, and is skipped on other platforms.
