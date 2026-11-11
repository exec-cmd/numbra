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
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Input,
    OptionList,
    Select,
    Static,
    TabbedContent,
)
from typer.testing import CliRunner

import numbra.tui
from numbra.config import ConfigError, ConfigManager, ConfigPaths, Settings, get_value, set_value
from numbra.core.challenge import Challenge, ChallengeOptions
from numbra.core.funbox import FunboxMode
from numbra.core.models import Difficulty, Operation, format_answer
from numbra.core.stats import Stats
from numbra.core.tricks import TRICKS
from numbra.tui.app import MENU, MenuScreen, NumbraApp, terminal_theme
from numbra.tui.funbox import FunboxSetupScreen
from numbra.tui.results import ResultsScreen, SessionScreen
from numbra.tui.settings import SettingsScreen
from numbra.tui.train import (
    FUNBOX_TITLE,
    SummaryScreen,
    TrainingScreen,
    TrainSetupScreen,
)
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
        config_paths=ConfigPaths.from_root(tmp_path / "config"),
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
            assert labels == [f"{key}  {label}" for _, label, key, _, _ in MENU]
            assert labels == [
                "t  Train",
                "r  Results",
                "s  Settings",
                "k  Tricks",
                "f  Funbox",
                "q  Quit",
            ]

    asyncio.run(scenario())


def test_theme_follows_the_terminal_background() -> None:
    assert terminal_theme("0;15") == "ansi-light"
    assert terminal_theme("15;0") == "ansi-dark"
    assert terminal_theme("") == "ansi-dark"  # unknown background


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
            app.screen.query_one("#strict", Checkbox).value = True
            app.screen.query_one("#start", Button).focus()
            await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, TrainingScreen))
            training = app.screen
            assert isinstance(training, TrainingScreen)
            session = training.session
            limit = session.time_limit_for(0, 0)
            clock.advance(limit)  # the strict limit is reached without any answer
            await wait_until(
                pilot, lambda: "Time's up" in plain_text(training.query_one("#feedback", Static))
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
                pilot, lambda: "over" in plain_text(training.query_one("#clock", Static))
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
            app.screen.query_one(OptionList).highlighted = 3  # Menu: Tricks
            await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, TricksScreen))
            table = app.screen.query_one(DataTable)
            assert table.row_count == len(TRICKS)
            assert [str(column.label) for column in table.columns.values()] == [
                "Trick",
                "Problem",
                "Levels",
            ]
            rule = app.screen.query_one("#rule", Static)
            await wait_until(pilot, lambda: TRICKS[0].rule in plain_text(rule))
            await pilot.press("down")
            await wait_until(pilot, lambda: TRICKS[1].rule in plain_text(rule))

    asyncio.run(scenario())


def save_completed_session(tmp_path: Path) -> int:
    session = Challenge(make_settings(tmp_path)).create_session(
        ChallengeOptions(seed=42, stages=1, operations=(Operation.ADD,))
    )
    for index, problem in enumerate(session.stages[0].problems):
        session.submit(0, index, str(problem.answer), 0.5)
    Stats(tmp_path / "numbra.sqlite3").save(session.complete(actual_duration=1.0))
    return session.total_examples


async def open_results(pilot: Pilot[Any], app: NumbraApp) -> ResultsScreen:
    app.screen.query_one(OptionList).highlighted = 1  # Menu: Results
    await pilot.press("enter")
    await wait_until(pilot, lambda: isinstance(app.screen, ResultsScreen))
    screen = app.screen
    assert isinstance(screen, ResultsScreen)
    return screen


def test_results_without_sessions_shows_the_empty_message(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            results = await open_results(pilot, app)
            await wait_until(pilot, lambda: results.query_one("#empty").display)
            assert plain_text(results.query_one("#empty", Static)) == (
                "No finished trainings yet. Choose Train in the menu, finish a run, and your results appear here."
            )
            assert not results.query_one("#tabs").display

    asyncio.run(scenario())


async def open_settings(pilot: Pilot[Any], app: NumbraApp) -> SettingsScreen:
    await pilot.pause()
    app.screen.query_one(OptionList).highlighted = 2  # Menu: Settings
    await pilot.press("enter")
    await wait_until(pilot, lambda: isinstance(app.screen, SettingsScreen))
    screen = app.screen
    assert isinstance(screen, SettingsScreen)
    return screen


async def edit_difficulty(pilot: Pilot[Any], screen: SettingsScreen, text: str) -> None:
    table = screen.query_one(DataTable)
    table.move_cursor(row=table.get_row_index("challenge.difficulty"))
    await pilot.press("enter")
    await wait_until(pilot, lambda: screen.app.screen is not screen)
    options = screen.app.screen.query_one("#value", OptionList)
    options.highlighted = ["easy", "normal", "hard"].index(text)
    await pilot.press("enter")


def test_settings_table_lists_effective_values(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            table = screen.query_one(DataTable)
            keys = [row.key.value for row in table.ordered_rows]
            assert "challenge.difficulty" in keys
            assert table.get_row("challenge.difficulty")[1] == "normal"

    asyncio.run(scenario())


def test_results_history_opens_a_session_and_escape_returns(tmp_path: Path) -> None:
    async def scenario() -> None:
        total = save_completed_session(tmp_path)
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            results = await open_results(pilot, app)
            assert results.query_one("#sessions", DataTable).row_count == 1
            results.query_one(TabbedContent).active = "sessions-tab"
            await wait_until(pilot, lambda: app.focused is results.query_one("#sessions"))
            await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, SessionScreen))
            assert app.screen.query_one("#attempts", DataTable).row_count == total
            await pilot.press("escape")
            await wait_until(pilot, lambda: isinstance(app.screen, ResultsScreen))
            await pilot.press("escape")
            await wait_until(pilot, lambda: isinstance(app.screen, MenuScreen))

    asyncio.run(scenario())


def test_settings_edit_saves_and_refreshes(tmp_path: Path) -> None:
    async def scenario() -> None:
        paths = ConfigPaths.from_root(tmp_path / "config")
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            await edit_difficulty(pilot, screen, "hard")
            await wait_until(pilot, lambda: app.screen is screen)
            assert get_value(paths, "challenge.difficulty") == "hard"
            assert screen.query_one(DataTable).get_row("challenge.difficulty")[1] == "hard"

    asyncio.run(scenario())


def test_settings_invalid_value_is_shown_and_nothing_is_written(tmp_path: Path) -> None:
    async def scenario() -> None:
        paths = ConfigPaths.from_root(tmp_path / "config")
        settings = make_settings(tmp_path)  # creates numbra.toml
        before = paths.main.read_bytes()
        app = make_app(tmp_path, settings, FakeClock())
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            table = screen.query_one(DataTable)
            table.move_cursor(row=table.get_row_index("challenge.stages"))
            await pilot.press("enter")
            await wait_until(pilot, lambda: app.screen is not screen)
            editor = app.screen
            editor.query_one("#value", Input).value = "abc"
            await pilot.press("enter")
            await wait_until(
                pilot, lambda: plain_text(editor.query_one("#modal-error", Static)) != ""
            )
            assert "Enter a whole number" in plain_text(editor.query_one("#modal-error", Static))
            assert get_value(paths, "challenge.stages") == 3
            await pilot.press("escape")
            await wait_until(pilot, lambda: app.screen is screen)
            assert isinstance(app.screen, SettingsScreen)
            await pilot.press("escape")
            await wait_until(pilot, lambda: isinstance(app.screen, MenuScreen))
        assert paths.main.read_bytes() == before

    asyncio.run(scenario())


def test_results_tabs_show_saved_statistics(tmp_path: Path) -> None:
    async def scenario() -> None:
        total = save_completed_session(tmp_path)
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            results = await open_results(pilot, app)
            assert results.query_one("#skills", DataTable).row_count > 0
            assert results.query_one("#bests", DataTable).row_count == 1
            # One session has no miss and fewer than five attempts, so no weak spot.
            assert "Nothing stands out yet" in plain_text(results.query_one("#practice", Static))
            last = plain_text(results.query_one("#last", Static))
            assert f"{total} of {total} correct" in last
            # The trend needs two sessions; the hint takes its place.
            assert not results.query_one("#trend", Static).display
            assert results.query_one("#trend-hint").display

    asyncio.run(scenario())


def test_settings_reset_restores_the_default(tmp_path: Path) -> None:
    async def scenario() -> None:
        paths = ConfigPaths.from_root(tmp_path / "config")
        set_value(paths, "challenge.difficulty", "hard")
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            table = screen.query_one(DataTable)
            table.move_cursor(row=table.get_row_index("challenge.difficulty"))
            await pilot.press("d")
            await wait_until(
                pilot,
                lambda: screen.query_one(DataTable).get_row("challenge.difficulty")[1] == "normal",
            )
        assert get_value(paths, "challenge.difficulty") == "normal"

    asyncio.run(scenario())


def test_results_reload_shows_sessions_saved_while_open(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            results = await open_results(pilot, app)
            await wait_until(pilot, lambda: results.query_one("#empty").display)
            save_completed_session(tmp_path)
            await pilot.press("r")
            await wait_until(
                pilot, lambda: results.query_one("#sessions", DataTable).row_count == 1
            )
            assert not results.query_one("#empty").display

    asyncio.run(scenario())


def test_settings_reset_of_an_unset_seed_removes_its_row(tmp_path: Path) -> None:
    async def scenario() -> None:
        paths = ConfigPaths.from_root(tmp_path / "config")
        set_value(paths, "challenge.seed", "42")
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            table = screen.query_one(DataTable)
            table.move_cursor(row=table.get_row_index("challenge.seed"))
            await pilot.press("d")
            await wait_until(
                pilot, lambda: "challenge.seed" not in [r.key.value for r in table.ordered_rows]
            )
            assert get_value(paths, "challenge.seed") is None

    asyncio.run(scenario())


def test_train_setup_reads_the_changed_setting(tmp_path: Path) -> None:
    async def scenario() -> None:
        paths = ConfigPaths.from_root(tmp_path / "config")
        app = NumbraApp(config_paths=paths, database_path=tmp_path / "numbra.sqlite3")
        async with app.run_test() as pilot:
            screen = await open_settings(pilot, app)
            await edit_difficulty(pilot, screen, "hard")
            await wait_until(pilot, lambda: app.screen is screen)
            await pilot.press("escape")
            await wait_until(pilot, lambda: isinstance(app.screen, MenuScreen))
            app.screen.query_one(OptionList).highlighted = 0
            await pilot.press("enter")  # Menu: Train
            await wait_until(pilot, lambda: isinstance(app.screen, TrainSetupScreen))
            assert app.screen.query_one("#difficulty", Select).value == Difficulty.HARD

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


def save_funbox_session(tmp_path: Path) -> int:
    session = Challenge(make_settings(tmp_path)).create_session(
        ChallengeOptions(seed=42, stages=1, funbox=(FunboxMode.LOGIC,))
    )
    for index, problem in enumerate(session.stages[0].problems):
        session.submit(0, index, format_answer(problem.answer), 0.5)
    Stats(tmp_path / "numbra.sqlite3").save(session.complete(actual_duration=1.0))
    return session.total_examples


async def open_funbox(pilot: Pilot[Any], app: NumbraApp) -> FunboxSetupScreen:
    await pilot.pause()
    app.screen.query_one(OptionList).highlighted = 4  # Menu: Funbox
    await pilot.press("enter")
    await wait_until(pilot, lambda: isinstance(app.screen, FunboxSetupScreen))
    screen = app.screen
    assert isinstance(screen, FunboxSetupScreen)
    return screen


async def start_funbox(pilot: Pilot[Any], app: NumbraApp) -> TrainingScreen:
    screen = await open_funbox(pilot, app)
    screen.query_one("#start", Button).focus()
    await pilot.press("enter")
    await wait_until(pilot, lambda: isinstance(app.screen, TrainingScreen))
    training = app.screen
    assert isinstance(training, TrainingScreen)
    return training


def test_funbox_setup_without_a_mode_shows_the_error(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            screen = await open_funbox(pilot, app)
            assert screen.title == FUNBOX_TITLE
            boxes = list(screen.query("#choices Checkbox"))
            assert len(boxes) == len(FunboxMode)
            assert not any(box.value for box in boxes)
            screen.query_one("#start", Button).focus()
            await pilot.press("enter")
            await wait_until(
                pilot, lambda: "funbox mode" in plain_text(screen.query_one("#error", Static))
            )
            assert isinstance(app.screen, FunboxSetupScreen)

    asyncio.run(scenario())


def test_funbox_session_is_saved_outside_the_training_history(tmp_path: Path) -> None:
    async def scenario() -> None:
        settings = make_settings(tmp_path, funbox_modes=(FunboxMode.LOGIC,))
        app = make_app(tmp_path, settings, FakeClock())
        async with app.run_test() as pilot:
            training = await start_funbox(pilot, app)
            session = training.session
            assert session.mode == "funbox"
            assert training.title == FUNBOX_TITLE
            for index, problem in enumerate(session.stages[0].problems):
                await wait_until(
                    pilot,
                    lambda index=index: (
                        training._index == index and not training.query_one(Input).disabled
                    ),
                )
                await pilot.press(*format_answer(problem.answer))
                await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, SummaryScreen))
            assert app.screen.title == FUNBOX_TITLE
            summary = " ".join(plain_text(widget) for widget in app.screen.query(Static))
            assert "Personal best" not in summary
            assert "Recommendation" not in summary
            await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, MenuScreen))
        stats = Stats(tmp_path / "numbra.sqlite3")
        assert stats.history() == []
        saved = stats.funbox_history()
        assert len(saved) == 1
        assert saved[0].correct_answers == session.total_examples
        assert [group.name for group in stats.funbox_stats()] == ["logic"]

    asyncio.run(scenario())


def test_cancelled_funbox_session_saves_nothing(tmp_path: Path) -> None:
    async def scenario() -> None:
        settings = make_settings(tmp_path, funbox_modes=(FunboxMode.LOGIC,))
        app = make_app(tmp_path, settings, FakeClock())
        async with app.run_test() as pilot:
            training = await start_funbox(pilot, app)
            await pilot.press("escape")
            await pilot.press("escape")
            await wait_until(pilot, lambda: isinstance(app.screen, MenuScreen))
            assert training.session.mode == "funbox"
        assert Stats(tmp_path / "numbra.sqlite3").funbox_history() == []

    asyncio.run(scenario())


def test_results_sessions_lists_saved_funbox_sessions(tmp_path: Path) -> None:
    async def scenario() -> None:
        total = save_funbox_session(tmp_path)
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            results = await open_results(pilot, app)
            await wait_until(pilot, lambda: results.query_one("#tabs").display)
            assert not results.query_one("#empty").display
            assert results.query_one("#sessions", DataTable).row_count == 1
            assert "funbox:" in str(results.query_one("#sessions", DataTable).get_row_at(0)[1])
            results.query_one(TabbedContent).active = "sessions-tab"
            await pilot.pause()
            results.query_one("#sessions", DataTable).focus()
            await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, SessionScreen))
            assert app.screen.query_one("#attempts", DataTable).row_count == total

    asyncio.run(scenario())
