# Configuration

## Keep your preferences

On first run, Numbra creates a configuration folder and a `numbra.toml` file. The file stores the default challenge length, difficulty, number of stages, operations, optional seed, and advanced-topic choices. Command-line options override saved settings; saved settings override built-in defaults.

You can edit `numbra.toml` by hand or use `numbra config`, described below. For example, this keeps six-minute normal challenges with three stages and enables square roots:

```toml
[challenge]
duration_minutes = 6
difficulty = "normal"
stages = 3
operations = ["+", "-", "*", "/"]

[features]
sqrt = true
```

The supported difficulties are `easy`, `normal`, and `hard`. Older files that still say `very-easy` or `very-hard` keep working: they are read as `easy` or `hard` with a warning, and matching `[difficulties.very-easy]` or `[difficulties.very-hard]` tables are ignored with a warning. Numbra does not rewrite your file on its own; remove those values when convenient. Advanced topics (`sqrt`, `trig`, `log`, `power`, and `identities`) and `tricks` are off by default; `--advanced` never turns `tricks` on or off. `identities` is a separate choice and is not an operation in the `operations` list. See [Usage](usage.md) for command-line switches and [Training rules](training.md) for difficulty profiles.

The `[funbox]` table holds `modes = []`, a list of experimental funbox modes (`fractions`, `substitution`, `equations`, `logic`, `graphs`, `derivatives`). Numbra checks the names when it reads the file and reports an unknown mode with `funbox.modes`. The interactive Funbox screen starts with these modes checked. `numbra challenge --funbox` does not read this list; it uses the modes given on its command line. See [Training rules](training.md#funbox-experimental).

Leave out `seed` to get a new random sequence each time. Set an integer seed when you want to repeat a generated session with matching settings.

## Change settings from the command line

`numbra config` reads and changes `numbra.toml` without a text editor. The **Settings** screen of the interactive interface makes the same changes (see [Usage](usage.md#interactive-mode)):

```bash
numbra config list                             # every setting with its effective value
numbra config get challenge.difficulty         # one value
numbra config set challenge.difficulty hard
numbra config set challenge.operations '["+", "-"]'
numbra config set challenge.seed 42
numbra config unset challenge.seed             # back to a new random seed each time
numbra config path                             # where numbra.toml is kept
```

Keys are the dotted names used in `numbra.toml`, such as `features.trig` or `stages.fast.limit_seconds`. Every key in the built-in defaults can be set, plus the optional `challenge.seed`. Quote keys that contain `*` in the shell, for example `'timing.operation_bonus_seconds.*'`.

A value is read as TOML, so `true`, `42`, `7.5`, and `["+", "*"]` keep their types. Text that is not valid TOML is stored as a string, so `hard` needs no quotes. `unset` removes the key from the file, and the built-in default applies again.

Numbra checks the whole file before it writes. An unknown key, or a value the file would reject, fails with an error that names the key and `numbra.toml`, and the file stays unchanged. A successful change rewrites `numbra.toml` in Numbra's own layout, so comments added by hand are lost. `list` and `get` also validate the file, so a broken file is reported instead of shown.

## Where settings and results are stored

Configuration files are kept in the operating system's application configuration folder. Training history is stored separately in a local database in the application data folder. Numbra does not use an account or cloud sync.

On Linux, the folders normally live under `~/.config/numbra` and `~/.local/share/numbra`; `XDG_CONFIG_HOME` and `XDG_DATA_HOME` can change them. On macOS, both use `~/Library/Application Support/numbra`. On Windows, configuration uses `%APPDATA%\numbra` and data uses `%LOCALAPPDATA%\numbra`.

## Limits and errors

Challenge length and stage count must be at least one. Cooldown accepts one to three seconds. Difficulty profiles limit operand sizes and results. Advanced topics use finite sets of exact values, so not every mathematically possible expression is available. A challenge that cannot fit every selected topic reports the minimum duration needed.

Numbra reports invalid configuration with the affected filename or setting. Existing settings are not rewritten automatically when the application is updated. `temps.json` and `design.toml` are created alongside `numbra.toml` and validated on challenge startup; their defaults need no manual editing. Integer settings require TOML integers, and operations require an array of strings. Booleans and numeric strings are not accepted as numbers.
