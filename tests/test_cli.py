import asyncio
import sys
from types import SimpleNamespace

from typer.testing import CliRunner

from numbra.cli import app
from numbra.cli.input import timed_prompt

runner = CliRunner()


def test_help_and_version() -> None:
    help_result = runner.invoke(app, ["--help"])
    version_result = runner.invoke(app, ["--version"])
    assert help_result.exit_code == 0
    assert "challenge" in help_result.stdout
    assert version_result.exit_code == 0
    assert "0.1.0" in version_result.stdout


def test_invalid_operations_are_reported() -> None:
    result = runner.invoke(app, ["challenge", "--operations", "^"])
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
