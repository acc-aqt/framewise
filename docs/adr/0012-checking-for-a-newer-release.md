# ADR-0012: framewise checks `main`'s Changelog for a newer Release

**Status:** Accepted — 2026-11-25. Builds on ADR-0007's Changelog and its platform marker.

## Context

A photographer learns about a newer Release only by checking GitHub or PyPI themselves. The Review UI shows the running version and the Changelog its wheel carries, nothing newer. Until now framewise made no network call of its own: it downloads models only on first use of a portable Provider or when asked to (`framewise models download`), and "no photo leaves the machine" is a promise in the README. A check for a newer Release is a new kind of call, so what it sends and how to turn it off has to be decided and stated.

The Changelog mixes entries for macOS, Linux and Windows, so "a newer Release exists" is not the same as "a newer Release brings this photographer something".

## Decision

1. **The update check is framewise's one unprompted network call.** When `framewise review` starts, it starts on a background thread, so it never delays start-up or the Review UI. It has a 5-second timeout. Any failure (offline, timeout, a response other than 200, a Changelog out of shape) means "no update" and is not reported to the photographer.
2. **It sends nothing about the photographer.** It is a plain GET of a public file, the raw `CHANGELOG.md` on `main` from `raw.githubusercontent.com`, with the headers `Host`, `User-Agent: framewise`, `Accept-Encoding: identity` and `Connection: close`: no version, platform, identifier, Session or Frame. The User-Agent is fixed, because Python's default one names the Python version. GitHub sees the request's IP address, as for any download.
3. **`main`'s Changelog is the source of truth for the newest Release.** The newest Release is its first `## X.Y.Z — YYYY-MM-DD` section, parsed with the same parser and shape rules as the installed Changelog (ADR-0007). It is one request, with no PyPI or GitHub API call. Pre-releases are not considered: the Changelog's headings are plain `X.Y.Z`.
4. **At most once a day.** The fetched text and the time it was fetched are kept in `update-check.json` in the data directory. A copy younger than 24 hours is used without fetching. A failed fetch keeps nothing, so the next start tries again.
5. **An update is reported only when it brings the photographer something.** The newest Release must be strictly greater than the running version, compared by semver, and at least one Release newer than the running one must have an entry for the photographer's platform, by the Changelog's platform marker (ADR-0007). The Review UI gets every newer Release, newest first, filtered to the platform.
6. **The update command follows the install.** A wheel, which carries its own Changelog, gets the `uvx` command with `framewise-cull@latest` on macOS or `"framewise-cull[portable]@latest"` on Linux and Windows. A checkout, whose Changelog sits at the root of the git clone, gets `git pull` followed by the platform's setup script.
7. **It can be turned off**, with `check_for_updates = false` at the top level of `config.toml`, or `FRAMEWISE_NO_UPDATE_CHECK=1` in the environment. When off, nothing is fetched and no update is reported. A `config.toml` that is not valid TOML counts as off, since it cannot say whether the photographer turned the check off; `framewise review` already stops on it with the error from reading the Providers and RAW-only settings.

## Considered Options

- **PyPI's JSON API or the GitHub Releases API.** Rejected: a second source to keep in step with the Changelog, and the notice needs the Changelog's entries anyway. Known gap of reading `main`: a Release heading reaches `main` a few minutes before its wheel reaches PyPI, so a photographer may briefly be told about a version uvx cannot install yet.
- **Checking on every start.** Rejected: restarting `framewise review` repeatedly would hit the network each time for no new information.
- **Off by default.** Rejected: photographers who never read the README would never learn about updates. The check sends nothing about them, and turning it off is one line.
- **Telling the photographer when the check fails.** Rejected: an offline machine is normal for framewise, and the notice is a convenience.

## Consequences

- Because the notice reads `main`'s Changelog, platform markers added there apply to every photographer running a version with the update check, however old the Changelog in their wheel.
- Releases older than the update check carry none, so photographers on 0.2.0 or earlier learn about it only by updating once by hand.
- A Changelog on `main` out of shape silences the notice for everyone until it is fixed; the shape test in CI keeps that from happening.
