from __future__ import annotations

from .models import Difficulty, StageKind

_WEIGHTS = {
    Difficulty.VERY_EASY: {StageKind.FAST: 0, StageKind.NORMAL: 0, StageKind.SLOW: 3},
    Difficulty.EASY: {StageKind.FAST: 0, StageKind.NORMAL: 1, StageKind.SLOW: 2},
    Difficulty.NORMAL: {StageKind.FAST: 1, StageKind.NORMAL: 1, StageKind.SLOW: 1},
    Difficulty.HARD: {StageKind.FAST: 2, StageKind.NORMAL: 1, StageKind.SLOW: 0},
    Difficulty.VERY_HARD: {StageKind.FAST: 3, StageKind.NORMAL: 0, StageKind.SLOW: 0},
}


def allocate_stage_kinds(difficulty: Difficulty, stages: int) -> tuple[StageKind, ...]:
    if stages < 1:
        raise ValueError("stages must be at least one")
    weights = _WEIGHTS[difficulty]
    total = sum(weights.values())
    quotas = {kind: stages * weight / total for kind, weight in weights.items()}
    counts = {kind: int(quota) for kind, quota in quotas.items()}
    remainder = stages - sum(counts.values())
    order = sorted(
        quotas, key=lambda kind: (-(quotas[kind] - counts[kind]), list(StageKind).index(kind))
    )
    for kind in order[:remainder]:
        counts[kind] += 1
    return tuple(kind for kind in StageKind for _ in range(counts[kind]))
