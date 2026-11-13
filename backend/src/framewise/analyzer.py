from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class FrameSignals:
    fingerprint: list[float]


class FrameAnalyzer(Protocol):
    def analyze(self, jpg_path: Path) -> FrameSignals: ...
