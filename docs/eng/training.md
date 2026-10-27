# Training rules

## Difficulty

Each level combines a fixed operand profile with a band of *work units*, a transparent estimate of the mental steps a problem needs (for example, a carry or a two-digit product adds a step). Difficulty never adapts to your past answers.

| Level | Operands | Numbers per problem | Max result | Work units |
| --- | ---: | ---: | ---: | ---: |
| `easy` | 1–20 | 2 | 400 | 1–2 |
| `normal` | 2–50 | 2–3 | 500 | 2–5 |
| `hard` | 5–999 | 3–4 | 10,000 | 4–9 |

Inside a stage, problems cycle through every work-unit level of the band in a shuffled order, so a stage mixes lighter and heavier problems instead of staying at one level. Selected operations stay balanced. Large operands (above 12) are not repeated more than three times per session while other problems are available, and `normal` and `hard` skip divisions whose quotient is below 3.

Arithmetic follows standard precedence and is exact; division never divides a value by itself, and negative intermediate values and answers are allowed. A seed reproduces the same sequence for the same settings. Exercise collections are finite: when one is exhausted, examples repeat and Numbra prints a warning.

Advanced topics are bounded: square roots cover perfect squares with roots 2–20; powers use bases 2–20 and exponents 2 or 3; logarithms use bases 2, 3, 5, or 10 with integer results −3 through 4; trigonometry uses exact rational values from its degree tables; identities use bounded sum and product patterns. Intermediate fractions have denominators of at most 12.

## Stages and time limits

Stage kinds repeat `slow`, `normal`, `fast` with default limits of 15, 10, and 5 seconds per answer. Stages change the pace, not the difficulty: each stage gets a comparable share of the time budget and problems from the same band. Operation bonuses add time per operation in a problem: 0 s for `+` and `-`, 1 s for `*`, 2 s for `/`, 3 s for `^`.

In the default soft mode you can keep typing after the limit. `--strict` ends the attempt at the limit. `--cooldown` (1–3 s, default 2) pauses between examples.

## Points and grades

A correct answer is worth up to `1 + 0.2 × max(0, work units − 1)` points, so heavier problems are worth more. Within the limit you get the full value; in soft mode the value then falls linearly to zero at twice the limit. Wrong answers and strict timeouts score zero.

The session score is a percentage of the maximum. Grades: S ≥ 90%, A ≥ 75%, B ≥ 60%, C ≥ 40%, otherwise D.

## Progress

A progress group is the difficulty, the mode (strict or soft), and the selected operations and topics. Within a group Numbra tracks your best score percentage and your best average time per correct answer. Duration, stage count, and generator updates do not start a new group.

A day counts toward your streak when at least one challenge was completed on it, in local time. The streak continues through the next day, so it does not reset in the morning before you train; a fully missed day resets it to zero. The longest streak is kept.

Only completed challenges are saved. A cancelled challenge leaves no trace.
