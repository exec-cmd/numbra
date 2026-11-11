"""Coverage for the setup wizard navigation and preset values."""

import asyncio
from pathlib import Path

from test_tui import FakeClock, make_app, make_settings, save_completed_session, wait_until
from textual.widgets import Button, Input, OptionList, SelectionList, Static

from numbra.core.models import Difficulty
from numbra.core.stats import GroupStats, Stats
from numbra.tui.app import MenuScreen
from numbra.tui.funbox import FunboxSetupScreen
from numbra.tui.train import TrainSetupScreen


async def open_training(pilot, app) -> TrainSetupScreen:
    await pilot.press("t")
    await wait_until(pilot, lambda: isinstance(app.screen, TrainSetupScreen))
    assert isinstance(app.screen, TrainSetupScreen)
    return app.screen


def test_presets_reflect_history_and_settings(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_training(pilot, app)
            presets = screen.query_one("#presets", OptionList)
            assert [presets.get_option_at_index(i).id for i in range(presets.option_count)] == [
                "quick",
                "settings",
                "custom",
            ]
            await pilot.press("escape")
            await wait_until(pilot, lambda: isinstance(app.screen, MenuScreen))

        save_completed_session(tmp_path)
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_training(pilot, app)
            presets = screen.query_one("#presets", OptionList)
            assert presets.get_option_at_index(0).id == "repeat"
            presets.highlighted = 0
            await pilot.press("enter")
            await pilot.pause()
            assert screen.query_one("#duration", Input).value == "1"
            assert screen._difficulty() is Difficulty.EASY
            assert screen.query_one("#strict").value is False
            assert screen.query_one("#choices", SelectionList).selected == ["+"]
            assert screen.query_one("#steps").current == "step-review"

    asyncio.run(scenario())


def test_custom_navigation_error_and_digit_routing(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_training(pilot, app)
            presets = screen.query_one("#presets", OptionList)
            presets.highlighted = presets.option_count - 1
            await pilot.press("enter")
            await wait_until(pilot, lambda: screen.query_one("#steps").current == "step-level")
            await pilot.press("enter", "enter", "enter")
            await wait_until(pilot, lambda: screen.query_one("#steps").current == "step-review")
            await pilot.press("2")
            await wait_until(pilot, lambda: screen.query_one("#steps").current == "step-practise")
            await pilot.press("escape")
            await wait_until(pilot, lambda: screen.query_one("#steps").current == "step-review")
            await pilot.press("escape")
            await wait_until(pilot, lambda: screen.query_one("#steps").current == "step-time")
            screen.query_one("#duration", Input).focus()
            screen.query_one("#duration", Input).select_all()
            await pilot.press("2")
            await pilot.pause()
            assert screen.query_one("#duration", Input).value == "2"
            assert screen.query_one("#steps").current == "step-time"
            await pilot.press("escape")
            await pilot.press("escape")
            await pilot.press("escape")
            await pilot.press("escape")
            await wait_until(pilot, lambda: isinstance(app.screen, MenuScreen))

        app = make_app(tmp_path / "empty", make_settings(tmp_path / "empty"), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_training(pilot, app)
            screen.query_one("#presets", OptionList).highlighted = 2
            await pilot.press("enter")
            await pilot.press("enter", "enter")
            await wait_until(pilot, lambda: screen.query_one("#steps").current == "step-time")
            choices = screen.query_one("#choices", SelectionList)
            choices.deselect_all()
            await pilot.press("ctrl+s")
            await wait_until(pilot, lambda: screen.query_one("#steps").current == "step-practise")
            assert "operation list" in str(screen.query_one("#practise-error", Static).content)

    asyncio.run(scenario())


def test_weak_spot_preset_selects_only_its_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        Stats,
        "weak_spots",
        lambda self, min_attempts=5, limit=3: [GroupStats("operation", "/", 6, 2, 1.0)],
    )

    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_training(pilot, app)
            presets = screen.query_one("#presets", OptionList)
            assert presets.get_option_at_index(0).id == "weak"
            presets.highlighted = 0
            await pilot.press("enter")
            await pilot.pause()
            assert screen.query_one("#choices", SelectionList).selected == ["/"]
            assert screen.query_one("#steps").current == "step-review"

    asyncio.run(scenario())


def test_funbox_wizard_and_80x24_layout(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test(size=(80, 24)) as pilot:
            screen = await open_training(pilot, app)
            assert screen.query_one("#presets").region.bottom <= 23
            screen.query_one("#presets", OptionList).highlighted = 2
            await pilot.press("enter")
            await pilot.press("enter", "enter", "enter")
            await wait_until(pilot, lambda: screen.query_one("#steps").current == "step-review")
            assert screen.query_one("#start", Button).region.bottom <= 23
            await pilot.press("escape", "escape", "escape", "escape", "escape")
            await pilot.press("f")
            await wait_until(pilot, lambda: isinstance(app.screen, FunboxSetupScreen))
            funbox = app.screen
            assert funbox.query_one("#steps").current == "step-level"
            assert not funbox.query("#presets")
            assert funbox.query_one("#choices", SelectionList)
            assert funbox.query_one("#start", Button).region.bottom <= 23

    asyncio.run(scenario())
