"""Keep every command test away from the developer's real config and history."""

import pytest


@pytest.fixture(autouse=True)
def isolated_platform_paths(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "platform-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "platform-data"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "platform-config"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "platform-data"))
