# ADR-0007: Windows as a native platform

**Status:** Accepted — 2026-11-18

## Context

framewise ran on macOS and Linux. Most Lightroom Classic photographers work on Windows, so they could not cull a Session with it. Windows support had to cover the parts of framewise that touch the operating system: the Session store location, keeping the machine awake, background priority, the folder dialog, Trash, ExifTool, and reading Lightroom's color label set. The maintainer has no permanent Windows machine, only one borrowed from time to time.

## Decision

1. **framewise runs natively on Windows,** installed with `scripts/setup.ps1` and run from a clone with uv, like on the other platforms.
2. **Windows uses the portable Providers only:** DINOv2-small for the fingerprint and MediaPipe for face detection and eye state, the same as Linux. Windows has no `face-quality` or `aesthetics` Provider yet.
3. **Only Windows x64 is supported.** Windows on ARM is neither tested in CI nor checked by hand.
4. **Each operating-system seam gets a Windows branch:**
   - the Session store under `%LOCALAPPDATA%\framewise`, found by the case-normalized folder path, since Windows paths ignore case
   - `SetThreadExecutionState` to keep the machine awake, and Windows' background thread mode for `--background`
   - Tk's folder dialog, which is the Explorer one
   - Lightroom Classic's color label set read from its `.agprefs` preferences, a Lua table in `%APPDATA%`
5. **Windows is listed as preview** until a scripted acceptance run on a real Windows machine with Lightroom Classic passes. CI tests everything else on `windows-latest`.

## Considered Options

- **Running the Linux build under WSL2.** Rejected: Session folders under `/mnt/c` scan slowly, and Trash, the folder dialog and Lightroom's preferences sit on the other side of the VM.
- **Windows-native Providers** (Windows ML or DirectML) for face quality and aesthetics. Deferred: the portable Providers make framewise useful on Windows first, and ADR-0005 lets such Providers be added later.
- **Making `setup.sh` run under Git Bash.** Rejected: it would make Git Bash a prerequisite, and PowerShell is what Windows users already have.
- **Holding the epic back until the acceptance run.** Rejected: with borrowed hardware the branch would drift from main. Listing Windows as preview is honest while CI covers all but the dialog and the Lightroom import.

## Consequences

- `framewise-benchmark` does not run on Windows. It is a calibration tool for the maintainer, whose Lightroom catalog is on macOS.
- The `.agprefs` reader was built from the known format before a real preferences file had been checked. The first borrowed-machine session captures one as a test fixture.
- Paths longer than Windows' 260-character limit are not supported.
