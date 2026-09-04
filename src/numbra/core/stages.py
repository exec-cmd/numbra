from __future__ import annotations

from .models import StageKind


def allocate_stage_kinds(stages: int) -> tuple[StageKind, ...]:
    if stages < 1:
        raise ValueError("stages must be at least one")
    cycle = (StageKind.FAST, StageKind.NORMAL, StageKind.SLOW)
    return tuple(cycle[index % len(cycle)] for index in range(stages))
