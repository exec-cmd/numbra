"""Drive the Textual app headlessly with a fake clock and a no-op cooldown sleeper.

Every test writes to a temporary database and reads settings from a temporary config root.
"""

import asyncio
import importlib
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from textual.pilot import Pilot
from textual.widgets import Button, DataTable, Input, OptionList, Static, Switch
from typer.testing import CliRunner

import numbra.tui
from numbra.config import ConfigError, ConfigManager, ConfigPaths, Settings
from numbra.core.models import Difficulty, Operation
from numbra.core.stats import Stats
from numbra.core.tricks import TRICKS
from numbra.tui.app import MENU, MenuScreen, NumbraApp
from numbra.tui.train import SummaryScreen, TrainingScreen, TrainSetupScreen
from numbra.tui.tricks import TricksScreen

cli_app_module = importlib.import_module("numbra.cli.app")
cli_app = cli_app_module.app


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


async def no_sleep(_seconds: float) -> None:
    return None


def make_settings(tmp_path: Path, **changes: Any) -> Settings:
    settings = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    base = {
        "duration_minutes": 1,
        "stages": 1,
        "difficulty": Difficulty.EASY,
        "operations": (Operation.ADD,),
        "seed": 42,
    }
    return replace(settings, challenge=replace(settings.challenge, **{**base, **changes}))


def make_app(
    tmp_path: Path, settings: Settings, clock: FakeClock, *, sleeper=no_sleep
) -> NumbraApp:
    return NumbraApp(
        settings_loader=lambda: settings,
        database_path=tmp_path / "numbra.sqlite3",
        today=lambda: date(2026, 11, 6),
        clock=clock,
        sleeper=sleeper,
    )


async def wait_until(pilot: Pilot[Any], predicate: Callable[[], bool]) -> None:
    for _ in range(300):
        if predicate():
            return
        await pilot.pause(0.01)
    raise AssertionError("condition was not reached")


def plain_text(widget: Static) -> str:
    content = widget.content
    return getattr(content, "plain", str(content))


async def start_training(pilot: Pilot[Any], app: NumbraApp) -> TrainingScreen:
    await pilot.press("enter")  # Menu: Train
    await wait_until(pilot, lambda: isinstance(app.screen, TrainSetupScreen))
    app.screen.query_one("#start", Button).focus()
    await pilot.press("enter")
    await wait_until(pilot, lambda: isinstance(app.screen, TrainingScreen))
    screen = app.screen
    assert isinstance(screen, TrainingScreen)
    return screen


def test_menu_lists_every_entry(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, MenuScreen)
            menu = app.screen.query_one(OptionList)
            labels = [str(menu.get_option_at_index(i).prompt) for i in range(menu.option_count)]
            assert labels == [label for _, label, _ in MENU]
            assert labels == ["Train", "Tricks", "Quit"]

    asyncio.run(scenario())


def test_full_short_session_is_saved(tmp_path: Path) -> None:
    async def scenario() -> None:
        clock = FakeClock()
        app = make_app(tmp_path, make_settings(tmp_path), clock)
        async with app.run_test() as pilot:
            training = await start_training(pilot, app)
            session = training.session
            assert session.total_examples >= 2
            for index, plan in enumerate(session.stages[0].problems):
                await wait_until(
                    pilot,
                    lambda index=index: (
                        training._index == index and not training.query_one(Input).disabled
                    ),
                )
                await pilot.press(*str(plan.answer))
                await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, SummaryScreen))
            await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, MenuScreen))
        rows = Stats(tmp_path / "numbra.sqlite3").history()
        assert len(rows) == 1
        assert rows[0].total_examples == session.total_examples
        assert rows[0].correct_answers == session.total_examples
        assert rows[0].timeouts == 0

    asyncio.run(scenario())


def test_cancelled_session_saves_nothing(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            training = await start_training(pilot, app)
            await pilot.press("escape")
            assert "Press Esc again" in plain_text(training.query_one("#feedback", Static))
            await pilot.press("escape")
            await wait_until(pilot, lambda: isinstance(app.screen, MenuScreen))
        assert Stats(tmp_path / "numbra.sqlite3").history() == []

    asyncio.run(scenario())


def test_strict_timeout_is_recorded_and_the_run_completes(tmp_path: Path) -> None:
    async def scenario() -> None:
        clock = FakeClock()
        # The cooldown waits on a gate so the timeout message stays on screen until the test reads it.
        gate = asyncio.Event()

        async def hold(_seconds: float) -> None:
            await gate.wait()

        app = make_app(tmp_path, make_settings(tmp_path), clock, sleeper=hold)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, TrainSetupScreen))
            app.screen.query_one("#strict", Switch).value = True
            app.screen.query_one("#start", Button).focus()
            await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, TrainingScreen))
            training = app.screen
            assert isinstance(training, TrainingScreen)
            session = training.session
            limit = session.time_limit_for(0, 0)
            clock.advance(limit)  # the strict limit is reached without any answer
            await wait_until(
                pilot, lambda: "Time!" in plain_text(training.query_one("#feedback", Static))
            )
            assert training.query_one(Input).disabled
            gate.set()
            for index in range(1, session.total_examples):
                await wait_until(pilot, lambda index=index: training._index == index)
                await pilot.press(*str(session.stages[0].problems[index].answer))
                await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, SummaryScreen))
        history = Stats(tmp_path / "numbra.sqlite3").history()
        assert len(history) == 1
        assert history[0].timeouts == 1
        assert history[0].correct_answers == session.total_examples - 1

    asyncio.run(scenario())


def test_soft_mode_keeps_input_open_after_the_limit(tmp_path: Path) -> None:
    async def scenario() -> None:
        clock = FakeClock()
        app = make_app(tmp_path, make_settings(tmp_path), clock)
        async with app.run_test() as pilot:
            training = await start_training(pilot, app)
            clock.advance(training.session.time_limit_for(0, 0) + 1.5)
            await wait_until(
                pilot, lambda: "Overtime" in plain_text(training.query_one("#clock", Static))
            )
            assert not training.query_one(Input).disabled
            await pilot.press("escape")
            await pilot.press("escape")
            await wait_until(pilot, lambda: isinstance(app.screen, MenuScreen))

    asyncio.run(scenario())


def test_invalid_setup_value_is_shown_inline(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, TrainSetupScreen))
            app.screen.query_one("#duration", Input).value = "0"
            app.screen.query_one("#start", Button).focus()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, TrainSetupScreen)
            assert "at least 1" in plain_text(app.screen.query_one("#error", Static))

    asyncio.run(scenario())


def test_broken_settings_are_reported_on_the_setup_screen(tmp_path: Path) -> None:
    def broken() -> Settings:
        raise ConfigError("numbra.toml: invalid TOML")

    async def scenario() -> None:
        app = NumbraApp(
            settings_loader=broken, database_path=tmp_path / "numbra.sqlite3", clock=FakeClock()
        )
        async with app.run_test() as pilot:
            await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, TrainSetupScreen))
            texts = [plain_text(widget) for widget in app.screen.query(Static)]
            assert any("numbra.toml: invalid TOML" in text for text in texts)
            assert not app.screen.query(Button)

    asyncio.run(scenario())


def test_tricks_screen_lists_every_trick(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            await pilot.pause()
            app.screen.query_one(OptionList).highlighted = 1
            await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, TricksScreen))
            table = app.screen.query_one(DataTable)
            assert table.row_count == len(TRICKS)
            assert [str(column.label) for column in table.columns.values()] == [
                "Trick",
                "Rule",
                "Example",
                "Levels",
            ]

    asyncio.run(scenario())


def test_bare_command_prints_help_without_a_terminal() -> None:
    result = CliRunner().invoke(cli_app, [])
    assert result.exit_code == 0
    assert "Usage" in result.stdout
    assert "challenge" in result.stdout


def test_bare_command_opens_the_tui_on_a_terminal(monkeypatch) -> None:
    launched: list[str] = []

    class FakeApp:
        def run(self) -> None:
            launched.append("run")

    class Terminal:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(numbra.tui, "NumbraApp", FakeApp)
    monkeypatch.setattr(cli_app_module, "sys", SimpleNamespace(stdin=Terminal(), stdout=Terminal()))
    result = CliRunner().invoke(cli_app, [])
    assert result.exit_code == 0
    assert launched == ["run"]
