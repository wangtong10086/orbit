"""Shared scoring policy for Layer 0."""

from __future__ import annotations

import math
from typing import Iterable


class ScoringPolicy:
    """Single scoring policy authority for active architecture paths."""

    @staticmethod
    def strict_geo_mean(scores: Iterable[float]) -> float:
        values = list(scores)
        if not values:
            return 0.0
        if any(score < 0 for score in values):
            raise ValueError("strict_geo_mean does not accept negative scores")
        if any(score == 0 for score in values):
            return 0.0
        return math.exp(sum(math.log(score) for score in values) / len(values))


def strict_geo_mean(scores: Iterable[float]) -> float:
    """Convenience wrapper around the single active scoring policy."""

    return ScoringPolicy.strict_geo_mean(scores)
