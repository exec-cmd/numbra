from typer.testing import CliRunner

from numbra.cli import app

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
