# <picture><source media="(prefers-color-scheme: dark)" srcset="docs/brand/mark-dark.svg" /><img src="docs/brand/mark-light.svg" alt="" width="32" height="32" /></picture> framewise

## Install

The repo has two parts:

- `backend/`: the Python FastAPI backend and the `framewise` command, managed with [`uv`](https://docs.astral.sh/uv/). `uv` installs and pins its own Python, so the system Python is untouched.
- `frontend/`: the Angular Review UI, which the backend serves.

Clone the repo:

```sh
git clone https://github.com/acc-aqt/framewise.git
cd framewise
```

Install the prerequisites yourself:

- [uv](https://docs.astral.sh/uv/getting-started/installation/).
- [Node.js](https://nodejs.org), preferably in the version recorded in [`frontend/.nvmrc`](frontend/.nvmrc). With [nvm](https://github.com/nvm-sh/nvm), `nvm use` in `frontend/` reads it. The setup script warns if your Node.js is a different version.
- On macOS, [Homebrew](https://brew.sh).

Then run the setup script:

```sh
scripts/setup.sh
```

It installs everything else framewise needs, optional tools included, builds the Review UI and installs the backend. `scripts/setup.sh --help` says what it does and on which platforms it runs. Re-running it is safe: after pulling new changes, run it again to update framewise.

## Platform support

- **macOS**: the Apple Vision Providers serve every Capability. `aesthetics` needs macOS 15 or later.
- **Linux**: the [portable Providers](#providers) serve `fingerprint`, `face-detection` and `eye-state`. There is no `face-quality` or `aesthetics` Provider for Linux yet.
- The portable Providers also run on macOS 14 or later, which onnxruntime needs.

## Running it

Review a Session:

```sh
cd backend
uv run framewise review /path/to/session-folder
```

Or leave out the folder (`uv run framewise review`) and choose it in the Review UI: **Choose Session folder…** opens the Finder folder dialog (on Linux, zenity's). To review another Session, restart framewise. framewise scans subfolders too; put an empty `.framewise-ignore` file in a folder to leave it and everything under it out of the Session.

This scans the folder, starts the server on `http://127.0.0.1:8765/` and opens the browser straight away. It then analyses each Frame's JPG with the installed analysis Providers, using every core; which ones a machine gets is under [Platform support](#platform-support). The Review UI shows progress and fills in with Groups of near-duplicate and burst Frames as analysis runs. Each Frame gets a proposed Verdict (Winner, Keeper, Reject or Unsure) with Reasons, judged from its sharpness, motion blur, exposure and, where an `aesthetics` Provider is available, an aesthetics score. In Frames with faces, every face is checked for closed eyes, sharpness and, where a `face-quality` Provider is available, face quality, and sharpness is judged on the faces rather than the whole image. A Camera rating, such as in-camera stars, nudges a Frame up a little but never past a technical flaw. The Keeper budget slider sets roughly what share of the Session's Frames to keep (40% to start, stored per Session): each Group's Winner always stays, then the best Frames without flaws become Keepers until the budget is spent, and the slider shows how many Keepers result. The Review UI filters by Verdict and by Reason, and an open Group and the loupe show a badge on each face. Results are kept in the Session store under `~/Library/Application Support/framewise/` (on Linux, `$XDG_DATA_HOME/framewise/`, by default `~/.local/share/framewise/`), so a re-run only analyses new or changed Frames.

To review from another machine, such as when framewise runs on a headless Linux box, forward the port over SSH (`ssh -L 8765:127.0.0.1:8765 <host>`) and open `http://127.0.0.1:8765/` on your machine.

- `--port` picks another port.
- `--background` analyses on a quarter of the cores at background priority, so apps like Lightroom stay responsive.
- `--allow-sleep` lets the machine sleep during analysis. By default framewise keeps it awake until analysis finishes (on Linux, through `systemd-inhibit` where it exists). `FRAMEWISE_DATA_DIR` overrides the Session store folder. If the Review UI has not been built, `framewise review` warns you.

In an open Group, review with Lightroom Classic's shortcuts: `1`–`5` set stars (`0` clears them), `6`–`9` set color labels, `P` / `X` / `U` keep, reject and clear, `W` makes the current Frame the Group's Winner, `←` / `→` move between Frames and `⌥←` / `⌥→` step through the current Group. `E` opens the loupe, `Z` zooms to 100% and `Esc` closes it. Overrides are saved in the Session store as you go (ADR-0003). The Keeper budget never changes them, and the Frames you keep count towards it. Fix wrong grouping in an open Group: split it at a Frame or split off the selected Frames, move a Frame to the previous or next Group, or merge the Group with its neighbour. Fixed Groups are kept on later re-runs (ADR-0004); "Reset grouping" hands a fixed Group back to framewise's grouping.

## Providers

By default each Capability (`fingerprint`, `face-detection`, `eye-state`, `face-quality`, `aesthetics`) uses its highest-priority Provider available on the machine. To choose one yourself, name its Provider id in a `config.toml` in the same folder as the Session store:

```toml
[providers]
eye-state = "apple-vision-eye-state"
```

Capabilities left out keep the default. A Provider that is not installed or not available on the machine is an error, never a silent fallback. `framewise-benchmark` reads the same file, and `--provider <capability>=<id>`, repeatable, overrides it for one run, so Providers can be compared against your Reference ratings; its report names the Provider that served each Capability.

The portable Providers run on Linux and macOS with free, local models. On Linux the [setup script](#install) installs them. On macOS, install them with the `portable` extra (`cd backend && uv sync --extra portable`); the setup script keeps them when you run it again. DINOv2-small, run by onnxruntime, then serves `fingerprint` (`dinov2-small-fingerprint`), and MediaPipe's Face Landmarker serves `face-detection` (`mediapipe-face-detection`) and `eye-state` (`mediapipe-eye-state`). They rank below Apple Vision, so on macOS Apple Vision stays the default ([Platform support](#platform-support)). Their model files are downloaded on first use into a `models` folder next to the Session stores and checked against pinned SHA-256 checksums. On a machine that will analyse offline, fetch them ahead of time with `uv run framewise models download`. To write your own Provider, such as another face detector or eye-state check, see [docs/providers.md](docs/providers.md).

## Rating write-back

Nothing is written to the photos until you ask. Once analysis has finished, **Rating write-back…** in the Review UI shows a dry run: every file with its current and new rating and color label. Only after you confirm does framewise write the Verdicts (ADR-0001): Winner 3★, Keeper 2★, Reject 0★ with the red label, Unsure 0★ with the yellow label. Overrides count: an Override's Verdict replaces framewise's, and stars or a color label set with the shortcuts replace the ones the Verdict maps to. JPGs and DNGs get embedded XMP; other RAWs get an `.xmp` sidecar, merged into any existing one. Label names come from Lightroom Classic's active color label set (for example `Rot` and `Gelb`). The previous values are kept in the Session store, so **Undo write-back** restores them and removes sidecars framewise created. Write back before importing into Lightroom. Writing takes a while for large Sessions, because each DNG is rewritten in full, and the screen shows how many files are done. Reloading the page doesn't stop it.

**Reset Session…** on the same screen starts the review over: it undoes the write-back and clears all Overrides, fixed Groups and the Keeper budget. The analysis is kept, so nothing is analysed again. Stars and labels framewise didn't write, such as in-camera ratings, stay as they are.

For development and demos, `uv run framewise reset /path/to/session-folder` resets harder: it undoes the write-back, then deletes the Session store, so the next `framewise review` analyses every Frame again. Quit `framewise review` first. If a file can't be restored, the store is kept so you can retry.

Write-back needs [ExifTool](https://exiftool.org), which the [setup script](#install) installs.

## Tests

Set up the checkout as under [Install](#install), then:

```sh
cd backend && uv run pytest && uv run ruff check .
cd frontend && npx ng test --watch=false
```

Most backend tests use a fake Frame analyzer. `tests/test_providers.py` composes analysis from fake Providers. `tests/test_apple_vision.py` runs the real Apple Vision Providers on generated images and the public-domain reference faces in `tests/fixtures/faces/`, and is skipped on other platforms. `tests/test_mediapipe_faces.py` runs the MediaPipe Providers on the same faces and `tests/test_dinov2_fingerprint.py` the DINOv2 fingerprint on generated images and a Session analysed only by portable Providers; both are skipped unless the `portable` extra is installed and `framewise models download` has run.
