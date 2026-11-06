# Generation internals

Read before changing `core/generator.py`, `core/catalog.py`, `core/tricks.py`, or `core/expressions.py`. Product rules (uniqueness, balance, bands, caps) live in `AGENTS.md`; this file records how the code meets them.

## Pick order

`ProblemGenerator._take(family)` builds a candidate window per signature group (`CANDIDATE_WINDOW` unseen problems each) and picks the lowest rank tuple, ties broken by the seeded RNG. Rank, in priority order:

1. operation imbalance beyond slack 2
2. a large operand (> 12) would exceed `OPERAND_REPEAT_CAP`
3. a template (expression shape with every number masked) would exceed `TEMPLATE_REPEAT_CAP`
4. distance between the problem's work units and the target level
5. trick strategy use (tricks only)
6. total large-operand reuse
7. exact imbalance

Reordering the tuple changes every seeded sequence: treat it as a generation-version change (see Versions).

The target level comes from `_next_level()`: a seeded, shuffled cycle over the band's available levels. `start_stage()` clears that cycle and the per-stage operation counts, so each stage spreads over the whole band. `Challenge.create_session` passes the carried-over candidate to `start_stage` so the count includes it.

`generate_many` alternates families: arithmetic is picked while its count is at most the advanced families' total, otherwise the least-used advanced family.

## Catalogs

- `_catalog_groups` is `lru_cache`d on `(profile, operations, difficulty, topics)`. Keep every new parameter hashable, and expect a stale pool if a parameter is left out of the key.
- It filters by work-unit band, drops round products (`_round_product`) except on `easy`, and drops small quotients (`_small_quotient`, quotient < 3) on `normal` and `hard`.
- `accepted` rejects an additive chain of three or more terms whose values are all equal, such as `log_3 9 + log_2 4 + 2`. Both catalogs and tricks go through `accepted`.
- Problems group by signature: `(operator counts, units)`, or `(strategy, units)` for tricks.
- An empty family raises `GenerationError`; the CLI reports it as a configuration error (exit 2).
- Exhausting a family refills that family's queue with a fresh shuffle, adds one warning, and leaves other families' uniqueness intact. `Challenge` shows the warning only when a repeat was actually displayed.

## Topic atoms

`catalog.topic_atoms` fixes the ranges: square roots 2–20; power bases 2–20 with exponents 2 and 3; logarithm bases 2, 3, 5, 10 with exponents −3 through 4; trigonometry from an exact-value table. Intermediate denominators stay at most 12 through `accepted`/`valid_bounds`. `topic_catalog` keeps only integer answers: a fractional atom such as `sin(30) = 1/2` also yields whole multiples (`2*sin(30)`, `4*sin(30)`, `6*sin(30)`, via `integral_forms`), and `add` drops any other fractional result. Widening a range is a product change.

## Tricks

`core/tricks.py` assigns work units per trick (a trick makes large-looking numbers cheap), so `complexity_score` reads `problem.work_units` instead of running the heuristic. The generator uses `TRICK_MAX_RESULT[difficulty]` for the trick pool, and `trick_levels()` derives the level column of `numbra tricks` from the same bands. A new trick needs a `TRICKS` entry, catalog problems, and a test in `tests/test_tricks.py` that checks the example and each level it appears on.

## Funbox

`core/funbox/` holds one module per mode, each with `make(rng, difficulty, units)` returning a `Problem` with `family="funbox"`, `tree=None`, `operations=()`, and `work_units` set to the drawn unit. `FunboxGenerator` has the `ProblemGenerator` surface that `Challenge.create_session` calls (`generate_many`, `start_stage`, `warnings`). Modes rotate by least-used count, and uniqueness is by display text: `canonical_problem_key` returns `("funbox", expression)`, because funbox texts are not arithmetic trees. After 50 failed draws a repeat is accepted and one warning is added. Funbox problems get no operation bonus (`_problem_bonus` returns 0), and their answers are `Answer` values rendered by `format_answer` (`core/models.py`) and matched by `_matches_answer` (`core/challenge.py`). The settings fingerprint gains a `funbox` key only for funbox sessions, so ordinary fingerprints do not change.

## Versions

Generated sequences and scores are stamped with `generation_version` and `scoring_version`, and `comparable_history` only matches equal stamps. Any change that alters the sequence for a seed or the score for an attempt needs a bump. The literals currently live in several places in `core/challenge.py` (`CompletedTraining` defaults, `TrainingSession.__init__`, and `"generation"`/`"scoring"` inside the settings fingerprint); change them together and confirm with a grep for `generation`.

Done when the closest generator tests pass, `tests/test_generation_quality.py` and `tests/test_generation_matrix.py` still hold for default six-minute sessions, and a fixed seed reproduces its sequence across two runs.
