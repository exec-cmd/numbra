"""Focused coverage for the consolidated results screens."""

import asyncio
import sqlite3

from test_tui import (
    FakeClock,
    make_app,
    make_settings,
    open_results,
    plain_text,
    save_completed_session,
    save_funbox_session,
    wait_until,
)
from textual.widgets import DataTable, Static, TabbedContent

from numbra.core.challenge import Challenge, ChallengeOptions
from numbra.core.models import Operation
from numbra.core.report import METRIC_HELP
from numbra.core.stats import Stats
from numbra.tui.results import LegendScreen, ResultsScreen, SessionScreen


def test_results_has_three_tabs_and_merges_sessions_newest_first(tmp_path) -> None:
    async def scenario() -> None:
        save_completed_session(tmp_path)
        save_funbox_session(tmp_path)
        with sqlite3.connect(tmp_path / "numbra.sqlite3") as connection:
            connection.execute("UPDATE trainings SET started_at = 100 WHERE mode = 'challenge'")
            connection.execute("UPDATE trainings SET started_at = 200 WHERE mode = 'funbox'")
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            results = await open_results(pilot, app)
            tabs = results.query_one(TabbedContent).query("TabPane")
            assert [pane.id for pane in tabs] == ["overview-tab", "sessions-tab", "skills-tab"]
            table = results.query_one("#sessions", DataTable)
            assert table.row_count == 2
            assert "funbox:" in str(table.get_row_at(0)[1])
            assert "funbox:" not in str(table.get_row_at(1)[1])

    asyncio.run(scenario())


def test_overview_time_uses_correct_attempts_only(tmp_path) -> None:
    async def scenario() -> None:
        session = Challenge(make_settings(tmp_path)).create_session(
            ChallengeOptions(seed=42, stages=1, operations=(Operation.ADD,))
        )
        for index, problem in enumerate(session.stages[0].problems):
            answer = str(problem.answer + 1) if index == 0 else str(problem.answer)
            elapsed = 18.0 if index == 0 else 2.0
            session.submit(0, index, answer, elapsed)
        Stats(tmp_path / "numbra.sqlite3").save(session.complete(actual_duration=20.0))
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            results = await open_results(pilot, app)
            assert "2.0 s" in plain_text(results.query_one("#tile-time", Static))

    asyncio.run(scenario())


def test_funbox_does_not_change_overview_session_count(tmp_path) -> None:
    async def scenario() -> None:
        save_funbox_session(tmp_path)
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            results = await open_results(pilot, app)
            assert "0" in plain_text(results.query_one("#tile-sessions", Static))

    asyncio.run(scenario())


def test_overview_tiles_fit_three_lines_at_80_by_24(tmp_path) -> None:
    async def scenario() -> None:
        save_completed_session(tmp_path)
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test(size=(80, 24)) as pilot:
            results = await open_results(pilot, app)
            assert results.query_one("#tile-time", Static).region.height == 3

    asyncio.run(scenario())


def test_skills_has_operations_and_funbox_sections(tmp_path) -> None:
    async def scenario() -> None:
        save_completed_session(tmp_path)
        save_funbox_session(tmp_path)
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            results = await open_results(pilot, app)
            table = results.query_one("#skills", DataTable)
            labels = [table.get_row_at(index)[0].plain for index in range(table.row_count)]
            assert "Operations" in labels
            assert "Funbox (experimental)" in labels

    asyncio.run(scenario())


def test_funbox_session_detail_keeps_funbox_setup_label(tmp_path) -> None:
    async def scenario() -> None:
        save_funbox_session(tmp_path)
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            results = await open_results(pilot, app)
            results.query_one(TabbedContent).active = "sessions-tab"
            results.query_one("#sessions", DataTable).focus()
            await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, SessionScreen))
            summary = plain_text(app.screen.query_one("#session-summary", Static))
            assert "funbox:" in summary

    asyncio.run(scenario())


def test_question_mark_opens_and_escape_closes_metric_legend(tmp_path) -> None:
    async def scenario() -> None:
        save_completed_session(tmp_path)
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test() as pilot:
            await open_results(pilot, app)
            await pilot.press("?")
            await wait_until(pilot, lambda: isinstance(app.screen, LegendScreen))
            content = plain_text(app.screen.query_one("#legend", Static))
            assert all(name in content for name in METRIC_HELP)
            await pilot.press("escape")
            await wait_until(pilot, lambda: isinstance(app.screen, ResultsScreen))

    asyncio.run(scenario())


def test_session_numbers_continue_across_stages_and_m_filters_correct_rows(tmp_path) -> None:
    async def scenario() -> None:
        session = Challenge(make_settings(tmp_path, stages=2)).create_session(
            ChallengeOptions(seed=42, stages=2, operations=(Operation.ADD,))
        )
        for stage_index, stage in enumerate(session.stages):
            for problem_index, problem in enumerate(stage.problems):
                answer = (
                    str(problem.answer + 1)
                    if (stage_index == 0 or stage_index == 1) and problem_index == 0
                    else str(problem.answer)
                )
                session.submit(stage_index, problem_index, answer, 0.5)
        Stats(tmp_path / "numbra.sqlite3").save(session.complete(actual_duration=1.0))
        app = make_app(tmp_path, make_settings(tmp_path, stages=2), FakeClock())
        async with app.run_test() as pilot:
            results = await open_results(pilot, app)
            results.query_one(TabbedContent).active = "sessions-tab"
            results.query_one("#sessions", DataTable).focus()
            await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, SessionScreen))
            table = app.screen.query_one("#attempts", DataTable)
            assert table.get_row_at(table.row_count - 1)[0].plain == str(session.total_examples)
            assert plain_text(app.screen.query_one("#session-note", Static)) == (
                "✗ 2 mistakes   (m: show mistakes only)"
            )
            await pilot.press("m")
            assert table.row_count == 2
            assert table.get_row_at(0)[0].plain == "1"
            assert plain_text(app.screen.query_one("#session-note", Static)) == (
                "Showing mistakes only (m: show all)"
            )

    asyncio.run(scenario())
