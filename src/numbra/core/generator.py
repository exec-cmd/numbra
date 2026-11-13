from __future__ import annotations

import random
from bisect import bisect_right
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Final

from .catalog import build_arithmetic, problem, topic_catalog
from .expressions import Expr, canonical_key, solution_steps, work_units
from .grouping import group_terms
from .missing import missing_number
from .models import BASIC_OPERATIONS, Difficulty, Operation, Problem, Topic
from .permutation import permute_operands
from .tricks import trick_catalog


class GenerationError(ValueError):
    """The selected profile has no exercises for a required family."""


@dataclass(frozen=True, slots=True)
class DifficultyProfile:
    min_value: int
    max_value: int
    min_terms: int = 2
    max_terms: int = 3
    max_result: int = 10_000
    term_weights: tuple[tuple[int, int], ...] = ()


# Candidates inspected per signature group when looking for unused operands.
CANDIDATE_WINDOW = 4
# Arithmetic sampling stops after two balanced, cap-safe alternatives.
ARITHMETIC_CANDIDATES = 2
# A large operand may appear this many times per session while alternatives exist.
OPERAND_REPEAT_CAP = 3
CONSTRUCTION_ATTEMPTS = 100

# Tricks keep their own result ladder: a profile's max_result would hide most of them.
TRICK_MAX_RESULT = {
    Difficulty.EASY: 400,
    Difficulty.NORMAL: 2_500,
    Difficulty.HARD: 10_000,
}

WORK_BANDS = {
    Difficulty.EASY: (1, 3),
    Difficulty.NORMAL: (2, 8),
    Difficulty.HARD: (4, 16),
}

TOPIC_WORK_BANDS = {
    Difficulty.EASY: (1, 2),
    Difficulty.NORMAL: (2, 5),
    Difficulty.HARD: (4, 9),
}

TRICK_WORK_BANDS = {
    Difficulty.EASY: (1, 2),
    Difficulty.NORMAL: (2, 5),
    Difficulty.HARD: (4, 9),
}

# Stage-sized bags keep term counts close to their weights within each stage.
LENGTH_BAG_SIZES = {
    Difficulty.NORMAL: 8,
    Difficulty.HARD: 8,
}
DEFAULT_LENGTH_BAG_SIZE: Final = 8


def canonical_problem_key(problem: Problem) -> tuple[object, ...]:
    if problem.tree is None and problem.family == "funbox":
        # Funbox texts are not parsed as arithmetic; their display text identifies them.
        return ("funbox", problem.expression)
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
        brackets: bool = True,
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
        self.operations = tuple(dict.fromkeys(Operation(op) for op in operations))
        self.profile = (
            replace(profile, min_terms=2) if self.operations == (Operation.DIVIDE,) else profile
        )
        basic = tuple(op for op in self.operations if op is not Operation.POWER)
        self._arithmetic_operations = basic + (
            (Operation.POWER,)
            if difficulty is None and basic and Operation.POWER in self.operations
            else ()
        )
        self.difficulty = difficulty
        self._length_bag_size = (
            LENGTH_BAG_SIZES.get(difficulty, DEFAULT_LENGTH_BAG_SIZE)
            if difficulty is not None
            else DEFAULT_LENGTH_BAG_SIZE
        )
        self.topics = tuple(dict.fromkeys(Topic(topic) for topic in topics))
        self._brackets = brackets
        self._random = random.Random(seed)
        self._length_random = random.Random(f"{seed}:length")
        self._forms = random.Random(f"{seed}:forms")
        self._grouping = random.Random(f"{seed}:grouping")
        self._seen: set[tuple[object, ...]] = set()
        self._last: tuple[object, ...] | None = None
        self.warnings: list[str] = []
        self._topic_counts: Counter[str] = Counter()
        self._operation_counts: Counter[Operation] = Counter()
        self._operand_counts: Counter[int] = Counter()
        self._strategy_counts: Counter[str] = Counter()
        self._cycle: deque[int] = deque()
        self._length_bag: deque[int] = deque()
        self._failed_lengths: set[int] = set()
        self._arithmetic_candidates: dict[tuple[object, ...], Problem] = {}
        if self._arithmetic_operations:
            self._refill_length_bag()
        self._groups: dict[str, list[tuple[tuple[Problem, ...], deque[Problem]]]] = defaultdict(
            list
        )
        for family, groups in _catalog_groups(profile, self.operations, difficulty, self.topics):
            for candidates in groups:
                shuffled = list(candidates)
                self._random.shuffle(shuffled)
                frozen = tuple(shuffled)
                self._groups[family].append((frozen, deque(frozen)))
        self._constructed = bool(self._arithmetic_operations)
        self._families = (("arithmetic",) if self._constructed else ()) + tuple(self._groups)
        self._levels = tuple(
            sorted(
                {
                    complexity_score(p) - 2
                    for groups in self._groups.values()
                    for pool, _ in groups
                    for p in pool
                }
            )
        )

    def _apply_forms(self, p: Problem) -> Problem:
        show = self._forms.random() < 1 / 6
        selector = self._forms.random()
        if p.tree is not None:
            tree = permute_operands(p.as_tree(), self._forms)
            p = replace(
                p,
                tree=tree,
                expression=tree.render(),
                solution_steps=solution_steps(tree),
            )
        p = self._apply_missing_number(p, show, selector)
        grouped = group_terms(p.expression, self._grouping)
        return replace(p, expression=grouped) if self._brackets else p

    def _next_level(self) -> int:
        """Spread work units evenly: each band level once per shuffled cycle."""
        if not self._cycle:
            levels = list(self._levels)
            self._random.shuffle(levels)
            self._cycle.extend(levels)
        return self._cycle.popleft()

    def _refill_length_bag(self) -> None:
        available = {
            length: weight
            for length, weight in _length_weights(self.profile).items()
            if weight > 0 and length not in self._failed_lengths
        }
        if available:
            lengths = tuple(available)
            total = sum(available.values())
            cumulative = []
            running = 0.0
            for length in lengths:
                running += self._length_bag_size * available[length] / total
                cumulative.append(running)
            offset = self._length_random.random()
            bag = [
                lengths[bisect_right(cumulative, offset + slot)]
                for slot in range(self._length_bag_size)
            ]
            self._length_random.shuffle(bag)
            self._length_bag.extend(bag)

    def _construct(self, complexity_range: tuple[int, int] | None = None) -> Problem:
        def rank(candidate: Problem) -> tuple[int, int, int, int]:
            selected = [
                self._operation_counts[op] + candidate.operations.count(op)
                for op in self._arithmetic_operations
            ]
            imbalance = max(selected, default=0) - min(selected, default=0)
            numbers = _large_numbers(candidate)
            reuse = sum(self._operand_counts[n] for n in numbers)
            overused = any(
                self._operand_counts[n] + numbers.count(n) > OPERAND_REPEAT_CAP for n in numbers
            )
            return max(0, imbalance - 2), int(overused), reuse, imbalance

        while True:
            if not self._length_bag:
                self._refill_length_bag()
                if not self._length_bag:
                    break
            terms = self._length_bag.popleft()
            candidates: list[Problem] = []
            candidate_keys: set[tuple[object, ...]] = set()
            preferred = 0
            operation_weights = {
                op: 1 / (1 + self._operation_counts[op]) for op in self._arithmetic_operations
            }
            for _ in range(CONSTRUCTION_ATTEMPTS):
                tree = build_arithmetic(
                    self._random,
                    terms,
                    self.profile.min_value,
                    self.profile.max_value,
                    self.profile.max_result,
                    self._arithmetic_operations,
                    operation_weights,
                    _dividend_limit(self.profile, self.difficulty),
                    max(
                        self.profile.min_value,
                        3 if self.difficulty in (Difficulty.NORMAL, Difficulty.HARD) else 2,
                    ),
                )
                if tree is None:
                    continue
                candidate = problem(tree)
                if not _allowed(candidate, self.difficulty):
                    continue
                if complexity_range is not None and not (
                    complexity_range[0] <= complexity_score(candidate) <= complexity_range[1]
                ):
                    continue
                key = canonical_problem_key(candidate)
                self._arithmetic_candidates[key] = candidate
                if key in candidate_keys:
                    continue
                candidate_keys.add(key)
                if key in self._seen:
                    continue
                candidates.append(candidate)
                candidate_rank = rank(candidate)
                if candidate_rank[0] == candidate_rank[1] == 0:
                    preferred += 1
                if preferred == ARITHMETIC_CANDIDATES:
                    break
            if not candidates:
                self._failed_lengths.add(terms)
                self._length_bag = deque(length for length in self._length_bag if length != terms)
                continue

            best = min(map(rank, candidates))
            candidate = self._random.choice([item for item in candidates if rank(item) == best])
            key = canonical_problem_key(candidate)
            self._seen.add(key)
            self._last = key
            self._operation_counts.update(candidate.operations)
            self._operand_counts.update(_large_numbers(candidate))
            self._topic_counts["arithmetic"] += 1
            return self._apply_forms(
                replace(candidate, solution_steps=solution_steps(candidate.as_tree()))
            )
        if self._arithmetic_candidates:
            warning = (
                "Selected settings require repeated arithmetic exercises; unique catalog exhausted."
            )
            if warning not in self.warnings:
                self.warnings.append(warning)
            different = [
                p
                for p in self._arithmetic_candidates.values()
                if canonical_problem_key(p) != self._last
            ]
            choices = different or list(self._arithmetic_candidates.values())
            best = min(map(rank, choices))
            candidate = self._random.choice([p for p in choices if rank(p) == best])
            self._last = canonical_problem_key(candidate)
            self._operation_counts.update(candidate.operations)
            self._operand_counts.update(_large_numbers(candidate))
            self._topic_counts["arithmetic"] += 1
            return self._apply_forms(
                replace(candidate, solution_steps=solution_steps(candidate.as_tree()))
            )
        raise GenerationError(
            "No arithmetic exercises satisfy operand, term, result and effort limits"
        )

    def generate(self, complexity_range: tuple[int, int] | None = None) -> Problem:
        if complexity_range is not None:
            if self._constructed:
                return self._construct(complexity_range)
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
            return self._apply_forms(replace(p, solution_steps=solution_steps(p.as_tree())))
        return self.generate_many(1)[0]

    def _take(self, family: str) -> Problem:
        if family == "arithmetic":
            return self._construct()
        groups = self._groups[family]
        tricks = family == Topic.TRICKS.value
        target = self._next_level()
        choices: list[tuple[tuple[int, ...], int, int, Problem]] = []
        for i, (_, queue) in enumerate(groups):
            while queue and canonical_problem_key(queue[0]) in self._seen:
                queue.popleft()
            window = 0
            for j, p in enumerate(queue):
                if window == CANDIDATE_WINDOW:
                    break
                if canonical_problem_key(p) in self._seen:
                    continue
                window += 1
                # A trick fixes its own operation, so it does not weigh on the balance.
                selected = [
                    self._operation_counts[op] + (0 if tricks else p.operations.count(op))
                    for op in self.operations
                ]
                imbalance = max(selected, default=0) - min(selected, default=0)
                numbers = _large_numbers(p)
                reuse = sum(self._operand_counts[n] for n in numbers)
                overused = any(
                    self._operand_counts[n] + numbers.count(n) > OPERAND_REPEAT_CAP for n in numbers
                )
                # Slack of 2 lets multi-step levels (e.g. "a - b - c") in; later picks rebalance.
                rank = (
                    max(0, imbalance - 2),
                    int(overused),
                    abs(complexity_score(p) - 2 - target),
                    self._strategy_counts[p.strategy] if tricks else 0,
                    reuse,
                    imbalance,
                )
                choices.append((rank, i, j, p))
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
        different = [c for c in choices if canonical_problem_key(c[3]) != self._last]
        choices = different or choices
        best = min(c[0] for c in choices)
        tied = [c for c in choices if c[0] == best]
        _, group_index, position, p = self._random.choice(tied)
        del self._groups[family][group_index][1][position]
        key = canonical_problem_key(p)
        self._seen.add(key)
        self._last = key
        if tricks:
            self._strategy_counts[p.strategy] += 1
        else:
            self._operation_counts.update(p.operations)
        self._operand_counts.update(_large_numbers(p))
        self._topic_counts.update({family: 1})
        return self._apply_forms(replace(p, solution_steps=solution_steps(p.as_tree())))

    def _apply_missing_number(self, p: Problem, show: bool, selector: float) -> Problem:
        result = (
            missing_number(p.as_tree(), random.Random(selector))
            if p.family not in {"tricks", "funbox"}
            else None
        )
        if show and result is not None:
            text, answer, steps = result
            return replace(p, expression=text, answer=answer, solution_steps=steps)
        return p

    def generate_many(self, count: int) -> tuple[Problem, ...]:
        if count < 0:
            raise ValueError("count must not be negative")
        problems = []
        advanced = [f for f in self._families if f != "arithmetic"]
        for _ in range(count):
            if "arithmetic" not in self._families:
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
        """Reset local operator balance and level cycle, counting a carried candidate."""
        self._operation_counts.clear()
        self._cycle.clear()
        self._failed_lengths.clear()
        self._length_bag.clear()
        self._refill_length_bag()
        if pending is not None and pending.family == "arithmetic":
            try:
                self._length_bag.remove(len(pending.operations) + 1)
            except ValueError:
                self._length_bag.pop()
        # Tricks stay outside operation balance, carried over or not (see _take).
        if pending is not None and pending.family != Topic.TRICKS.value:
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


def trick_levels() -> dict[str, tuple[Difficulty, ...]]:
    """Difficulty levels on which each trick has at least one problem."""
    levels: dict[str, list[Difficulty]] = {}
    for difficulty, limit in TRICK_MAX_RESULT.items():
        low, high = TRICK_WORK_BANDS[difficulty]
        found = {p.strategy for p in trick_catalog(limit) if low <= complexity_score(p) - 2 <= high}
        for strategy in found:
            levels.setdefault(strategy, []).append(difficulty)
    return {strategy: tuple(found) for strategy, found in levels.items()}


def _nodes(expr: Expr) -> tuple[Expr, ...]:
    return (expr, *(node for arg in expr.args for node in _nodes(arg)))


def _large_numbers(problem: Problem) -> tuple[int, ...]:
    """Operands above the multiplication table, whose repetition is noticeable."""
    return _tree_large_numbers(problem.as_tree())


@lru_cache(maxsize=65536)
def _tree_large_numbers(expr: Expr) -> tuple[int, ...]:
    return tuple(node.value for node in _nodes(expr) if node.kind == "number" and node.value > 12)


def _small_quotient(problem: Problem) -> bool:
    return any(node.kind == "/" and abs(node.evaluate()) < 3 for node in _nodes(problem.as_tree()))


def _round_product(problem: Problem) -> bool:
    tree = problem.as_tree()
    return (
        tree.kind == "*"
        and all(a.kind == "number" for a in tree.args)
        and all(a.value % 10 == 0 for a in tree.args)
    )


def _length_weights(profile: DifficultyProfile) -> dict[int, float]:
    lengths = range(profile.min_terms, profile.max_terms + 1)
    configured = dict(profile.term_weights)
    if any(length in configured for length in lengths):
        return {length: float(configured.get(length, 0)) for length in lengths}
    return {length: 2.0 ** -(length - profile.min_terms) for length in lengths}


def _dividend_limit(profile: DifficultyProfile, difficulty: Difficulty | None) -> int:
    return (
        profile.max_result
        if difficulty in (Difficulty.NORMAL, Difficulty.HARD)
        else profile.max_value
    )


def _allowed(problem: Problem, difficulty: Difficulty | None) -> bool:
    low, high = WORK_BANDS[difficulty] if difficulty is not None else (1, 10_000)
    if difficulty is Difficulty.HARD and problem.operations == (Operation.DIVIDE,):
        low = 3
    return (
        low <= complexity_score(problem) - 2 <= high
        and not (difficulty is not Difficulty.EASY and _round_product(problem))
        and not (difficulty in (Difficulty.NORMAL, Difficulty.HARD) and _small_quotient(problem))
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
    if Operation.POWER in operations:
        legacy = topic_catalog(
            Topic.POWER, profile.min_value, profile.max_value, profile.max_result, basic, True
        )
        if difficulty is None:
            if not basic:
                pools[Topic.POWER.value] = tuple(p for p in legacy if p.as_tree().kind == "^")
        elif Topic.POWER not in topics:
            topics += (Topic.POWER,)
    for topic in topics:
        if topic is Topic.TRICKS:
            limit = TRICK_MAX_RESULT[difficulty] if difficulty is not None else profile.max_result
            pools[topic.value] = trick_catalog(limit)
            continue
        others = (
            tuple(t for t in topics if t is not topic and t is not Topic.TRICKS)
            if difficulty is Difficulty.HARD
            else ()
        )
        pools[topic.value] = topic_catalog(
            topic,
            profile.min_value,
            profile.max_value,
            profile.max_result,
            basic or BASIC_OPERATIONS,
            Topic.POWER in topics,
            others,
        )
    grouped: list[tuple[str, tuple[tuple[Problem, ...], ...]]] = []
    for family, pool in pools.items():
        low, high = (
            (
                TRICK_WORK_BANDS[difficulty]
                if family == Topic.TRICKS.value
                else TOPIC_WORK_BANDS[difficulty]
            )
            if difficulty is not None
            else (1, 10_000)
        )
        signatures: dict[tuple[object, ...], list[Problem]] = defaultdict(list)
        seen = set()
        for p in pool:
            units = complexity_score(p) - 2
            if not low <= units <= high:
                continue
            if difficulty is not Difficulty.EASY and difficulty is not None and _round_product(p):
                continue
            if difficulty in (Difficulty.NORMAL, Difficulty.HARD) and _small_quotient(p):
                continue
            key = canonical_problem_key(p)
            if key in seen:
                continue
            seen.add(key)
            operation_counts = Counter(p.operations)
            # Tricks rotate by strategy; one large trick would otherwise dominate a session.
            signature = (
                (p.strategy, units)
                if family == Topic.TRICKS.value
                else (tuple(operation_counts[op] for op in Operation), units)
            )
            signatures[signature].append(p)
        if not signatures:
            raise GenerationError(
                f"No {family} exercises satisfy operand, term, result and effort limits"
            )
        grouped.append((family, tuple(tuple(candidates) for candidates in signatures.values())))
    return tuple(grouped)
