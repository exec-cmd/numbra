"""Focused tests for the grouped settings table and its type-aware editors."""

import asyncio
from pathlib import Path
from typing import Any

from test_tui import FakeClock, make_app, make_settings, open_settings, plain_text, wait_until
from textual.containers import Vertical
from textual.pilot import Pilot
from textual.widgets import Button, DataTable, Input, OptionList, SelectionList, Static

from numbra.config import ConfigPaths, get_value
from numbra.tui.settings import SettingsScreen


async def open_setting(pilot: Pilot[Any], screen: SettingsScreen, key: str) -> None:
    table = screen.query_one(DataTable)
    table.move_cursor(row=table.get_row_index(key))
    await pilot.press("enter")


def test_rows_show_readable_names_groups_and_values(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            table = screen.query_one(DataTable)
            assert table.get_row("challenge.duration_minutes")[0].plain == "  Length, minutes"
            assert table.get_row("challenge.difficulty")[0].plain == "  Difficulty"
            assert table.get_row("challenge.operations")[1] == "+ − × ÷"
            assert table.get_row("features.sqrt")[1] == "off"
            assert table.get_row("generation.brackets")[0].plain == "  Brackets in long examples"
            assert table.get_row("generation.brackets")[1] == "on"
            keys = [row.key.value for row in table.ordered_rows]
            assert "group:Training" in keys
            assert "group:Examples" in keys
            assert "group:Topics" in keys
            assert table.get_row("group:Training")[0].plain == "Training"
            assert table.get_row("group:Training")[0].style == "bold"
            assert table.cursor_row == 1
            assert plain_text(screen.query_one("#help", Static)) == "How long one training lasts."

    asyncio.run(scenario())


def test_enter_toggles_boolean_setting(tmp_path: Path) -> None:
    async def scenario() -> None:
        paths = ConfigPaths.from_root(tmp_path / "config")
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            await open_setting(pilot, screen, "features.sqrt")
            await wait_until(pilot, lambda: get_value(paths, "features.sqrt") is True)
            assert screen.query_one(DataTable).get_row("features.sqrt")[1] == "on"

    asyncio.run(scenario())


def test_generation_brackets_toggle_saves_false(tmp_path: Path) -> None:
    async def scenario() -> None:
        paths = ConfigPaths.from_root(tmp_path / "config")
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            await open_setting(pilot, screen, "generation.brackets")
            await wait_until(pilot, lambda: get_value(paths, "generation.brackets") is False)
            assert screen.query_one(DataTable).get_row("generation.brackets")[1] == "off"

    asyncio.run(scenario())


def test_difficulty_modal_saves_hard(tmp_path: Path) -> None:
    async def scenario() -> None:
        paths = ConfigPaths.from_root(tmp_path / "config")
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            await open_setting(pilot, screen, "challenge.difficulty")
            await wait_until(pilot, lambda: app.screen is not screen)
            assert app.screen.query_one(Vertical).border_subtitle == "Enter saves, Esc cancels"
            options = app.screen.query_one("#value", OptionList)
            options.highlighted = 2
            await pilot.press("enter")
            await wait_until(pilot, lambda: app.screen is screen)
            assert get_value(paths, "challenge.difficulty") == "hard"

    asyncio.run(scenario())


def test_difficulty_modal_save_button_saves_highlighted_value(tmp_path: Path) -> None:
    async def scenario() -> None:
        paths = ConfigPaths.from_root(tmp_path / "config")
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            await open_setting(pilot, screen, "challenge.difficulty")
            await wait_until(pilot, lambda: app.screen is not screen)
            editor = app.screen
            options = editor.query_one("#value", OptionList)
            options.highlighted = 2
            editor.query_one("#save", Button).focus()
            await pilot.press("enter")
            await wait_until(pilot, lambda: app.screen is screen)
            assert get_value(paths, "challenge.difficulty") == "hard"

    asyncio.run(scenario())


def test_operations_modal_saves_selection_in_canonical_order(tmp_path: Path) -> None:
    async def scenario() -> None:
        paths = ConfigPaths.from_root(tmp_path / "config")
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            await open_setting(pilot, screen, "challenge.operations")
            await wait_until(pilot, lambda: app.screen is not screen)
            choices = app.screen.query_one("#value", SelectionList)
            assert choices.get_option_at_index(2).prompt == "× multiplication"
            choices.highlighted = 1
            await pilot.press("space")
            app.screen.query_one("#save", Button).focus()
            await pilot.press("enter")
            await wait_until(pilot, lambda: app.screen is screen)
            assert get_value(paths, "challenge.operations") == ["+", "*", "/"]

    asyncio.run(scenario())


def test_empty_operations_selection_shows_error_without_writing(tmp_path: Path) -> None:
    async def scenario() -> None:
        paths = ConfigPaths.from_root(tmp_path / "config")
        settings = make_settings(tmp_path)
        before = paths.main.read_bytes()
        app = make_app(tmp_path, settings, FakeClock())
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            await open_setting(pilot, screen, "challenge.operations")
            await wait_until(pilot, lambda: app.screen is not screen)
            editor = app.screen
            choices = editor.query_one("#value", SelectionList)
            for index in range(4):
                choices.highlighted = index
                await pilot.press("space")
            editor.query_one("#save", Button).focus()
            await pilot.press("enter")
            await wait_until(
                pilot, lambda: plain_text(editor.query_one("#modal-error", Static)) != ""
            )
            assert "operation list must not be empty" in plain_text(
                editor.query_one("#modal-error", Static)
            )
            assert get_value(paths, "challenge.operations") == ["+", "-", "*", "/"]
            await pilot.press("escape")

        assert paths.main.read_bytes() == before

    asyncio.run(scenario())


def test_numeric_modal_rejects_text_and_accepts_integer(tmp_path: Path) -> None:
    async def scenario() -> None:
        paths = ConfigPaths.from_root(tmp_path / "config")
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            await open_setting(pilot, screen, "challenge.stages")
            await wait_until(pilot, lambda: app.screen is not screen)
            editor = app.screen
            field = editor.query_one("#value", Input)
            field.value = "abc"
            await pilot.press("enter")
            await wait_until(
                pilot,
                lambda: (
                    "Enter a whole number" in plain_text(editor.query_one("#modal-error", Static))
                ),
            )
            assert get_value(paths, "challenge.stages") == 3
            field.value = "8"
            await pilot.press("enter")
            await wait_until(pilot, lambda: app.screen is screen)
            assert get_value(paths, "challenge.stages") == 8

    asyncio.run(scenario())


def test_reset_restores_default_and_group_row_is_inert(tmp_path: Path) -> None:
    async def scenario() -> None:
        paths = ConfigPaths.from_root(tmp_path / "config")
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            table = screen.query_one(DataTable)
            table.move_cursor(row=table.get_row_index("features.sqrt"))
            await pilot.press("enter")
            await wait_until(pilot, lambda: get_value(paths, "features.sqrt") is True)
            await pilot.press("d")
            await wait_until(pilot, lambda: get_value(paths, "features.sqrt") is False)
            before = paths.main.read_bytes()
            table.move_cursor(row=table.get_row_index("group:Training"))
            await pilot.press("enter")
            await pilot.press("d")
            await pilot.pause()
            assert app.screen is screen
            assert paths.main.read_bytes() == before

    asyncio.run(scenario())


def test_help_changes_with_highlighted_row(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            table = screen.query_one(DataTable)
            table.move_cursor(row=table.get_row_index("challenge.difficulty"))
            await pilot.pause()
            assert plain_text(screen.query_one("#help", Static)) == (
                "The default level for new trainings: easy, normal or hard."
            )
            table.move_cursor(row=table.get_row_index("challenge.operations"))
            await pilot.pause()
            assert plain_text(screen.query_one("#help", Static)) == "Operations used by default."

    asyncio.run(scenario())
