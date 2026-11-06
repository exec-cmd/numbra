<div align="center">

# numbra

**A terminal trainer for daily mental-arithmetic speed practice.**

[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
![Local first](https://img.shields.io/badge/local--first-no%20account%2C%20no%20network-informational)

English · [Русский](README_RU.md)

</div>

Numbra generates reproducible exercises, runs short timed stages, and keeps your history, personal records, and day streak in a local SQLite database.

## Features

- **Reproducible sessions.** A seed gives the same exercises every time; exercises stay unique until the catalog runs out.
- **Three difficulties.** `easy`, `normal`, and `hard`, with transparent static profiles.
- **Timed stages.** Slow, normal, and fast stages. Soft mode keeps input open past the limit and lowers the score; `--strict` ends the attempt at the limit.
- **Beyond `+ − × ÷`.** Optional square roots, trigonometry, logarithms, powers, identities, and mental-math **tricks** such as `43 * 11` or `97 * 94`.
- **Exact answers.** Every answer is a whole number, graded with exact arithmetic; fractions such as `3/4` are also accepted as input.
- **Progress that means something.** Grades from S to D, personal bests per setup, average time per correct answer, a level recommendation, and a day streak.
- **Local only.** No account, no cloud, no network.

## Install

Python 3.13 or newer is required. From a checkout:

```bash
uv tool install .
numbra --version
```

Or download `numbra-<version>-py3-none-any.whl` from the release assets and run `uv tool install ./numbra-<version>-py3-none-any.whl`.

## Quick start

Run `numbra` with no arguments in a terminal to open the interactive interface: a menu for training, results and tricks. The commands below remain available for scripts and quick use.

```bash
numbra                           # interactive interface
numbra challenge                 # six minutes, three stages, normal difficulty
numbra challenge -d hard --strict
numbra challenge -o "*,/" -t 3   # only multiplication and division, three minutes
numbra challenge -o tricks       # mental-math tricks
numbra tricks                    # every trick with its rule and an example
numbra results                   # history, personal records, streak
numbra config list               # every setting and its value
numbra config set challenge.difficulty hard   # save a new default
```

Press `Ctrl+C` to cancel; an incomplete session is not saved.

### What a session looks like

```text
Stage 1/3 · slow · 9 examples
Example 1/27 · limit 17s
48 * 5 =
Correct · score 1.00
```

After the last example Numbra prints your score and grade, a breakdown by stage, operation, and topic, the delta against your previous comparable session, your personal best, and your streak.

## Documentation

| Page | What is in it |
| --- | --- |
| [Usage](docs/eng/usage.md) | Commands, options, results |
| [Training rules](docs/eng/training.md) | Difficulty, stages, timing, scoring, progress |
| [Configuration](docs/eng/configuration.md) | `numbra.toml`, `numbra config`, file locations |
| [Agent reference](docs/develop/README.md) | Internals for coding agents; start with [AGENTS.md](AGENTS.md) |

## Development

```bash
uv sync --locked --all-groups
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

## License

MIT. See [LICENSE](LICENSE).
