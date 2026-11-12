import asyncio
import importlib
import re
import sys
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from numbra.cli import app
from numbra.cli.input import cooldown, timed_prompt

runner = CliRunner()


def test_help_and_version() -> None:
    help_result = runner.invoke(app, ["--help"])
    version_result = runner.invoke(app, ["--version"])
    assert help_result.exit_code == 0
    assert "challenge" in help_result.stdout
    assert version_result.exit_code == 0
    assert "1.5.0" in version_result.stdout


def test_invalid_operations_are_reported() -> None:
    result = runner.invoke(app, ["challenge", "--operations", "%"])
    assert result.exit_code == 2
    assert "unsupported operation" in result.stdout


@pytest.mark.parametrize("level", ["very-easy", "very-hard"])
def test_legacy_levels_are_not_cli_difficulties(level: str) -> None:
    result = runner.invoke(app, ["challenge", "--difficulty", level])
    assert result.exit_code == 2


def test_results_empty_database_is_clear() -> None:
    result = runner.invoke(app, ["results", "--limit", "10"])
    assert result.exit_code == 0
    assert "No completed challenges" in result.stdout


def test_results_reset_requires_confirmation() -> None:
    result = runner.invoke(app, ["results", "--reset"], input="n\n")
    assert result.exit_code == 0
    assert "cancelled" in result.stdout.lower()


def test_short_flags_are_documented() -> None:
    result = runner.invoke(app, ["challenge", "--help"])
    assert result.exit_code == 0
    plain_help = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]|\s+", "", result.stdout)
    assert "-t" in plain_help
    assert "-n" in plain_help
    assert "--strict" in plain_help
    assert "--cooldown" in plain_help
    for flag in ("--advanced", "--identities"):
        assert flag in plain_help
    for topic in ("sqrt", "trig", "log", "power"):
        assert topic in plain_help
    assert "fraction" in plain_help.lower()


def test_operation_selection_and_remaining_flags_are_passed(monkeypatch) -> None:
    from numbra.core.challenge import Challenge

    captured = {}

    def capture_options(self, options):
        captured["options"] = options
        raise ValueError("stop after capturing options")

    monkeypatch.setattr(Challenge, "create_session", capture_options)
    result = runner.invoke(app, ["challenge", "-o", "sqrt,trig", "--no-identities", "--advanced"])

    assert result.exit_code == 2
    options = captured["options"]
    assert options.advanced is True
    from numbra.core.models import Topic

    assert options.operations == (Topic.SQRT, Topic.TRIG)
    assert options.identities is False


def test_timed_prompt_returns_none_after_timeout(monkeypatch) -> None:
    class NeverEndingPrompt:
        async def prompt_async(self, *args, **kwargs):
            await asyncio.sleep(1)

    monkeypatch.setitem(
        sys.modules,
        "prompt_toolkit",
        SimpleNamespace(PromptSession=lambda: NeverEndingPrompt()),
    )
    assert asyncio.run(timed_prompt("answer: ", 0.01)) is None


def test_soft_prompt_accepts_answer_after_limit(monkeypatch) -> None:
    class DelayedPrompt:
        async def prompt_async(self, *args, **kwargs):
            await asyncio.sleep(0.02)
            return "42"

    monkeypatch.setitem(
        sys.modules,
        "prompt_toolkit",
        SimpleNamespace(PromptSession=lambda: DelayedPrompt()),
    )
    assert asyncio.run(timed_prompt("answer: ", 0.001, strict=False)) == "42"


def test_cooldown_uses_injected_sleeper() -> None:
    calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        calls.append(seconds)

    asyncio.run(cooldown(2.0, fake_sleep))

    assert calls == [2.0]


@pytest.mark.parametrize("selection", ["+,sqrt", "sqrt"])
def test_challenge_prints_score_and_grade(monkeypatch, selection) -> None:
    from numbra.config import ConfigManager

    manager = ConfigManager()
    manager.load_or_create()
    settings_path = manager.paths.main
    settings_path.write_text(
        settings_path.read_text(encoding="utf-8").replace(
            'difficulty = "normal"', 'difficulty = "very-easy"'
        ),
        encoding="utf-8",
    )
    cli_module = importlib.import_module("numbra.cli.app")

    async def fake_prompt(*args, **kwargs):
        return "0"

    async def fake_cooldown(*args, **kwargs):
        return None

    monkeypatch.setattr(cli_module, "timed_prompt", fake_prompt)
    monkeypatch.setattr(cli_module, "cooldown", fake_cooldown)

    result = runner.invoke(
        app,
        [
            "challenge",
            "--duration",
            "1",
            "--stages",
            "1",
            "--operations",
            selection,
            "--cooldown",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert "Score" in result.stdout
    assert "Accuracy" in result.stdout
    assert "Time" in result.stdout
    plain_output = re.sub(r"\s+", " ", result.stdout)
    assert "Warning:" in plain_output and "using 'easy'" in plain_output


def _run_correct_challenge(monkeypatch, *extra: str):
    from numbra.core.expressions import parse_expression

    cli_module = importlib.import_module("numbra.cli.app")

    async def correct_prompt(text, *args, **kwargs):
        return str(parse_expression(text.removesuffix(" = ")).evaluate())

    async def no_cooldown(*args, **kwargs):
        return None

    monkeypatch.setattr(cli_module, "timed_prompt", correct_prompt)
    monkeypatch.setattr(cli_module, "cooldown", no_cooldown)
    args = ["challenge", "-t", "1", "-n", "1", "-o", "+", "--cooldown", "1", *extra]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.stdout
    return re.sub(r"\s+", " ", result.stdout)


def test_first_session_prints_new_best_without_comparison(monkeypatch) -> None:
    output = _run_correct_challenge(monkeypatch)
    assert "Time" in output
    assert "New personal best!" in output
    assert "Streak: 1 day (best 1)" in output


def test_challenge_prints_progress_block(monkeypatch) -> None:
    _run_correct_challenge(monkeypatch, "-S", "1")
    output = _run_correct_challenge(monkeypatch, "-S", "2", "-t", "2")
    assert "Best" in output
    assert "matched" in output or "to go" in output or "New personal best!" in output
    assert "Streak: 1 day (best 1)" in output


def test_recommendation_uses_progress_group(monkeypatch) -> None:
    for seed in ("1", "2"):
        _run_correct_challenge(monkeypatch, "-S", seed, "-t", seed)
    output = _run_correct_challenge(monkeypatch, "-S", "3", "-t", "3")
    assert "Recommendation: try the next difficulty level." in output


def test_recommendation_on_hard_never_suggests_next_level(monkeypatch) -> None:
    for seed in ("1", "2"):
        _run_correct_challenge(monkeypatch, "-d", "hard", "-S", seed)
    output = _run_correct_challenge(monkeypatch, "-d", "hard", "-S", "3")
    assert "Recommendation: keep the current difficulty level." in output


def test_results_prints_streak_and_records(monkeypatch) -> None:
    _run_correct_challenge(monkeypatch)
    result = runner.invoke(app, ["results"])
    assert result.exit_code == 0
    output = re.sub(r"\s+", " ", result.stdout)
    assert "Streak 1 day (best 1)" in output
    assert "Personal bests" in output


def test_tricks_command_lists_every_trick() -> None:
    from numbra.core.tricks import TRICKS

    result = runner.invoke(app, ["tricks"])
    assert result.exit_code == 0
    output = re.sub(r"\s+", " ", result.stdout)
    assert "Mental-math tricks" in output
    for trick in TRICKS:
        assert trick.id in output
    assert "easy, normal" in output


def test_results_uses_shared_metric_names_and_area_names(monkeypatch) -> None:
    _run_correct_challenge(monkeypatch, "-o", "*")
    output = runner.invoke(app, ["results"]).stdout
    assert all(
        label in output
        for label in ("Sessions", "Skills", "Personal bests", "Time", "multiplication")
    )
    assert "Average answer" not in output


def test_results_time_uses_only_correct_answers(monkeypatch) -> None:
    cli_module = importlib.import_module("numbra.cli.app")
    from numbra.core.expressions import parse_expression

    attempts = 0

    async def one_wrong_answer(text, *args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            return "wrong"
        return str(parse_expression(text.removesuffix(" = ")).evaluate())

    async def no_cooldown(*args, **kwargs):
        return None

    monkeypatch.setattr(cli_module, "timed_prompt", one_wrong_answer)
    monkeypatch.setattr(cli_module, "cooldown", no_cooldown)
    challenge = runner.invoke(app, ["challenge", "-t", "1", "-n", "1", "-o", "+"])
    assert challenge.exit_code == 0, challenge.stdout
    import sqlite3

    from numbra.config import default_database_path

    with sqlite3.connect(default_database_path()) as connection:
        connection.execute(
            "UPDATE attempts SET elapsed = CASE is_correct WHEN 1 THEN 1.0 ELSE 9.0 END"
        )

    output = runner.invoke(app, ["results"]).stdout
    assert "Time           1.0 s" in output
    assert "3.7 s" not in output


def test_results_shows_tricks_table_only_with_data(monkeypatch) -> None:
    _run_correct_challenge(monkeypatch)
    assert "Tricks" not in runner.invoke(app, ["results"]).stdout
    _run_correct_challenge(monkeypatch, "-o", "tricks")
    result = runner.invoke(app, ["results"])
    assert result.exit_code == 0
    assert "Skills" in result.stdout
    assert "Tricks" in result.stdout
    assert "Time" in result.stdout


def test_config_help_lists_commands() -> None:
    result = runner.invoke(app, ["config", "--help"])
    assert result.exit_code == 0
    for command in ("list", "get", "set", "unset", "path"):
        assert command in result.stdout


def test_config_set_get_and_unset_round_trip() -> None:
    assert runner.invoke(app, ["config", "set", "challenge.difficulty", "hard"]).exit_code == 0
    get_result = runner.invoke(app, ["config", "get", "challenge.difficulty"])
    assert get_result.exit_code == 0
    assert get_result.stdout.strip() == '"hard"'
    unset_result = runner.invoke(app, ["config", "unset", "challenge.difficulty"])
    assert unset_result.exit_code == 0
    assert unset_result.stdout.strip() == 'challenge.difficulty = "normal"'


def test_config_list_prints_effective_values() -> None:
    result = runner.invoke(app, ["config", "list"])
    assert result.exit_code == 0
    assert 'challenge.difficulty = "normal"' in result.stdout
    assert 'challenge.operations = ["+", "-", "*", "/"]' in result.stdout


def test_config_set_accepts_negative_seed() -> None:
    result = runner.invoke(app, ["config", "set", "challenge.seed", "-5"])
    assert result.exit_code == 0
    assert "challenge.seed = -5" in result.stdout


def test_config_invalid_value_exits_2_and_names_key_and_file() -> None:
    result = runner.invoke(app, ["config", "set", "challenge.difficulty", "bogus"])
    assert result.exit_code == 2
    assert "Configuration error" in result.stdout
    assert "challenge.difficulty" in result.stdout
    assert "numbra.toml" in result.stdout


def test_config_unknown_key_exits_2() -> None:
    result = runner.invoke(app, ["config", "get", "challenge.nope"])
    assert result.exit_code == 2
    assert "challenge.nope" in result.stdout


def test_config_path_is_inside_isolated_config_root() -> None:
    result = runner.invoke(app, ["config", "path"])
    assert result.exit_code == 0
    assert result.stdout.strip().endswith("numbra.toml")
    assert "platform-config" in result.stdout


def test_results_shows_summary_history_and_breakdown(monkeypatch) -> None:
    _run_correct_challenge(monkeypatch)
    result = runner.invoke(app, ["results"])
    assert result.exit_code == 0
    output = re.sub(r"\s+", " ", result.stdout)
    assert "Sessions 1" in output
    assert re.search(r"Score trend [▁▂▃▄▅▆▇█]+", output)
    assert "Sessions" in output
    assert "Skills" in output
    assert "Difficulty" in output
    assert "Operations" in output
    assert "Time" in output


def test_results_weak_spots_list_missed_operations(monkeypatch) -> None:
    cli_module = importlib.import_module("numbra.cli.app")

    async def wrong_prompt(*args, **kwargs):
        return "x"

    async def no_cooldown(*args, **kwargs):
        return None

    monkeypatch.setattr(cli_module, "timed_prompt", wrong_prompt)
    monkeypatch.setattr(cli_module, "cooldown", no_cooldown)
    # Seed 2 gives three examples with five additions, enough for a weak spot (five attempts).
    challenge = runner.invoke(
        app, ["challenge", "-t", "1", "-n", "1", "-o", "+", "--cooldown", "1", "-S", "2"]
    )
    assert challenge.exit_code == 0, challenge.stdout

    result = runner.invoke(app, ["results"])

    assert result.exit_code == 0
    output = re.sub(r"\s+", " ", result.stdout)
    assert "Practise next" in output
    assert "0%" in output.split("Practise next", 1)[1].split("Personal bests", 1)[0]


def test_results_yes_requires_reset() -> None:
    result = runner.invoke(app, ["results", "--yes"])
    assert result.exit_code == 2
    assert "--yes can only be used with --reset" in result.stdout


def test_sparkline_maps_scores_to_block_characters() -> None:
    cli_module = importlib.import_module("numbra.cli.app")

    assert cli_module._sparkline([0.0, 0.5, 1.0, 2.0, -1.0]) == "▁▅██▁"


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def test_funbox_rejects_unknown_modes_and_ordinary_selection() -> None:
    unknown = runner.invoke(app, ["challenge", "--funbox", "nope"])
    assert unknown.exit_code == 2
    assert _compact("unsupported funbox mode 'nope'") in _compact(unknown.stdout)

    combined = runner.invoke(app, ["challenge", "--funbox", "logic", "-o", "+"])
    assert combined.exit_code == 2
    assert _compact("cannot be combined with -o") in _compact(combined.stdout)


def test_funbox_challenge_runs_a_short_session(monkeypatch) -> None:
    cli_module = importlib.import_module("numbra.cli.app")

    async def fake_prompt(*args, **kwargs):
        return "true"

    async def no_cooldown(*args, **kwargs):
        return None

    monkeypatch.setattr(cli_module, "timed_prompt", fake_prompt)
    monkeypatch.setattr(cli_module, "cooldown", no_cooldown)
    result = runner.invoke(
        app, ["challenge", "--funbox", "logic", "-t", "1", "-n", "1", "--cooldown", "1"]
    )

    assert result.exit_code == 0, result.stdout
    output = re.sub(r"\s+", " ", result.stdout)
    assert "Funbox (experimental): logic" in output
    assert re.search(r"Correct|Incorrect", output)
    assert "Previous comparable" not in output
    assert "Recommendation" not in output


def test_results_lists_funbox_in_its_own_table(monkeypatch) -> None:
    cli_module = importlib.import_module("numbra.cli.app")

    async def fake_prompt(*args, **kwargs):
        return ""

    async def no_cooldown(*args, **kwargs):
        return None

    monkeypatch.setattr(cli_module, "timed_prompt", fake_prompt)
    monkeypatch.setattr(cli_module, "cooldown", no_cooldown)
    run = runner.invoke(
        app, ["challenge", "--funbox", "logic", "-t", "1", "-n", "1", "--cooldown", "1"]
    )
    assert run.exit_code == 0, run.stdout

    result = runner.invoke(app, ["results"])

    assert result.exit_code == 0
    output = re.sub(r"\s+", " ", result.stdout)
    assert "No completed challenges yet." in output
    assert "Funbox (experimental)" in output
    assert "logic" in output
