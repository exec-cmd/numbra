# numbra

English | [Русский](README_RU.md)

`numbra` is a terminal trainer for daily mental-arithmetic speed practice. It generates reproducible exercises, runs short timed stages, and keeps your history, personal records, and day streak in a local SQLite database. No account, no network.

## Install

Python 3.13 or newer is required. From a checkout:

```bash
uv tool install .
numbra --version
```

Or download `numbra-<version>-py3-none-any.whl` from the release assets and run `uv tool install ./numbra-<version>-py3-none-any.whl`.

## Quick start

```bash
numbra challenge                 # six minutes, three stages, normal difficulty
numbra challenge -d hard --strict
numbra challenge -o "*,/" -t 3   # only multiplication and division, three minutes
numbra results                   # history, personal records, streak
```

Press `Ctrl+C` to cancel; an incomplete session is not saved. After each session Numbra shows your average time per correct answer, your personal best for the same settings, and your current streak.

## Documentation

- [Usage](docs/eng/usage.md) — commands, options, results.
- [Training rules](docs/eng/training.md) — difficulty, stages, timing, scoring, progress.
- [Configuration](docs/eng/configuration.md) — `numbra.toml`, file locations.
- [Contributor docs](docs/develop/README.md) and [AGENTS.md](AGENTS.md) for coding agents.

## License

MIT. See [LICENSE](LICENSE).
