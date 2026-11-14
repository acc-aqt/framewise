# framewise

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

This scans the folder, starts the server on `http://127.0.0.1:8765/` and opens the browser straight away. It then analyses each Frame's JPG with Apple Vision (so it runs on macOS only), using every core. The Review UI shows progress and fills in with Groups of near-duplicate and burst Frames as analysis runs. Each Frame gets a proposed Verdict (Winner, Keeper, Reject or Unsure) with Reasons, judged from its sharpness, motion blur, exposure and, on macOS 15 or later, Apple Vision's aesthetics score. In Frames with faces, every face is checked for closed eyes, sharpness and Apple Vision's face capture quality, and sharpness is judged on the faces rather than the whole image. The Review UI filters by Verdict and by Reason, and an open Group and the loupe show a badge on each face. Results are kept in the Session store under `~/Library/Application Support/framewise/`, so a re-run only analyses new or changed Frames.

- `--port` picks another port.
- `--background` analyses on a quarter of the cores at background priority, so apps like Lightroom stay responsive.
- `--allow-sleep` lets the Mac sleep during analysis. By default framewise keeps it awake until analysis finishes. `FRAMEWISE_DATA_DIR` overrides the Session store folder. If the Review UI has not been built, `framewise review` warns you to run `npx ng build` in `frontend/`.

In an open Group, review with Lightroom Classic's shortcuts: `1`–`5` set stars (`0` clears them), `6`–`9` set color labels, `P` / `X` / `U` keep, reject and clear, `←` / `→` move between Frames and `⌥←` / `⌥→` step through the current Group. `E` opens the loupe, `Z` zooms to 100% and `Esc` closes it. Overrides are saved in the Session store as you go (ADR-0003).

## Tests

```sh
cd backend && uv run pytest && uv run ruff check .
cd frontend && npx ng test --watch=false
```

Most backend tests use a fake Frame analyzer. `tests/test_vision_analyzer.py` runs the real Apple Vision analyzer on generated images and the public-domain reference faces in `tests/fixtures/faces/`, and is skipped on other platforms.
