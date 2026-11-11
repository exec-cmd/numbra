import asyncio
from dataclasses import replace

from test_tui import FakeClock, make_app, make_settings, plain_text, save_completed_session
from textual.widgets import Button, Checkbox, ContentSwitcher, DataTable, Static, TabbedContent

from numbra.config import ConfigPaths
from numbra.i18n import MISSES
from numbra.tui.app import MenuScreen
from numbra.tui.funbox import FunboxSetupScreen
from numbra.tui.results import LegendScreen, ResultsScreen, SessionScreen
from numbra.tui.settings import _LABELS, SettingEditor, SettingsScreen
from numbra.tui.train import SummaryScreen, TrainingScreen, TrainSetupScreen
from numbra.tui.tricks import TricksScreen


def test_tui_screens_render_in_russian(tmp_path) -> None:
    async def scenario() -> None:
        save_completed_session(tmp_path)
        settings = replace(make_settings(tmp_path), language="ru")
        gate = asyncio.Event()

        async def hold(_seconds: float) -> None:
            await gate.wait()

        app = make_app(tmp_path, settings, FakeClock(), sleeper=hold)
        MISSES.clear()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, MenuScreen)
            assert "Тренировка" in str(app.screen.query_one("#menu").get_option_at_index(0).prompt)

            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, TrainSetupScreen)
            setup = app.screen
            for step in ("step-start", "step-level", "step-practise", "step-time", "step-review"):
                setup.query_one("#steps", ContentSwitcher).current = step
                await pilot.pause()
            app.screen.query_one("#strict", Checkbox).value = True
            await pilot.pause()
            assert "1 мин" in plain_text(app.screen.query_one("#summary", Static))
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert isinstance(app.screen, TrainingScreen)
            training = app.screen
            training._tick()
            assert " с" in plain_text(training.query_one("#clock", Static))
            training._record(str(training.session.stages[0].problems[0].answer), 0.5, False)
            assert "Верно" in str(training.query_one("#feedback", Static).render())
            gate.set()
            for index in range(1, training.session.total_examples):
                await pilot.pause(0.05)
                gate.clear()
                problem = training.session.stages[0].problems[index]
                training._record(
                    "wrong" if index == 1 else None if index == 2 else str(problem.answer),
                    0.5,
                    index == 2,
                )
                gate.set()
            await pilot.pause(0.2)
            assert isinstance(app.screen, SummaryScreen)
            await pilot.press("enter")
            await pilot.pause()

            for screen in (
                TrainSetupScreen(),
                TricksScreen(),
                FunboxSetupScreen(),
                SettingsScreen(),
                ResultsScreen(),
            ):
                app.push_screen(screen)
                await pilot.pause()
                if type(screen) is TrainSetupScreen:
                    assert screen.query_one("#start", Button).region.bottom <= 23
                    for step in (
                        "step-start",
                        "step-level",
                        "step-practise",
                        "step-time",
                        "step-review",
                    ):
                        screen.query_one("#steps", ContentSwitcher).current = step
                        await pilot.pause()
                if isinstance(screen, FunboxSetupScreen):
                    for step in ("step-level", "step-practise", "step-time", "step-review"):
                        screen.query_one("#steps", ContentSwitcher).current = step
                        await pilot.pause()
                if isinstance(screen, TricksScreen):
                    assert "Умножьте" in str(screen.query_one("#rule", Static).render())
                    table = screen.query_one(DataTable)
                    assert any(
                        any(mark in str(table.get_row_at(index)[2]) for mark in ("Л", "Ср", "Сл"))
                        for index in range(table.row_count)
                    )
                    assert all(
                        not any(mark in str(table.get_row_at(index)[2]) for mark in ("E", "N", "H"))
                        for index in range(table.row_count)
                    )
                    assert any(
                        "×" in str(table.get_row_at(index)[1]) for index in range(table.row_count)
                    )
                if isinstance(screen, SettingsScreen):
                    assert (
                        plain_text(screen.query_one("#path", Static)).count("Файл конфигурации:")
                        == 1
                    )
                if isinstance(screen, ResultsScreen):
                    assert "сесс" in plain_text(screen.query_one("#tile-sessions", Static))
                    tabs = screen.query_one(TabbedContent)
                    for active in ("overview-tab", "sessions-tab", "skills-tab"):
                        tabs.active = active
                        await pilot.pause()
                    app.push_screen(LegendScreen())
                    await pilot.pause()
                    assert app.screen.query_one("#legend", Static).region.bottom <= 23
                    await pilot.press("escape")
                    await pilot.pause()
                    table = screen.query_one("#sessions", DataTable)
                    if table.row_count:
                        record = screen._sessions[0]
                        app.push_screen(SessionScreen(record))
                        await pilot.pause()
                        assert " из " in plain_text(
                            app.screen.query_one("#session-summary", Static)
                        )
                        await pilot.press("escape")
                        await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()

            paths = ConfigPaths.from_root(tmp_path / "config")
            for key, current in (("challenge.difficulty", "normal"), ("ui.language", "ru")):
                _, label, help_text = _LABELS[key]
                app.push_screen(SettingEditor(paths, key, label, help_text, current))
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()

            assert MISSES == set(), f"Untranslated TUI strings: {sorted(MISSES)}"

    asyncio.run(scenario())
