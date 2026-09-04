from __future__ import annotations

from dataclasses import dataclass, field

from ..core.models import Difficulty, Operation, StageKind


@dataclass(frozen=True, slots=True)
class DifficultyConfig:
    min_value: int
    max_value: int
    min_terms: int
    max_terms: int


@dataclass(frozen=True, slots=True)
class OperationTimingConfig:
    enabled: bool = True
    bonus_seconds: dict[Operation, float] = field(default_factory=dict)

    def bonus_for(self, operations: tuple[Operation, ...]) -> float:
        if not self.enabled:
            return 0.0
        return sum(self.bonus_seconds.get(operation, 0.0) for operation in operations)


def _default_stage_limits() -> dict[StageKind, float]:
    return {StageKind.FAST: 5.0, StageKind.NORMAL: 10.0, StageKind.SLOW: 15.0}


def _default_profiles() -> dict[Difficulty, DifficultyConfig]:
    return {
        Difficulty.VERY_EASY: DifficultyConfig(1, 10, 2, 2),
        Difficulty.EASY: DifficultyConfig(1, 20, 2, 2),
        Difficulty.NORMAL: DifficultyConfig(2, 50, 2, 3),
        Difficulty.HARD: DifficultyConfig(5, 150, 2, 3),
        Difficulty.VERY_HARD: DifficultyConfig(10, 999, 3, 4),
    }


@dataclass(frozen=True, slots=True)
class ChallengeConfig:
    duration_minutes: int = 6
    difficulty: Difficulty = Difficulty.NORMAL
    stages: int = 3
    seed: int | None = None
    operations: tuple[Operation, ...] = tuple(Operation)
    stage_limits: dict[StageKind, float] = field(default_factory=_default_stage_limits)
    profiles: dict[Difficulty, DifficultyConfig] = field(default_factory=_default_profiles)
    operation_timing: OperationTimingConfig = field(
        default_factory=lambda: OperationTimingConfig(
            True,
            {
                Operation.ADD: 0.0,
                Operation.SUBTRACT: 0.0,
                Operation.MULTIPLY: 1.0,
                Operation.DIVIDE: 2.0,
            },
        )
    )


@dataclass(frozen=True, slots=True)
class Settings:
    challenge: ChallengeConfig
    templates: tuple[str, ...]
    styles: dict[str, str]
