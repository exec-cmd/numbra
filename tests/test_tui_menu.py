"""Focused tests for the menu hotkeys and side panel."""

import asyncio
from io import StringIO
from pathlib import Path

from rich.console import Console
from test_tui import (
    FakeClock,
    make_app,
    make_settings,
    save_completed_session,
    wait_until,
)
from textual.widgets import DataTable, OptionList, Static

from numbra.tui.app import MENU
from numbra.tui.results import ResultsScreen
from numbra.tui.settings import SettingsScreen
from numbra.tui.tricks import TricksScreen


def render_text(widget: Static) -> str:
    output = StringIO()
    Console(file=output, force_terminal=False).print(widget.content)
    return output.getvalue()


def test_menu_hotkeys_open_screens_and_quit(tmp_path: Path) -> None:
    async def scenario() -> None:
        for key, screen_type in (("r", ResultsScreen), ("s", SettingsScreen), ("k", TricksScreen)):
            app = make_app(tmp_path / key, make_settings(tmp_path / key), FakeClock())
            async with app.run_test() as pilot:
                await pilot.press(key)
                await wait_until(
                    pilot,
                    lambda app=app, screen_type=screen_type: isinstance(app.screen, screen_type),
                )

        app = make_app(tmp_path / "quit", make_settings(tmp_path / "quit"), FakeClock())
        async with app.run_test() as pilot:
            await pilot.press("q")
            await pilot.pause()
            assert not app.is_running

    asyncio.run(scenario())


def test_menu_about_tracks_highlight(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            about = app.screen.query_one("#about", Static)
            assert MENU[0][3] in render_text(about)
            await pilot.press("down")
            await wait_until(pilot, lambda: MENU[1][3] in render_text(about))

    asyncio.run(scenario())


def test_menu_about_shows_saved_stats_or_empty_message(tmp_path: Path) -> None:
    async def scenario() -> None:
        empty_app = make_app(tmp_path / "empty", make_settings(tmp_path / "empty"), FakeClock())
        async with empty_app.run_test() as pilot:
            await pilot.pause()
            empty_text = render_text(empty_app.screen.query_one("#about", Static))
            assert "No trainings yet" in empty_text

        saved_path = tmp_path / "saved"
        save_completed_session(saved_path)
        saved_app = make_app(saved_path, make_settings(saved_path), FakeClock())
        async with saved_app.run_test() as pilot:
            await pilot.pause()
            saved_text = render_text(saved_app.screen.query_one("#about", Static))
            assert "Streak" in saved_text
            assert "Last" in saved_text

    asyncio.run(scenario())


def test_tricks_table_fits_at_80_columns(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test(size=(80, 24)) as pilot:
            menu = app.screen.query_one(OptionList)
            menu.highlighted = 3
            await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, TricksScreen))
            table = app.screen.query_one(DataTable)
            assert sum(column.get_render_width(table) for column in table.columns.values()) <= 78

    asyncio.run(scenario())
