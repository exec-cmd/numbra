# Usage

## Interactive mode

Run `numbra` with no arguments in a terminal to open the interactive interface. The menu shows the Numbra logo and these items: `t` **Train**, `r` **Results**, `s` **Settings**, `k` **Tricks**, `f` **Funbox**, and `q` **Quit**. A side panel describes the selected item and shows your Streak, last session, and an area to practise when available. Funbox is experimental; see [Training rules](training.md#funbox-experimental). The interface is in English or Russian, chosen by the `[ui] language` setting (see [Configuration](configuration.md#keep-your-preferences)); command-line output stays English. Without a terminal, for example when output is piped, `numbra` prints the help text instead.

In **Train**, a short wizard sets up the run. The first page offers presets: **Repeat last** (the setup of your newest training), **Weak spot** (your settings with only your weakest operation or topic), **Quick** (your settings for two minutes), and **From settings**. A preset opens **Review**; **Custom…** walks through **Level**, **Practise**, **Time**, and **Review**. `Enter` moves on, `Esc` goes one step back, and on Review `1`–`4` jump to a step. `Ctrl+S` starts from any step with the current values. **Funbox** uses the same steps without presets. During the run, the status line shows the stage, example, and correct and incorrect counts. An overall progress bar tracks the run; the example card contains the timer and expression. Operators display as `×`, `÷`, and `−`. The timer changes to its warning colour below 30% of the limit and shows overtime as `+N s over`. Feedback appears after each answer.

Keys during a training:

- `Enter` submits the answer. After the cooldown the next example appears.
- `Esc` pressed twice cancels the training. Nothing is saved.
- In the summary, `Enter` or `Esc` returns to the menu, `d` reviews the answers, and `t` starts another training with the same options. An explicit seed is reused; otherwise new examples are generated.
- `q` quits from the menu. An unfinished training is not saved.

**Results** has three tabs:

- **Overview** shows tiles for sessions, Accuracy, Time, and Streak with hints; the Score trend; the last session; areas to practise next; and up to five Personal bests.
- **Sessions** lists challenge and funbox sessions, newest first. Press `Enter` on a row to open that session.
- **Skills** groups operations, topics, tricks, difficulty, and funbox, with an Accuracy bar, attempts, and Time per correct answer.

Press `?` to open the metric legend. In session detail, examples are numbered continuously and mistakes are highlighted; press `m` to show mistakes only or all examples. `Esc` returns to Results. Press `r` to reload results and `Esc` to return to the menu.

**Settings** shows grouped rows with readable names and a help line for the selected setting. Press `Enter` to toggle on/off settings, open a difficulty list, an operations or funbox modes checklist, or a number field. Press `d` to restore the selected setting's built-in default. The file and keys of `numbra.toml` are unchanged; each edit is saved immediately.

**Tricks** lists tricks in the `Trick`, `Problem`, and `Levels` columns; levels use `E`, `N`, and `H`. The panel below the table shows the selected trick's rule, a worked example, and its levels.

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

Numbra displays a summary card shared with the interactive interface. It shows your Grade, Score, Accuracy, and Time, with changes against the previous comparable session where available. Ordinary sessions also show Best against your Personal best. The card includes a stage table, weakest area when present, Streak, and recommendation when available.

A progress group is difficulty, strict or soft mode, and the selected operations and topics. Duration, stage count, and generator updates do not split a group.

## Review or clear results

`numbra results` prints a `Results` panel with sessions, Accuracy, Time, Streak, last session, and Score trend, followed by:

- `Sessions` — the latest sessions, newest first. `--limit` sets the number of rows, for example `numbra results --limit 20`.
- `Skills` — attempts, accuracy, and Time by operations, topics, tricks, and difficulty.
- `Practise next` — shown when areas to practise are available.
- `Personal bests` — one row per progress group, with its best score and Time.
- `Funbox (experimental)` — shown when there are funbox results, with attempts, accuracy, and Time by mode.
- A closing note explains Time and Score.

To clear saved results, run `numbra results --reset` and confirm the prompt. For a script, add `--yes` to skip confirmation. Reset removes training history, records, streaks, and funbox results.

## Change saved settings

`numbra config list` shows every saved setting with its effective value. `numbra config get KEY` and `numbra config set KEY VALUE` read and change one setting, `numbra config unset KEY` restores its built-in default, and `numbra config path` prints the location of `numbra.toml`. Options given to `numbra challenge` still override these values for a single run. Keys and value syntax are described in [Configuration](configuration.md#change-settings-from-the-command-line).
