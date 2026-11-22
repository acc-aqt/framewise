import math
import random

import pytest

from framewise.judge import Scores
from framewise.weight_fit import fit_weights

KNOWN_WEIGHTS = {
    "sharpness": 0.5,
    "steadiness": 0.1,
    "exposure": 0.2,
    "aesthetics": 0.3,
    "face_quality": 0.0,
    "expression": 0.2,
}


def random_scores(rng: random.Random) -> Scores:
    return Scores(
        sharpness=rng.random(),
        steadiness=rng.random(),
        exposure=rng.random(),
        aesthetics=rng.random() if rng.random() < 0.8 else None,
        face_quality=rng.random() if rng.random() < 0.5 else None,
        expression=rng.random() if rng.random() < 0.5 else None,
        camera_rating=0,
        total=0,
    )


def preference(first: Scores, second: Scores) -> float:
    """How strongly the known weights prefer `first`, counting only components both Frames have."""
    return sum(
        weight * (getattr(first, name) - getattr(second, name))
        for name, weight in KNOWN_WEIGHTS.items()
        if getattr(first, name) is not None and getattr(second, name) is not None
    )


def synthetic_pairs(count: int, sharpness_of_choice: float, seed: int = 7):
    """Pairs of (preferred, other) Scores, the preferred one drawn by a logistic model of the
    known weights."""
    rng = random.Random(seed)
    pairs = []
    for _ in range(count):
        first, second = random_scores(rng), random_scores(rng)
        chance = 1 / (1 + math.exp(-sharpness_of_choice * preference(first, second)))
        pairs.append((first, second) if rng.random() < chance else (second, first))
    return pairs


def test_the_fit_recovers_the_weights_that_made_the_choices():
    fitted = fit_weights(synthetic_pairs(3000, sharpness_of_choice=10))

    assert fitted == pytest.approx(KNOWN_WEIGHTS, abs=0.06)
