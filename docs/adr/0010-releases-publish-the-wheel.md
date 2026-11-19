# ADR-0010: Releases publish the wheel

**Status:** Accepted — 2026-11-19

## Context

ADR-0009 made framewise build into one wheel with the Review UI inside, but nothing published it, so a photographer still needed a checkout or a wheel someone else built. The name `framewise` on PyPI belongs to an unrelated project.

## Decision

1. **Cutting a Release (ADR-0007) publishes its wheel.** Creating the GitHub Release starts `.github/workflows/release.yml`, which builds the wheel from the tag, checks that the tag matches the version and that the wheel carries the Review UI and the Changelog, and runs it in a clean container. It then attaches the wheel to the GitHub Release, uploads the same file to PyPI, and runs the version installed from PyPI in a clean container.
2. **On PyPI framewise is `framewise-cull`.** Only the distribution name changes: the command and the Python package stay `framewise`, so a photographer runs `uvx --python 3.13 --from framewise-cull framewise review`.
3. **PyPI uploads use trusted publishing** from the `pypi` environment, so the repo holds no PyPI token.
4. **Photographers install and update from PyPI;** the checkout is the contributor path. This replaces ADR-0007's "Photographers keep installing and updating from `main`".
5. **Running the Release workflow by hand is its dry run.** It builds and tests the wheel from a branch or tag and says what a Release would publish, without publishing. `scripts/release.sh --dry-run` names the wheel and where it would go.

## Considered Options

- **Another command name, so that `uvx framewise-cull` works without `--from`.** Rejected: the `framewise` command is one of the 1.0.0 promises (ADR-0007), and a second name for it would be one more to keep.
- **GitHub Releases only.** Rejected: installing from PyPI gives photographers a short command and `@latest` to update.
- **A PyPI API token as a repository secret.** Rejected: a long-lived secret that trusted publishing makes unnecessary.

## Consequences

- Setting up publishing is a one-time manual step on PyPI and GitHub, listed in the header of `.github/workflows/release.yml`.
- The Release workflow runs from the tagged commit, so changes to it take effect from the next Release on.
- A Release whose PyPI upload fails still has its GitHub Release and wheel; re-running the failed jobs publishes it.
