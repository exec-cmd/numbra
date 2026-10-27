# Configuration

## Keep your preferences

On first run, Numbra creates a configuration folder and a `numbra.toml` file. The file stores the default challenge length, difficulty, number of stages, operations, optional seed, and advanced-topic choices. Command-line options override saved settings; saved settings override built-in defaults.

The simplest way to change settings is to edit `numbra.toml`. For example, this keeps six-minute normal challenges with three stages and enables square roots:

```toml
[challenge]
duration_minutes = 6
difficulty = "normal"
stages = 3
operations = ["+", "-", "*", "/"]

[features]
sqrt = true
```

The supported difficulties are `easy`, `normal`, `hard`, and `very-hard`. Advanced topics (`sqrt`, `trig`, `log`, `power`, and `identities`) are off by default. `identities` is a separate choice and is not an operation in the `operations` list. See [Usage](usage.md) for command-line switches and topic behavior.

Leave out `seed` to get a new random sequence each time. Set an integer seed when you want to repeat a generated session with matching settings.

## Where settings and results are stored

Configuration files are kept in the operating system's application configuration folder. Training history is stored separately in a local database in the application data folder. Numbra does not use an account or cloud sync.

On Linux, the folders normally live under `~/.config/numbra` and `~/.local/share/numbra`; `XDG_CONFIG_HOME` and `XDG_DATA_HOME` can change them. On macOS, both use `~/Library/Application Support/numbra`. On Windows, configuration uses `%APPDATA%\numbra` and data uses `%LOCALAPPDATA%\numbra`.

## Limits and errors

Challenge length and stage count must be at least one. Cooldown accepts one to three seconds. Difficulty profiles limit operand sizes and results. Advanced topics use finite sets of exact values, so not every mathematically possible expression is available. A challenge that cannot fit every selected topic reports the minimum duration needed.

Numbra reports invalid configuration with the affected filename or setting. Existing settings are not rewritten automatically when the application is updated. `temps.json` and `design.toml` are created alongside `numbra.toml` and validated on challenge startup; their defaults need no manual editing. Integer settings require TOML integers, and operations require an array of strings. Booleans and numeric strings are not accepted as numbers.
