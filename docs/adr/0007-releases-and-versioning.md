# ADR-0007: Releases and versioning

**Status:** Accepted — 2026-11-18. Amended by ADR-0009 and ADR-0010 — 2026-11-19. Amended with the platform marker — 2026-11-25.

## Context

framewise changes daily, and photographers update it with `git pull` and `scripts/setup.sh`. Until now nothing told them what had changed: there were no versions, and the git log is written for contributors. Nor was there an answer to "is this 1.0 yet?".

## Decision

1. **A Release is a `vX.Y.Z` tag on `main` plus a GitHub Release carrying the same notes.**
   - Photographers keep installing and updating from `main`. A Release marks which notes apply; it does not change the update flow. ADR-0010 replaces this: photographers install and update from the wheel each Release publishes.
   - The `v` prefix keeps Release tags apart from other tags in the repo.
2. **The Changelog is the one source of the release notes.**
   - It is hand-written, at the repo root, for photographers, in Glossary terms. Changes they cannot notice, such as refactors, tests or CI, get no entry.
   - Each pull request with a user-visible change adds its line to `## Unreleased` in the same pull request. There is no CI gate; AGENTS.md and the pull request template ask for it.
   - Cutting a Release turns `## Unreleased` into `## X.Y.Z — YYYY-MM-DD`.
   - The Review UI shows the Changelog, so it keeps to a fixed shape: one level-2 section per version, newest first, `## Unreleased` first; optional level-3 subheadings; bullets; inline formatting limited to `**bold**` and `` `code` ``. A test fails when it drifts from that shape.
   - An entry that applies to only some platforms ends with a hidden marker naming them, any subset of `macos`, `linux` and `windows` separated by spaces, such as `<!-- linux windows -->`. An entry without a marker applies to every platform, so a marker naming all three is an error. The marker must be the last thing on the bullet, an unknown token is an error, and any other HTML stays forbidden. framewise strips the marker from the text it shows and filters by it; GitHub hides it in the Release notes, so cutting a Release needs no extra step. GitHub Releases published before the marker are not edited.
3. **The backend's project version is the only place the version lives.** The Review UI asks the backend for it.
4. **Releases are cut by hand with `scripts/release.sh`**, typically after an epic or a notable feature merges to `main`. There is no schedule.
5. **framewise stays on 0.x until it can keep four promises.** While on 0.x, a minor bump means new features or breaking changes, a patch bump means fixes only. 1.0.0 means:
   1. Upgrading never silently loses a photographer's Overrides or Session store.
   2. Rating write-back to Lightroom Classic is stable: the same Verdicts map to the same stars and color labels.
   3. The `framewise` command's subcommands and options are stable.
   4. Installing works on every platform the README claims to support.

   After 1.0.0, breaking any of them takes a major version.

## Considered Options

- **Release notes generated from pull request titles or commits.** Rejected: they describe the code, not what a photographer notices.
- **Installing from tags instead of `main`.** Rejected for now: it changes the install and update instructions for little gain while framewise is installed from a checkout. ADR-0009 makes framewise installable as one package, so a Release can carry the wheel instead.
- **A CI check that every pull request touches the Changelog.** Rejected: most pull requests are internal and would need a way to opt out.
- **1.0.0 as a feature milestone or a date.** Rejected: a version number is a promise about upgrades, so 1.0.0 is defined by the promises above.
