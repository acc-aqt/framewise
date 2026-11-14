import json
import shutil
import subprocess
import threading
import weakref
from dataclasses import dataclass
from pathlib import Path

HOMEBREW_EXIFTOOL = "/opt/homebrew/bin/exiftool"
READY = "{ready}"


@dataclass(frozen=True)
class ExifToolResult:
    output: str
    errors: list[str]


class ExifTool:
    """One persistent `exiftool -stay_open` process that runs commands one batch at a time.
    It starts on the first command, so creating it touches nothing."""

    def __init__(self, executable: str | None = None):
        self._executable = executable or shutil.which("exiftool") or HOMEBREW_EXIFTOOL
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    def run(self, *args: str | Path) -> ExifToolResult:
        lines = [str(arg) for arg in args]
        if any("\n" in line for line in lines):
            raise ValueError("exiftool arguments cannot contain line breaks")
        with self._lock:
            process = self._started()
            assert process.stdin is not None
            process.stdin.write("\n".join([*lines, "-echo4", READY, "-execute", ""]))
            process.stdin.flush()
            output = _read_until_ready(process.stdout)
            errors = _read_until_ready(process.stderr)
        return ExifToolResult(
            output=output,
            errors=[line for line in errors.splitlines() if line.startswith("Error")],
        )

    def read_json(self, *args: str | Path) -> list[dict]:
        output = self.run("-json", *args).output
        return json.loads(output) if output.strip() else []

    def close(self) -> None:
        with self._lock:
            if self._process is not None:
                _stop(self._process)
                self._process = None

    def _started(self) -> subprocess.Popen[str]:
        if self._process is None:
            self._process = subprocess.Popen(
                [self._executable, "-stay_open", "True", "-@", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            weakref.finalize(self, _stop, self._process)
        return self._process


def _read_until_ready(stream) -> str:
    lines = []
    for line in stream:
        if line.rstrip("\n") == READY:
            break
        lines.append(line)
    return "".join(lines)


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        process.stdin.write("-stay_open\nFalse\n")
        process.stdin.flush()
        process.wait(timeout=5)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        process.kill()
