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

Every answer is an integer. Input may also be an exact fraction such as `6/3`, which is compared exactly. How stages, time limits, difficulty, and points work is described in [Training rules](training.md).

## After a challenge

Numbra prints the result (correct answers, score, grade), a breakdown by stage kind, operation, and topic, and then your progress:

- `Previous comparable` and `Delta` — the last session with exactly the same settings and generator version.
- `Avg correct answer` — your mean time for correct answers, with the best and previous value in the same progress group.
- `New personal best` or `Personal best` — your best score percentage in the group and the difference to it.
- `Streak` — consecutive days with at least one completed challenge, and your longest streak.
- `Recommendation` — after three sessions in the group: try the next level, keep it, or step down. On `hard` it never suggests a higher level.

A progress group is difficulty, strict or soft mode, and the selected operations and topics. Duration, stage count, and generator updates do not split a group.

## Review or clear results

`numbra results` prints, in order:

- `Results` panel — completed sessions, examples, accuracy, and average answer time over all sessions; your streak; the grade of the last session; and a score sparkline of the sessions shown, oldest to newest, plus the timeout count.
- `History` — the most recent sessions, newest first: correct answers, accuracy, score, grade (S, A, B, C, or D), and average answer time. Choose the number of rows with `--limit`, for example `numbra results --limit 20`.
- `Breakdown` — attempts, accuracy, and average time of correct answers by difficulty, operation, and topic.
- `Weak spots` — shown only when some operation, topic, or trick has at least five attempts. It lists the three groups with the lowest accuracy; ties go to the group with the slower correct answers.
- `Personal records` — one row per progress group, and, once you have trained with `tricks`, a `Tricks` table with attempts, accuracy, and average correct time for each trick.

To clear saved results, run `numbra results --reset` and confirm the prompt. For a script, add `--yes` to skip confirmation. Reset removes training history, records, and streaks.

## Change saved settings

`numbra config list` shows every saved setting with its effective value. `numbra config get KEY` and `numbra config set KEY VALUE` read and change one setting, `numbra config unset KEY` restores its built-in default, and `numbra config path` prints the location of `numbra.toml`. Options given to `numbra challenge` still override these values for a single run. Keys and value syntax are described in [Configuration](configuration.md#change-settings-from-the-command-line).
