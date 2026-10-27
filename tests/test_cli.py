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
    assert "1.0.1" in version_result.stdout


def test_invalid_operations_are_reported() -> None:
    result = runner.invoke(app, ["challenge", "--operations", "%"])
    assert result.exit_code == 2
    assert "unsupported operation" in result.stdout


def test_very_easy_is_not_a_cli_difficulty() -> None:
    result = runner.invoke(app, ["challenge", "--difficulty", "very-easy"])
    assert result.exit_code == 2


def test_cli_rejects_very_hard() -> None:
    result = runner.invoke(app, ["challenge", "--difficulty", "very-hard"])
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
    assert "score" in result.stdout
    assert re.search(r"score \d+\.\d{2}/\d+\.\d{2}", result.stdout)
    assert "grade" in result.stdout
    assert "Topics: sqrt" in result.stdout
    plain_output = re.sub(r"\s+", " ", result.stdout)
    expected_operations = ", ".join(selection.split(","))
    assert f"Operations: {expected_operations}" in plain_output
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
    assert "Avg correct answer:" in output
    assert "New personal best:" in output
    assert " · best " not in output
    assert "Streak: 1 day (best 1)" in output


def test_challenge_prints_progress_block(monkeypatch) -> None:
    _run_correct_challenge(monkeypatch, "-S", "1")
    output = _run_correct_challenge(monkeypatch, "-S", "2", "-t", "2")
    assert re.search(r"Avg correct answer: \d+\.\d{2}s · best \d+\.\d{2}s · previous", output)
    assert "Personal best:" in output or "New personal best:" in output
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
    assert "Streak: 1 day (best 1)" in output
    assert "Personal records" in output
