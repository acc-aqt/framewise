"""Fits the Score weights to the photographer's Reference ratings.

Within a Group, a Frame rated higher is one the photographer preferred. A pairwise logistic
(Bradley-Terry) model on the differences of the Score components, with no intercept and
non-negative weights, finds the weights that best explain those preferences.
"""

import math

from framewise.judge import WEIGHTS, Scores

COMPONENTS = tuple(WEIGHTS)
# A light ridge penalty keeps the weights finite when the preferences are perfectly separable.
RIDGE = 1.0
MAX_SWEEPS = 500
CONVERGED_BELOW = 1e-7

Pair = tuple[Scores, Scores]
"""Two Frames' Scores, the preferred Frame first."""


def fit_weights(pairs: list[Pair]) -> dict[str, float] | None:
    """The weights that best explain why the first Frame of each pair was preferred, on the
    scale of today's `WEIGHTS`, or None when the pairs favor no component."""
    differences = [_differences(preferred, other) for preferred, other in pairs]
    raw = _fit(differences)
    total = sum(raw)
    if total == 0:
        return None
    scale = sum(WEIGHTS.values()) / total
    return {name: weight * scale for name, weight in zip(COMPONENTS, raw, strict=True)}


def _differences(preferred: Scores, other: Scores) -> list[float]:
    """Each component's lead of the preferred Frame, or 0 when either Frame lacks it."""
    differences = []
    for name in COMPONENTS:
        mine, theirs = getattr(preferred, name), getattr(other, name)
        differences.append(0.0 if mine is None or theirs is None else mine - theirs)
    return differences


def _fit(differences: list[list[float]]) -> list[float]:
    """Minimizes the logistic loss plus the ridge penalty by cyclic coordinate descent, taking
    one Newton step per weight and clipping it at zero."""
    weights = [0.0] * len(COMPONENTS)
    margins = [0.0] * len(differences)
    for _ in range(MAX_SWEEPS):
        largest_step = 0.0
        for j in range(len(COMPONENTS)):
            gradient, curvature = RIDGE * weights[j], RIDGE
            for row, margin in zip(differences, margins, strict=True):
                chance = _sigmoid(margin)
                gradient -= (1 - chance) * row[j]
                curvature += chance * (1 - chance) * row[j] ** 2
            step = max(0.0, weights[j] - gradient / curvature) - weights[j]
            if step:
                weights[j] += step
                margins = [m + step * row[j] for m, row in zip(margins, differences, strict=True)]
            largest_step = max(largest_step, abs(step))
        if largest_step < CONVERGED_BELOW:
            break
    return weights


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exp = math.exp(value)
    return exp / (1 + exp)
