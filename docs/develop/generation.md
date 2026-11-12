# Generation internals

Read before changing `core/generator.py`, `core/catalog.py`, `core/tricks.py`, or `core/expressions.py`. Product rules (uniqueness, balance, bands, caps) live in `AGENTS.md`; this file records how the code meets them.

## Selection

Arithmetic is constructed on demand; `_construct()` samples candidates and ranks them by operation imbalance beyond slack 2, large-operand cap violations, large-operand reuse, and exact imbalance. There is no finite arithmetic catalog or template cap. A candidate is unique by `canonical_problem_key` within the session. If no unseen candidate can be built under the selected settings, the generator repeats a built candidate and adds `Selected settings require repeated arithmetic exercises; unique catalog exhausted.` `OPERAND_REPEAT_CAP` remains 3 for operands above 12.

Tricks and advanced topics still use finite catalogs. `_take(family)` examines a candidate window per signature group (`CANDIDATE_WINDOW` unseen problems each) and ranks by operation imbalance beyond slack 2, operand cap, distance from the target work-unit level, trick strategy use, large-operand reuse, and exact imbalance. Exhausting one of these catalogs reshuffles and reuses that family, adds its repeat warning, and preserves other families' uniqueness. `Challenge` shows a warning only when a repeat is displayed.

The target level comes from `_next_level()`: a seeded, shuffled cycle over the band's available levels. `start_stage()` clears that cycle and the per-stage operation counts, so each stage spreads over the whole band. `Challenge.create_session` passes the carried-over candidate to `start_stage` so the count includes it. `generate_many` alternates arithmetic with the least-used finite family.

## Arithmetic construction

`catalog.build_arithmetic` builds each expression on demand from a drawn term count and configured operand, operation, result, dividend, and quotient bounds. Term counts use a shuffled short bag of quotas; default weights halve for each added term, so each extra term is half as likely. If a term count cannot produce an allowed unseen exercise, it is removed from later bags. Division-only selection uses two terms. Construction allows at most one division per exercise and bounds bracket nesting to depth 1 and two pairs total. Normal and hard allow dividends up to `max_result`; easy uses `max_value`. Normal and hard reject quotients below 3.

After construction, `_allowed` checks the arithmetic work-unit band and excludes round products outside easy. A failed band check discards the candidate. About one in six returned exercises hides one number as `?`; the answer is that missing number. Commutative `+` and `*` operands are permuted with a seeded forms RNG so their order varies.

Default term ranges are easy 2–3, normal 2–6, hard 3–8. Existing user files with the old default ranges (2–2, 2–3, 3–4) are read using these new defaults. `[generation] brackets` defaults to `true`, must be a boolean, and is exposed as the TUI setting `generation.brackets`. Grouping runs after operand permutation and missing-number selection, using its own `random.Random(f"{seed}:grouping")`; it adds at most two pairs at depth one, never inside existing brackets, and does not change canonical keys or generation versions.

Re-parsing grouped display text can produce a different canonical key, so keys come from the stored tree, never from `Problem.expression`.

Arithmetic work-unit bands are easy 1–3, normal 2–8, hard 4–16; hard division-only uses a floor of 3. Tricks and advanced topics retain easy 1–2, normal 2–5, hard 4–9. `_catalog_groups` remains cached on `(profile, operations, difficulty, topics)` for finite families. `accepted` rejects additive chains of three or more terms whose values are all equal, such as `log_3 9 + log_2 4 + 2`.

## Topic atoms

`catalog.topic_atoms` fixes the ranges: square roots 2–20; power bases 2–20 with exponents 2 and 3; logarithm bases 2, 3, 5, 10 with exponents −3 through 4; trigonometry from an exact-value table. Intermediate denominators stay at most 12 through `accepted`/`valid_bounds`. `topic_catalog` keeps only integer answers: a fractional atom such as `sin(30) = 1/2` also yields whole multiples (`2*sin(30)`, `4*sin(30)`, `6*sin(30)`, via `integral_forms`), and `add` drops any other fractional result. Widening a range is a product change.

## Tricks

`core/tricks.py` assigns work units per trick (a trick makes large-looking numbers cheap), so `complexity_score` reads `problem.work_units` instead of running the heuristic. The generator uses `TRICK_MAX_RESULT[difficulty]` for the trick pool, and `trick_levels()` derives the level column of `numbra tricks` from the same bands. A new trick needs a `TRICKS` entry, catalog problems, and a test in `tests/test_tricks.py` that checks the example and each level it appears on.

## Funbox

`core/funbox/` holds one module per mode, each with `make(rng, difficulty, units)` returning a `Problem` with `family="funbox"`, `tree=None`, `operations=()`, and `work_units` set to the drawn unit. `FunboxGenerator` has the `ProblemGenerator` surface that `Challenge.create_session` calls (`generate_many`, `start_stage`, `warnings`). Modes rotate by least-used count, and uniqueness is by display text: `canonical_problem_key` returns `("funbox", expression)`, because funbox texts are not arithmetic trees. After 50 failed draws a repeat is accepted and one warning is added. Funbox problems get no operation bonus (`_problem_bonus` returns 0), and their answers are `Answer` values rendered by `format_answer` (`core/models.py`) and matched by `_matches_answer` (`core/challenge.py`). The settings fingerprint gains a `funbox` key only for funbox sessions, so ordinary fingerprints do not change.

## Versions

Generated sequences and scores are stamped with `generation_version` and `scoring_version`, and `comparable_history` only matches equal stamps. Current values are `generation_version = 7`, settings fingerprint `"generation" = 6`, and `scoring_version = 2`. Any change that alters a seeded sequence or an attempt score needs the corresponding bump. The generation version literals are in `core/challenge.py` (`CompletedTraining` defaults and `TrainingSession.__init__`); the fingerprint generation and scoring keys are set there too. Keep each stamp synchronized with the behavior it identifies.

Done when the closest generator tests pass, `tests/test_generation_quality.py` and `tests/test_generation_matrix.py` still hold for default six-minute sessions, and a fixed seed reproduces its sequence across two runs.
