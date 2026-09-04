"""Domain services for numbra."""

from .generator import DifficultyProfile, ProblemGenerator
from .models import Difficulty, Operation, Problem, StageKind
from .stages import allocate_stage_kinds

__all__ = [
    "Challenge",
    "ChallengeOptions",
    "Difficulty",
    "DifficultyProfile",
    "Operation",
    "Problem",
    "ProblemGenerator",
    "StageKind",
    "Stats",
    "TrainingSession",
    "allocate_stage_kinds",
]


def __getattr__(name: str) -> object:
    if name in {"Challenge", "ChallengeOptions", "TrainingSession"}:
        from .challenge import Challenge, ChallengeOptions, TrainingSession

        return {
            "Challenge": Challenge,
            "ChallengeOptions": ChallengeOptions,
            "TrainingSession": TrainingSession,
        }[name]
    if name == "Stats":
        from .stats import Stats

        return Stats
    raise AttributeError(name)
