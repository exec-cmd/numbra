from __future__ import annotations

import random
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, replace
from functools import lru_cache

from .catalog import arithmetic_catalog, topic_catalog
from .expressions import canonical_key, solution_steps, work_units
from .models import BASIC_OPERATIONS, Difficulty, Operation, Problem, Topic


class GenerationError(ValueError):
    """The selected profile has no exercises for a required family."""


@dataclass(frozen=True, slots=True)
class DifficultyProfile:
    min_value: int
    max_value: int
    min_terms: int = 2
    max_terms: int = 2
    max_result: int = 10_000
    term_weights: tuple[tuple[int, int], ...] = ()


WORK_BANDS = {
    Difficulty.EASY: (1, 2),
    Difficulty.NORMAL: (2, 5),
    Difficulty.HARD: (4, 9),
}


def canonical_problem_key(problem: Problem) -> tuple[object, ...]:
    return canonical_key(problem.as_tree())


def complexity_score(problem: Problem) -> int:
    """A transparent effort heuristic; not an empirical ability measurement."""
    return 2 + max(
        1, problem.work_units if problem.work_units is not None else work_units(problem.as_tree())
    )


class ProblemGenerator:
    def __init__(
        self,
        profile: DifficultyProfile,
        operations: tuple[Operation, ...],
        seed: int,
        *,
        difficulty: Difficulty | None = None,
        topics: tuple[Topic, ...] = (),
    ) -> None:
        if not operations and not topics:
            raise ValueError("at least one operation or topic is required")
        if (
            profile.min_value < 0
            or profile.max_value < max(1, profile.min_value)
            or profile.max_result < 1
        ):
            raise ValueError("invalid difficulty range")
        if profile.min_terms < 2 or profile.max_terms < profile.min_terms:
            raise ValueError("invalid term range")
        if any(t < 2 or w <= 0 for t, w in profile.term_weights):
            raise ValueError("invalid term weights")
        self.profile = profile
        self.operations = tuple(dict.fromkeys(Operation(op) for op in operations))
        self.topics = tuple(dict.fromkeys(Topic(topic) for topic in topics))
        self._random = random.Random(seed)
        self._seen: set[tuple[object, ...]] = set()
        self._last: tuple[object, ...] | None = None
        self.warnings: list[str] = []
        self._topic_counts: Counter[str] = Counter()
        self._operation_counts: Counter[Operation] = Counter()
        self._groups: dict[str, list[tuple[tuple[Problem, ...], deque[Problem]]]] = defaultdict(
            list
        )
        low, high = WORK_BANDS[difficulty] if difficulty is not None else (1, 10_000)
        self._target_work = (low + high) / 2
        for family, groups in _catalog_groups(profile, self.operations, difficulty, self.topics):
            for candidates in groups:
                shuffled = list(candidates)
                self._random.shuffle(shuffled)
                frozen = tuple(shuffled)
                self._groups[family].append((frozen, deque(frozen)))
        self._families = tuple(self._groups)

    def generate(self, complexity_range: tuple[int, int] | None = None) -> Problem:
        if complexity_range is not None:
            possible = [
                p
                for groups in self._groups.values()
                for pool, _ in groups
                for p in pool
                if complexity_range[0] <= complexity_score(p) <= complexity_range[1]
                and canonical_problem_key(p) not in self._seen
            ]
            if not possible:
                raise GenerationError("No new exercise satisfies the requested complexity range")
            p = self._random.choice(possible)
            self._seen.add(canonical_problem_key(p))
            return replace(p, solution_steps=solution_steps(p.as_tree()))
        return self.generate_many(1)[0]

    def _take(self, family: str) -> Problem:
        groups = self._groups[family]
        choices: list[tuple[float, int, Problem]] = []
        for i, (_, queue) in enumerate(groups):
            while queue and canonical_problem_key(queue[0]) in self._seen:
                queue.popleft()
            if queue:
                p = queue[0]
                counts = self._operation_counts + Counter(p.operations)
                selected = [counts[op] for op in self.operations]
                imbalance = max(selected, default=0) - min(selected, default=0)
                score = imbalance * 100 + abs(complexity_score(p) - 2 - self._target_work)
                choices.append((score, i, p))
        if not choices:
            warning = (
                f"Selected settings require repeated {family} exercises; unique catalog exhausted."
            )
            if warning not in self.warnings:
                self.warnings.append(warning)
            # Complete shuffled cycles within this family, preserving other families' uniqueness.
            family_keys = {canonical_problem_key(p) for pool, _ in groups for p in pool}
            self._seen.difference_update(family_keys)
            for pool, queue in groups:
                cycle = list(pool)
                self._random.shuffle(cycle)
                if len(cycle) > 1 and canonical_problem_key(cycle[0]) == self._last:
                    cycle.append(cycle.pop(0))
                queue.extend(cycle)
            return self._take(family)
        different = [c for c in choices if canonical_problem_key(c[2]) != self._last]
        choices = different or choices
        best = min(c[0] for c in choices)
        tied = [c for c in choices if c[0] == best]
        _, group_index, p = self._random.choice(tied)
        self._groups[family][group_index][1].popleft()
        key = canonical_problem_key(p)
        self._seen.add(key)
        self._last = key
        self._operation_counts.update(p.operations)
        self._topic_counts.update({family: 1})
        return replace(p, solution_steps=solution_steps(p.as_tree()))

    def generate_many(self, count: int) -> tuple[Problem, ...]:
        if count < 0:
            raise ValueError("count must not be negative")
        problems = []
        advanced = [f for f in self._families if f != "arithmetic"]
        for _ in range(count):
            if "arithmetic" not in self._groups:
                family = min(advanced, key=lambda f: self._topic_counts[f])
            elif not advanced or self._topic_counts["arithmetic"] <= sum(
                self._topic_counts[f] for f in advanced
            ):
                family = "arithmetic"
            else:
                family = min(advanced, key=lambda f: self._topic_counts[f])
            problems.append(self._take(family))
        return tuple(problems)

    def start_stage(self, pending: Problem | None = None) -> None:
        """Reset local operator balance, counting a carried unshown candidate."""
        self._operation_counts.clear()
        if pending is not None:
            self._operation_counts.update(pending.operations)

    def generate_progressive_batches(
        self, counts: tuple[int, ...]
    ) -> tuple[tuple[Problem, ...], ...]:
        """Compatibility name: stages now have comparable effort, not a global sort."""
        if any(count < 0 for count in counts):
            raise ValueError("counts must not contain negative values")
        result = []
        for count in counts:
            self.start_stage()
            result.append(self.generate_many(count))
        return tuple(result)


def _round_product(problem: Problem) -> bool:
    tree = problem.as_tree()
    return (
        tree.kind == "*"
        and all(a.kind == "number" for a in tree.args)
        and all(a.value % 10 == 0 for a in tree.args)
    )


@lru_cache(maxsize=64)
def _catalog_groups(
    profile: DifficultyProfile,
    operations: tuple[Operation, ...],
    difficulty: Difficulty | None,
    topics: tuple[Topic, ...],
) -> tuple[tuple[str, tuple[tuple[Problem, ...], ...]], ...]:
    basic = tuple(op for op in operations if op is not Operation.POWER)
    pools: dict[str, tuple[Problem, ...]] = {}
    if basic:
        pools["arithmetic"] = arithmetic_catalog(
            profile.min_value,
            profile.max_value,
            profile.min_terms,
            profile.max_terms,
            profile.max_result,
            basic,
        )
    if Operation.POWER in operations:
        legacy = topic_catalog(
            Topic.POWER, profile.min_value, profile.max_value, profile.max_result, basic, True
        )
        if difficulty is None:
            # Legacy direct-generator calls balance ^ alongside ordinary operators.
            pools["arithmetic"] = pools.get("arithmetic", ()) + tuple(
                p for p in legacy if p.as_tree().kind == "^"
            )
        elif Topic.POWER not in topics:
            topics += (Topic.POWER,)
    for topic in topics:
        others = tuple(t for t in topics if t is not topic) if difficulty is Difficulty.HARD else ()
        pools[topic.value] = topic_catalog(
            topic,
            profile.min_value,
            profile.max_value,
            profile.max_result,
            basic or BASIC_OPERATIONS,
            Topic.POWER in topics,
            others,
        )
    low, high = WORK_BANDS[difficulty] if difficulty is not None else (1, 10_000)
    grouped: list[tuple[str, tuple[tuple[Problem, ...], ...]]] = []
    for family, pool in pools.items():
        signatures: dict[tuple[object, ...], list[Problem]] = defaultdict(list)
        seen = set()
        for p in pool:
            units = complexity_score(p) - 2
            if not low <= units <= high:
                continue
            if difficulty is not Difficulty.EASY and difficulty is not None and _round_product(p):
                continue
            key = canonical_problem_key(p)
            if key in seen:
                continue
            seen.add(key)
            operation_counts = Counter(p.operations)
            signature = (tuple(operation_counts[op] for op in Operation), units)
            signatures[signature].append(p)
        if not signatures:
            raise GenerationError(
                f"No {family} exercises satisfy operand, term, result and effort limits"
            )
        grouped.append((family, tuple(tuple(candidates) for candidates in signatures.values())))
    return tuple(grouped)
