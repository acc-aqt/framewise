import math
from collections.abc import Iterator, Mapping
from datetime import datetime, timedelta

from framewise.analyzer import SimilarityThresholds
from framewise.store import AnalyzedFrame

BURST_GAP = timedelta(seconds=2)
NEAR_DUPLICATE_WINDOW = timedelta(minutes=5)


def group_frames(
    frames: list[AnalyzedFrame],
    similarity: SimilarityThresholds,
    group_overrides: Mapping[str, str] | None = None,
) -> list[list[AnalyzedFrame]]:
    """Groups Frames in capture order, by the similarity of their fingerprints. `group_overrides`
    holds the Groups the photographer fixed, as a Group key by JPG path: Frames sharing a key
    form one Group, and only the other Frames are grouped by similarity."""
    group_overrides = group_overrides or {}
    fixed: dict[str, list[AnalyzedFrame]] = {}
    free: list[AnalyzedFrame] = []
    for frame in frames:
        key = group_overrides.get(frame.frame.jpg_path)
        if key is None:
            free.append(frame)
        else:
            fixed.setdefault(key, []).append(frame)
    fixed_groups = [sorted(group, key=_capture_order) for group in fixed.values()]
    groups = _similar_groups(free, similarity) + fixed_groups
    return sorted(groups, key=lambda group: _capture_order(group[0]))


def _similar_groups(
    frames: list[AnalyzedFrame], thresholds: SimilarityThresholds
) -> list[list[AnalyzedFrame]]:
    ordered = sorted(frames, key=_capture_order)
    unit_fingerprints = [_unit(frame.signals.fingerprint) for frame in ordered]
    parents = list(range(len(ordered)))
    for first, second in _candidate_pairs(ordered):
        similarity = _dot(unit_fingerprints[first], unit_fingerprints[second])
        if _belong_together(ordered[first], ordered[second], similarity, thresholds):
            parents[_root(parents, second)] = _root(parents, first)

    groups: dict[int, list[AnalyzedFrame]] = {}
    for index, frame in enumerate(ordered):
        groups.setdefault(_root(parents, index), []).append(frame)
    return list(groups.values())


def _belong_together(
    first: AnalyzedFrame,
    second: AnalyzedFrame,
    similarity: float,
    thresholds: SimilarityThresholds,
) -> bool:
    gap = _capture_gap(first, second)
    if gap is not None and gap <= BURST_GAP:
        return similarity >= thresholds.burst
    within_window = gap is None or gap <= NEAR_DUPLICATE_WINDOW
    return within_window and similarity >= thresholds.near_duplicate


def _candidate_pairs(ordered: list[AnalyzedFrame]) -> Iterator[tuple[int, int]]:
    """Pairs close enough in time to group. Frames without a capture time pair only with each
    other, so they can't bridge Groups captured far apart."""
    timed = [index for index, frame in enumerate(ordered) if frame.captured_at is not None]
    untimed = [index for index, frame in enumerate(ordered) if frame.captured_at is None]
    for position, first in enumerate(timed):
        for second in timed[position + 1 :]:
            if _capture_gap(ordered[first], ordered[second]) > NEAR_DUPLICATE_WINDOW:
                break
            yield first, second
    for position, first in enumerate(untimed):
        for second in untimed[position + 1 :]:
            yield first, second


def _capture_gap(first: AnalyzedFrame, second: AnalyzedFrame) -> timedelta | None:
    if first.captured_at is None or second.captured_at is None:
        return None
    return abs(second.captured_at - first.captured_at)


def _capture_order(analyzed: AnalyzedFrame) -> tuple[bool, datetime, str]:
    return (
        analyzed.captured_at is None,
        analyzed.captured_at or datetime.min,
        analyzed.frame.jpg_path,
    )


def _root(parents: list[int], index: int) -> int:
    while parents[index] != index:
        parents[index] = parents[parents[index]]
        index = parents[index]
    return index


def _unit(vector: list[float]) -> list[float]:
    length = math.sqrt(_dot(vector, vector)) or 1.0
    return [value / length for value in vector]


def _dot(first: list[float], second: list[float]) -> float:
    return sum(a * b for a, b in zip(first, second, strict=True))
