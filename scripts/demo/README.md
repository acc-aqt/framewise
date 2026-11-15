# Demo video

Records the ~40-second workflow video (open a Session → analysis → merge Groups → Compare with
Winner and Make Winner → Rating write-back) by driving the real Review UI with Playwright.

```sh
cd scripts/demo
npm ci && npx playwright install chromium
cp demo.config.example.json demo.config.json   # set the Session folder, merges and Winner
node record.mjs open    # picker → analysis; needs a Session folder without a store
node record.mjs work    # retakeable: starts from the analysed snapshot each time
node render.mjs         # writes the MP4 named in demo.config.json
```

The README's `docs/images/workflow.gif` is made from that MP4:

```sh
ffmpeg -i ~/Desktop/framewise-demo/framewise-demo.mp4 -vf "fps=10,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=192:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" ../../docs/images/workflow.gif
```

- `open` refuses a folder that is analysed already; run `framewise reset` on it first.
- No Finder dialog appears: `bin/osascript` stands in for it and answers with the configured
  folder.
- `work` really writes ratings into the files, then undoes the write-back once the take is
  recorded.
- Raw takes and the snapshot live in `out/`, which is not committed.
- A separate demo from another shoot: write e.g. `sewts.config.json` and pass `--config
  sewts.config.json` to `record.mjs` and `render.mjs`; its takes go to `out/sewts/`.
