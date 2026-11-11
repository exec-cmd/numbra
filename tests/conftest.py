"""Keep every command test away from the developer's real config and history."""

import pytest

from numbra.i18n import set_language


@pytest.fixture(autouse=True)
def isolated_platform_paths(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "platform-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "platform-data"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "platform-config"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "platform-data"))


@pytest.fixture(autouse=True)
def english_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.setenv(key, "C.UTF-8")
    set_language("en")
    yield
    set_language("en")
