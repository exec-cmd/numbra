# Usage

## Interactive mode

Run `numbra` with no arguments in a terminal to open the interactive interface. The menu offers **Train**, **Results**, **Settings**, **Tricks** and **Funbox** (experimental, see [Training rules](training.md#funbox-experimental)); `q` or **Quit** exits. Train walks through a setup form (difficulty, duration, stages, operations and topics, strict mode, seed), then the timed run, then the summary. The form starts from your saved settings. Tricks lists every trick with an example and the levels it appears on; the full rule of the selected row is shown below the table. Without a terminal, for example when output is piped, `numbra` prints the help text instead. Every command in this page works the same way.

Keys during a training:

- `Enter` submits the answer. After the cooldown the next example appears.
- `Esc` pressed twice cancels the training. Nothing is saved.
- In the summary, `Enter` or `Esc` returns to the menu. The setup forms (Train and Funbox), Settings and Tricks screens close with `Esc`.
- `Ctrl+Q` quits from any screen. An unfinished training is not saved.

Settings lists every key of `numbra.toml` with its effective value, and the file path at the top. `Enter` on a row opens an edit line holding the value as a TOML literal, such as `hard`, `42` or `["+", "-"]`. `Enter` saves it. A value the file would reject stays on screen with the error, and nothing is written until it is fixed or `Esc` cancels the edit. `d` or `Delete` removes the key, so the built-in default applies again. Each change is written to `numbra.toml` at once, and the next Train setup uses it.

The Results screen shows the same saved data as `numbra results`, on tabs:

- **Overview** shows the totals (sessions, examples, accuracy, time per answer, streak), the score trend with the best and average score (it needs two sessions), the last session, and up to three areas to practise next. An area appears there once it has at least five attempts and a miss, as in the weak spots of `numbra results`.
- **History** lists completed sessions, newest first, with the level, correct answers, score, grade, time per answer and length. Select a row with `Enter` to see every example of that session: stage, expression, your answer, the correct answer, result, time and score. `Esc` returns to the list.
- **Breakdown** shows accuracy, attempts and the time per correct answer by difficulty, operation, topic and trick.
- **Records** lists the best score and best time per answer for each level and operation set, as `numbra results` does.
- **Funbox** lists the mode totals and the completed funbox sessions; `Enter` on a session opens its examples, as in History. Funbox results are not part of the other tabs.
- History and the trend cover the 1000 newest sessions; the totals cover all of them.

`r` reloads the data, and `Esc` returns to the menu. The screen cannot reset results; use `numbra results --reset`.

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
| `--funbox MODES` | Off | Experimental: run only the listed modes, such as `logic,equations`. Cannot be combined with `-o`, `--advanced`, or `--identities`. |

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
- `Funbox (experimental)` — shown only after funbox sessions, with attempts, accuracy, and average correct time for each mode. Funbox results are not part of the other tables, records, the streak, or comparisons.

To clear saved results, run `numbra results --reset` and confirm the prompt. For a script, add `--yes` to skip confirmation. Reset removes training history, records, streaks, and funbox results.

## Change saved settings

`numbra config list` shows every saved setting with its effective value. `numbra config get KEY` and `numbra config set KEY VALUE` read and change one setting, `numbra config unset KEY` restores its built-in default, and `numbra config path` prints the location of `numbra.toml`. Options given to `numbra challenge` still override these values for a single run. Keys and value syntax are described in [Configuration](configuration.md#change-settings-from-the-command-line).
