# ADR-0009: framewise installs as one package

**Status:** Accepted — 2026-11-19

## Context

framewise was installed from a clone with `scripts/setup.sh` or `scripts/setup.ps1`, which needs git, Node.js and uv, and builds the Review UI on the photographer's machine. A photographer who only wants to cull a Session has no use for any of that. Rating write-back and `framewise reset` also failed late, with a traceback, when ExifTool was missing.

## Decision

1. **framewise builds into one Python wheel with the Review UI inside.** Building the wheel builds the Review UI and puts it, with the Changelog for **What's new**, in the package. Running it needs uv and ExifTool, not git or Node.js: `uvx --from <wheel> framewise review`.
2. **The build backend is hatchling,** because its build hook can run the Review UI build. `uv_build` cannot run build steps.
3. **A checkout keeps working as before.** Editable installs (`uv sync`) skip the Review UI build, and framewise serves the checkout's build and Changelog when the package carries none. `scripts/setup.sh` and `scripts/setup.ps1` stay the contributor path.
4. **ExifTool is required.** `framewise review` and `framewise reset` stop at start-up with one error that names the install command for the platform.
5. **Providers stay as in ADR-0005 and ADR-0008:** Apple Vision on macOS, and the `portable` extra elsewhere.
6. **CI builds the wheel and runs it with `uvx` in a clean Debian container** with only ExifTool installed, checking that the Review UI, the Session, the Changelog and the analysis of a Frame work.

## Considered Options

- **A script that builds the Review UI into the source tree before `uv build`.** Rejected: plain `uv build` would then make a wheel without the Review UI.
- **Publishing to PyPI now.** Deferred: the wheel comes first. Where photographers download it from is a follow-up.
- **Keeping ExifTool optional and failing only at Rating write-back.** Rejected: the failure came late and as a traceback, and write-back is the point of a review.

## Consequences

- Nothing publishes the wheel yet, so photographers still build it from a checkout or receive one.
- On Linux, MediaPipe's face checks need the OpenGL, EGL and OpenGL ES libraries, which `scripts/setup.sh` installs and a machine with only ExifTool lacks. The CI smoke test checks that a Frame is still analyzed without them, but not that its faces are checked.
- The Review UI build runs inside the wheel build, so building a wheel needs Node.js.
