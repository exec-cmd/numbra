"""Focused coverage for the training flow and its shared summary card."""

import asyncio
from io import StringIO
from pathlib import Path
from typing import Any

from rich.console import Console
from test_tui import (
    FakeClock,
    make_app,
    make_settings,
    plain_text,
    start_training,
    wait_until,
)
from textual.widgets import Button, Checkbox, Input, ProgressBar, Static

from numbra.core.challenge import Challenge, ChallengeOptions, TrainingSession
from numbra.core.funbox import FunboxMode
from numbra.core.models import Difficulty, Operation, format_answer
from numbra.core.report import build_report
from numbra.tui.funbox import FunboxSetupScreen
from numbra.tui.results import SessionScreen
from numbra.tui.train import SummaryScreen, TrainingScreen, TrainSetupScreen


async def _answer_all(pilot: Any, training: TrainingScreen) -> None:
    for index, plan in enumerate(training.session.stages[0].problems):
        await wait_until(
            pilot,
            lambda index=index: training._index == index and not training.query_one(Input).disabled,
        )
        await pilot.press(*format_answer(plan.answer))
        await pilot.press("enter")


def test_run_status_progress_and_card_advance(tmp_path: Path) -> None:
    async def scenario() -> None:
        clock = FakeClock()
        gate = asyncio.Event()

        async def hold(_seconds: float) -> None:
            await gate.wait()

        app = make_app(tmp_path, make_settings(tmp_path), clock, sleeper=hold)
        async with app.run_test() as pilot:
            training = await start_training(pilot, app)
            first = training.session.stages[0].problems[0]
            await pilot.press(*format_answer(first.answer))
            await pilot.press("enter")
            await wait_until(
                pilot,
                lambda: "Correct" in plain_text(training.query_one("#feedback", Static)),
            )
            assert "✓ 1" in plain_text(training.query_one("#counts", Static))
            assert training.query_one("#overall", ProgressBar).progress == 1
            gate.set()
            await wait_until(pilot, lambda: training._index == 1)
            assert (
                training.query_one("#card").border_title == f"2/{training.session.total_examples}"
            )

    asyncio.run(scenario())


def test_run_expression_uses_display_multiplication_and_division(tmp_path: Path) -> None:
    async def check(operation: Operation, symbol: str, root: Path) -> None:
        app = make_app(
            root,
            make_settings(root, operations=(operation,)),
            FakeClock(),
        )
        async with app.run_test() as pilot:
            training = await start_training(pilot, app)
            assert symbol in plain_text(training.query_one("#expression", Static))
            await pilot.press("escape")
            await pilot.press("escape")

    async def scenario() -> None:
        await check(Operation.MULTIPLY, "×", tmp_path / "multiply")
        await check(Operation.DIVIDE, "÷", tmp_path / "divide")

    asyncio.run(scenario())


def test_run_low_time_class_appears_below_thirty_percent(tmp_path: Path) -> None:
    async def scenario() -> None:
        clock = FakeClock()
        app = make_app(tmp_path, make_settings(tmp_path), clock)
        async with app.run_test() as pilot:
            training = await start_training(pilot, app)
            limit = training.session.time_limit_for(0, 0)
            clock.advance(limit * 0.71)
            training._tick()
            assert "-low" in training.query_one("#card").classes

    asyncio.run(scenario())


def test_tick_updates_timer_without_advancing_overall_progress(tmp_path: Path) -> None:
    async def scenario() -> None:
        clock = FakeClock()
        app = make_app(tmp_path, make_settings(tmp_path), clock)
        async with app.run_test() as pilot:
            training = await start_training(pilot, app)
            limit = training.session.time_limit_for(0, 0)
            clock.advance(limit / 2)
            training._tick()
            timer = training.query_one("#timer", ProgressBar)
            overall = training.query_one("#overall", ProgressBar)
            assert abs(timer.progress - limit / 2) < 0.1
            assert overall.progress == 0

    asyncio.run(scenario())


def test_training_progress_bars_fill_available_width_at_80_columns(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test(size=(80, 24)) as pilot:
            training = await start_training(pilot, app)
            assert training.query_one("#overall Bar").region.width >= 70
            assert training.query_one("#timer Bar").region.width >= 40
            await pilot.press("escape")
            await pilot.press("escape")

    asyncio.run(scenario())


def test_setup_forms_fit_at_80_columns_without_scrolling(tmp_path: Path) -> None:
    async def scenario() -> None:
        app = make_app(tmp_path, make_settings(tmp_path), FakeClock())
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("t")
            await wait_until(pilot, lambda: isinstance(app.screen, TrainSetupScreen))
            for screen_type, key in ((TrainSetupScreen, "t"), (FunboxSetupScreen, "f")):
                screen = app.screen
                assert isinstance(screen, screen_type)
                start = screen.query_one("#start", Button)
                scroll = screen.query_one("VerticalScroll")
                assert start.region.bottom <= 23
                assert scroll.max_scroll_y == 0
                if key == "t":
                    await pilot.press("escape")
                    await pilot.press("f")
                    await wait_until(pilot, lambda: isinstance(app.screen, FunboxSetupScreen))
                else:
                    await pilot.press("escape")

    asyncio.run(scenario())


def test_summary_review_and_train_again(tmp_path: Path) -> None:
    async def scenario() -> None:
        settings = make_settings(tmp_path, operations=(Operation.ADD, Operation.MULTIPLY))
        app = make_app(tmp_path, settings, FakeClock())
        async with app.run_test() as pilot:
            training = await start_training(pilot, app)
            await _answer_all(pilot, training)
            await wait_until(pilot, lambda: isinstance(app.screen, SummaryScreen))
            summary = app.screen.query_one("#summary", Static)
            buffer = StringIO()
            Console(file=buffer, width=80).print(summary.content)
            card_text = buffer.getvalue()
            for label in ("Score", "Accuracy", "Time", "Streak"):
                assert label in card_text

            await pilot.press("d")
            await wait_until(pilot, lambda: isinstance(app.screen, SessionScreen))
            await pilot.press("escape")
            await wait_until(pilot, lambda: isinstance(app.screen, SummaryScreen))
            await pilot.press("t")
            await wait_until(pilot, lambda: isinstance(app.screen, TrainingScreen))
            repeated = app.screen
            assert repeated.session.difficulty is training.session.difficulty
            assert repeated.session.operations == training.session.operations
            await pilot.press("escape")
            await pilot.press("escape")

    asyncio.run(scenario())


def test_setup_summary_checkbox_label_and_ctrl_s(tmp_path: Path) -> None:
    async def scenario() -> None:
        settings = make_settings(tmp_path, operations=(Operation.ADD, Operation.MULTIPLY))
        app = make_app(tmp_path, settings, FakeClock())
        async with app.run_test() as pilot:
            await pilot.press("enter")
            await wait_until(pilot, lambda: isinstance(app.screen, TrainSetupScreen))
            setup = app.screen
            assert "multiplication" in str(setup._boxes["*"].label)
            assert str(setup.query_one("#strict", Checkbox).label) == (
                "strict: an example ends at its time limit"
            )
            setup.query_one("#duration", Input).value = "2"
            await pilot.pause()
            assert plain_text(setup.query_one("#summary", Static)).startswith("2 min, 1 stages")
            await pilot.press("ctrl+s")
            await wait_until(pilot, lambda: isinstance(app.screen, TrainingScreen))

    asyncio.run(scenario())


def _completed(settings: Any, *, funbox: bool = False):
    options = ChallengeOptions(
        duration_minutes=1,
        stages=1,
        difficulty=Difficulty.EASY,
        seed=42,
        operations=(Operation.ADD,),
        funbox=(FunboxMode.LOGIC,) if funbox else None,
    )
    session: TrainingSession = Challenge(settings).create_session(options)
    for stage_index, stage in enumerate(session.stages):
        for problem_index, problem in enumerate(stage.problems):
            session.submit(stage_index, problem_index, str(problem.answer), 0)
    return session.complete(1)


def test_cli_summary_card_grade_once_and_funbox_without_best(tmp_path: Path) -> None:
    from numbra.cli.summary import summary_card
    from numbra.core.challenge import grade_for_score

    settings = make_settings(tmp_path)
    completed = _completed(settings)
    report = build_report(completed, None, [], (1, 1))
    buffer = StringIO()
    Console(record=True, file=buffer, width=80).print(summary_card(completed, report))
    output = buffer.getvalue()
    grade = grade_for_score(completed.score_percent)
    assert output.count(f"│  {grade}  │") == 1
    assert "level" not in output.lower()

    funbox = _completed(settings, funbox=True)
    funbox_report = build_report(funbox, None, [], (1, 1))
    buffer = StringIO()
    Console(record=True, file=buffer, width=80).print(summary_card(funbox, funbox_report))
    assert "Best" not in buffer.getvalue()
    assert "Funbox (experimental)" in buffer.getvalue()
