from string import Formatter

from typer.testing import CliRunner

from numbra.core.report import AREA_NAMES, METRIC_HELP, RECOMMENDATION_TEXT
from numbra.core.tricks import TRICKS
from numbra.i18n import (
    LANGUAGES,
    MISSES,
    PLURALS,
    current_language,
    resolve_language,
    set_language,
    t,
    tn,
)
from numbra.locale_ru import MESSAGES


def test_resolve_language() -> None:
    assert resolve_language("auto", {"LC_ALL": "ru_RU.UTF-8"}) == "ru"
    assert resolve_language("auto", {"LC_ALL": "", "LANG": "ru_RU.UTF-8"}) == "ru"
    assert resolve_language("auto", {"LANG": "en_US.UTF-8"}) == "en"
    assert resolve_language("auto", {}) == "en"
    assert resolve_language("en", {"LANG": "ru_RU.UTF-8"}) == "en"
    assert resolve_language("ru", {}) == "ru"
    assert LANGUAGES == ("auto", "en", "ru")


def test_plural_forms() -> None:
    set_language("ru")
    expected = {
        1: "{n} день",
        2: "{n} дня",
        5: "{n} дней",
        11: "{n} дней",
        12: "{n} дней",
        14: "{n} дней",
        21: "{n} день",
        22: "{n} дня",
        25: "{n} дней",
        101: "{n} день",
        111: "{n} дней",
    }
    for count, form in expected.items():
        assert tn(count, "{n} day", "{n} days") == form
    set_language("en")
    assert tn(1, "day", "days") == "day"
    assert tn(2, "day", "days") == "days"


def test_translation_context_and_fallback() -> None:
    set_language("ru")
    assert t("normal", "difficulty") == "средний"
    assert t("normal", "stage") == "обычный"
    MISSES.clear()
    assert t("missing phrase") == "missing phrase"
    assert "missing phrase" in MISSES


def test_translation_catalog_integrity() -> None:
    assert all(len(forms) == 3 and all(forms) for forms in PLURALS.values())

    def fields(value: str) -> list[str]:
        return sorted(name for _, name, _, _ in Formatter().parse(value) if name)

    for key, value in MESSAGES.items():
        assert fields(value) == fields(key), key
    assert set(METRIC_HELP) <= set(MESSAGES)
    assert set(METRIC_HELP.values()) <= set(MESSAGES)
    assert set(AREA_NAMES.values()) <= set(MESSAGES)
    assert {str(value) for value in RECOMMENDATION_TEXT.values()} <= set(MESSAGES)
    assert {trick.rule for trick in TRICKS} <= set(MESSAGES)


def test_cli_results_remains_english(monkeypatch) -> None:
    from numbra.cli.app import app

    monkeypatch.setenv("LANG", "ru_RU.UTF-8")
    result = CliRunner().invoke(app, ["results", "--limit", "10"])
    assert result.exit_code == 0
    assert "No completed challenges" in result.stdout
    assert current_language() == "en"


def test_russian_catalog_covers_static_texts() -> None:
    # Settings help lines, metric help and trick rules are only shown for the focused row,
    # so the screen walk in test_tui_i18n cannot reach all of them.
    from numbra.core.report import AREA_NAMES, METRIC_HELP, RECOMMENDATION_TEXT
    from numbra.core.tricks import TRICKS
    from numbra.locale_ru import MESSAGES
    from numbra.tui.settings import _LABELS

    needed = {text for row in _LABELS.values() for text in row}
    needed |= {*METRIC_HELP, *METRIC_HELP.values(), *AREA_NAMES.values()}
    needed |= set(RECOMMENDATION_TEXT.values())
    needed |= {trick.rule for trick in TRICKS} | {f"trick|{trick.id}" for trick in TRICKS}
    assert sorted(needed - set(MESSAGES)) == []
