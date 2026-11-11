import asyncio

from test_tui import FakeClock, make_app, make_settings

from numbra.tui.style import days, display_expression, grade_text, seconds


def test_display_expression_only_replaces_spaced_operators() -> None:
    assert display_expression("(47 - 39) * 41") == "(47 − 39) × 41"
    assert display_expression("30 / 6 + 9") == "30 ÷ 6 + 9"
    assert display_expression("1/2 + 3/4") == "1/2 + 3/4"
    assert display_expression("-3 + 4") == "-3 + 4"


def test_days_uses_singular_for_one_day() -> None:
    assert days(1) == "1 day"
    assert days(2) == "2 days"


def test_seconds_formats_values_and_missing_time() -> None:
    assert seconds(None) == "—"
    assert seconds(1.25) == "1.2 s"


def test_grade_text_uses_grade_for_score() -> None:
    assert grade_text(0.99).plain == "S"


def test_datatable_cursor_style_loads_with_ansi_themes(tmp_path) -> None:
    async def scenario() -> None:
        for theme in ("ansi-dark", "ansi-light"):
            app = make_app(tmp_path / theme, make_settings(tmp_path / theme), FakeClock())
            app.theme = theme
            async with app.run_test(size=(80, 24)):
                pass

    asyncio.run(scenario())
