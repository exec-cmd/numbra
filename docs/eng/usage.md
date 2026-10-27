# Usage

## Install and start

Numbra requires Python 3.13 or newer. Install it from a project checkout with:

```bash
uv tool install .
```

Start a challenge in an interactive terminal and view completed sessions with:

```bash
numbra challenge
numbra results
```

Use `numbra --help`, `numbra --version`, or `numbra challenge --help` for command help. Press `Ctrl+C` to cancel a challenge; incomplete sessions are not saved.

## Choose a challenge

| Option | Default | Effect |
| --- | --- | --- |
| `-t, --duration MINUTES` | 6 minutes or saved setting | Target training length; minimum 1 minute. |
| `-d, --difficulty LEVEL` | `normal` | `easy`, `normal`, or `hard`. |
| `-S, --seed INTEGER` | Saved seed or a new random seed | Repeats the same generated session when other settings match. |
| `-o, --operations LIST` | `+,-,*,/` | Select operations and topics: `+,-,*,/,sqrt,trig,log,power,tricks`; `^` also means `power`. |
| `-n, --stages INTEGER` | 3 or saved setting | Number of stages; minimum 1. |
| `--strict` | Off | A timeout immediately ends the attempt. |
| `--cooldown SECONDS` | 2 seconds | Pause between examples; accepts 1–3 seconds. |
| `--advanced` / `--no-advanced` | Saved settings | Enable all operations and advanced topics, or turn off configured advanced topics; `tricks` is unaffected. |
| `--identities` / `--no-identities` | Saved setting | Independently enable or disable numerical identities. |

For example:

```bash
numbra challenge --duration 6 --difficulty normal --seed 42 --operations +,-,*,/ --stages 3
```

Advanced topics are off by default. Use `-o "sqrt,trig,log,power"` to select them; `identities` is selected with `--identities`. With `-o "sqrt"`, every exercise includes a square root and there are no standalone arithmetic exercises. Topic exercises use the selected basic operations, or all four if none are listed. A challenge must be long enough to include every selected topic; otherwise startup tells you the minimum duration required.

`tricks` selects mental-math tricks such as `43 * 11`, `37 * 99`, or `97 * 94`. It is chosen only with `-o` or `[features] tricks`; `--advanced` and `--no-advanced` leave it unchanged. `-o tricks` alone gives a session of tricks only; `-o "+,-,*,/,tricks"` alternates tricks with ordinary arithmetic. Run `numbra tricks` to see every trick with its rule, an example, and the levels it appears on.

Answers may be integers or exact fractions such as `3/4`. How stages, time limits, difficulty, and points work is described in [Training rules](training.md).

## After a challenge

Numbra prints the result (correct answers, score, grade), a breakdown by stage kind, operation, and topic, and then your progress:

- `Previous comparable` and `Delta` — the last session with exactly the same settings and generator version.
- `Avg correct answer` — your mean time for correct answers, with the best and previous value in the same progress group.
- `New personal best` or `Personal best` — your best score percentage in the group and the difference to it.
- `Streak` — consecutive days with at least one completed challenge, and your longest streak.
- `Recommendation` — after three sessions in the group: try the next level, keep it, or step down. On `hard` it never suggests a higher level.

A progress group is difficulty, strict or soft mode, and the selected operations and topics. Duration, stage count, and generator updates do not split a group.

## Review or clear results

`numbra results` shows recent completed sessions, totals by operation, topic, and difficulty, your streak, a `Personal records` table per progress group, and, once you have trained with `tricks`, a `Tricks` table with attempts, accuracy, and average correct time for each trick. Choose how many sessions to display with `--limit`, for example `numbra results --limit 20`.

To clear saved results, run `numbra results --reset` and confirm the prompt. For a script, add `--yes` to skip confirmation. Reset removes training history, records, and streaks.
