import asyncio
import importlib
import sys
from types import SimpleNamespace

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
    assert "1.0.0" in version_result.stdout


def test_invalid_operations_are_reported() -> None:
    result = runner.invoke(app, ["challenge", "--operations", "%"])
    assert result.exit_code == 2
    assert "unsupported operation" in result.stdout


def test_results_empty_database_is_clear(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    result = runner.invoke(app, ["results", "--limit", "10"])
    assert result.exit_code == 0
    assert "No completed challenges" in result.stdout


def test_results_reset_requires_confirmation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    result = runner.invoke(app, ["results", "--reset"], input="n\n")
    assert result.exit_code == 0
    assert "cancelled" in result.stdout.lower()


def test_short_flags_are_documented() -> None:
    result = runner.invoke(app, ["challenge", "--help"])
    assert result.exit_code == 0
    assert "-t" in result.stdout
    assert "-n" in result.stdout
    assert "--strict" in result.stdout
    assert "--cooldown" in result.stdout


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


def test_challenge_prints_score_and_grade(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
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
            "+",
            "--cooldown",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert "score" in result.stdout
    assert "grade" in result.stdout
