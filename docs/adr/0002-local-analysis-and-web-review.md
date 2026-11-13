# ADR-0002: Local analysis pipeline and web Review UI

**Status:** Accepted — 2026-11-13

## Context

framewise runs on the photographer's MacBook Pro (M2 Pro, 10 cores, 16 GB). The agreed performance budget is **15 minutes for a 200-Frame Session** on the first pass, which works out to about 4.5 s per Frame. Analysis reads JPGs only (ADR-0001). The photographer wants a web front end for confirming, changing and refining the selection before anything is written to disk.

## Decision

1. **Everything runs locally.** No photo leaves the machine.
2. **Analysis runs in two tiers:**
   - **Tier 1 runs on every Frame.** It uses Apple's Vision framework on the Neural Engine plus cheap image maths on downscaled JPGs, and it produces:
     - the image fingerprints used to group Frames;
     - face-quality and closed-eye signals;
     - an aesthetics score;
     - sharpness and exposure measurements.
   - **Tier 2 runs only on the leading candidates in each group.** It uses a local vision-language model to judge expression and "moment". Which model to use is still open and will be decided by benchmarking on this MacBook against the budget.
3. **Each Group's Proposal follows a set rule.** One clear winner gets the top rating. Other strong Frames are proposed as lower-rated keepers. The rest stay unrated or are proposed as rejects.
4. **framewise keeps its state outside the photo folders.**
   - Analysis results, thumbnails and review state live in one SQLite database per Session under `~/Library/Application Support/framewise/`.
   - Results are cached per file, keyed by path, size and modification time, so re-running a Session is incremental.
   - Nothing is written into the photo folders except Rating write-back.
5. **The Review UI is a local web app.**
   - The backend is Python 3.13 with FastAPI. The Python version is managed with `uv`, separately from any system Python.
   - The backend is bound to `127.0.0.1` and serves the pages and the images.
   - `framewise review <session-folder>` analyses the Session, starts the server and opens the browser.
   - The Review UI opens immediately and fills in as Frames are analysed. The front end is built with **Angular**, using standalone components, signals and the CDK. Angular was picked because the photographer wants to build skills in it for other projects, not because it's the lightest option. The Review UI is the only place ratings get changed. Rating write-back (ADR-0001) is a separate, explicit step that shows a dry-run diff first.

## Consequences

- The budget leaves ample headroom for Tier 1, so Tier 2 gets most of the time. If benchmarking shows the vision-language model can't fit, Tier 2 is dropped and Tier 1 still delivers a usable shortlist.
- macOS only, because Apple Vision is used through PyObjC. That is acceptable for a single-user tool.
