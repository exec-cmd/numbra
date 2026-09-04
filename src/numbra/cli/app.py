from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from ..config import ConfigError, ConfigManager, default_database_path, default_log_path
from ..core.challenge import Challenge, ChallengeOptions, TrainingSession
from ..core.models import Difficulty, Operation, StageKind
from ..core.stats import Stats
from .input import timed_prompt
from .logging import configure_logging

logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    invoke_without_command=True,
    help="Train mental arithmetic from your terminal.",
)


def _parse_operations(value: str | None) -> tuple[Operation, ...] | None:
    if value is None:
        return None
    parts = tuple(item.strip() for item in value.split(",") if item.strip())
    if not parts:
        raise ValueError("operation list must not be empty")
    try:
        return tuple(Operation(item) for item in parts)
    except ValueError as exc:
        raise ValueError(f"unsupported operation; use +,-,*,/ ({exc})") from exc


@app.callback()
def callback(
    version: Annotated[bool, typer.Option("--version", help="Show version and exit.")] = False,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show log messages.")] = False,
) -> None:
    configure_logging(default_log_path(), verbose)
    if version:
        console.print("numbra 0.1.0")
        raise typer.Exit()


@app.command()
def challenge(
    duration: Annotated[
        int | None, typer.Option("-t", "--duration", help="Target duration in minutes.", min=1)
    ] = None,
    difficulty: Annotated[
        Difficulty | None, typer.Option("-d", "--difficulty", help="Difficulty level.")
    ] = None,
    seed: Annotated[int | None, typer.Option("-S", "--seed", help="Integer seed.")] = None,
    operations: Annotated[
        str | None, typer.Option("-o", "--operations", help="Comma-separated operations.")
    ] = None,
    stages: Annotated[
        int | None, typer.Option("-n", "--stages", help="Number of stages.", min=1)
    ] = None,
) -> None:
    try:
        selected_operations = _parse_operations(operations)
        settings = ConfigManager().load_or_create()
        session: TrainingSession = Challenge(settings).create_session(
            ChallengeOptions(duration, difficulty, seed, selected_operations, stages)
        )
    except (ConfigError, ValueError) as exc:
        logger.error("Unable to start challenge: %s", exc)
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    kinds = ", ".join(
        f"{kind.value}: {sum(stage.kind is kind for stage in session.stages)}" for kind in StageKind
    )
    console.print(f"[bold]Numbra challenge[/bold] · difficulty: {session.difficulty.value}")
    console.print(
        f"Target: {session.target_seconds / 60:g} min · stages: {len(session.stages)} · operations: {', '.join(session.operations)} · seed: {session.seed}"
    )
    console.print(f"Stage distribution: {kinds}")
    started = time.monotonic()
    try:
        for stage_index, stage in enumerate(session.stages):
            console.print(
                f"\n[bold cyan]Stage {stage.number}/{len(session.stages)}[/bold cyan] · {stage.kind.value} · {len(stage.problems)} examples"
            )
            for problem_index, problem in enumerate(stage.problems):
                limit = session.time_limit_for(stage_index, problem_index)
                console.print(f"Limit for this example: {limit:g}s")
                before = time.monotonic()
                answer = asyncio.run(timed_prompt(f"{problem.expression} = ", limit))
                elapsed = time.monotonic() - before
                attempt = session.submit(
                    stage_index, problem_index, answer, elapsed, answer is None
                )
                if attempt.timed_out:
                    console.print(f"[yellow]Time![/yellow] {problem.answer}")
                elif attempt.is_correct:
                    console.print("[green]Correct[/green]")
                else:
                    console.print(f"[red]Incorrect[/red] (answer: {problem.answer})")
    except (KeyboardInterrupt, EOFError):
        session.cancel()
        logger.info("Challenge cancelled")
        console.print("\n[yellow]Challenge cancelled. Nothing was saved.[/yellow]")
        raise typer.Exit(code=130) from None
    completed = session.complete(time.monotonic() - started)
    training_id = Stats(default_database_path()).save(completed)
    logger.info("Challenge %s saved with %s attempts", training_id, len(completed.attempts))
    console.print(
        f"\n[bold]Result:[/bold] {completed.correct_answers}/{completed.total_examples} correct ({completed.accuracy:.1%}), {completed.timeouts} timeouts, average {completed.average_response_seconds:.2f}s"
    )
    console.print(
        f"Target duration: {completed.duration_target_seconds:.1f}s · actual: {completed.actual_duration_seconds:.1f}s"
    )
    for kind in StageKind:
        stage_numbers = {stage.number for stage in completed.stages if stage.kind is kind}
        kind_attempts = [item for item in completed.attempts if item.stage_number in stage_numbers]
        kind_total = sum(len(stage.problems) for stage in completed.stages if stage.kind is kind)
        if kind_total:
            console.print(
                f"{kind.value}: {sum(item.is_correct for item in kind_attempts)}/{kind_total} correct, "
                f"{sum(item.timed_out for item in kind_attempts)} timeouts"
            )
    operation_totals: dict[Operation, list[int]] = {}
    for attempt in completed.attempts:
        totals = operation_totals.setdefault(attempt.operation, [0, 0])
        totals[0] += 1
        totals[1] += int(attempt.is_correct)
    if operation_totals:
        console.print(
            "Operations: "
            + ", ".join(
                f"{operation.value} {values[1]}/{values[0]}"
                for operation, values in sorted(
                    operation_totals.items(), key=lambda item: item[0].value
                )
            )
        )


@app.command()
def results(
    limit: Annotated[
        int, typer.Option("-l", "--limit", help="Number of history rows.", min=1)
    ] = 10,
    reset: Annotated[bool, typer.Option("-r", "--reset", help="Delete all saved results.")] = False,
    yes: Annotated[bool, typer.Option("-y", "--yes", help="Skip reset confirmation.")] = False,
) -> None:
    if yes and not reset:
        console.print("[red]Error:[/red] --yes can only be used with --reset")
        raise typer.Exit(code=2)
    stats = Stats(default_database_path())
    if reset:
        if not yes and not typer.confirm("Delete all completed challenge results?", default=False):
            console.print("Reset cancelled.")
            return
        stats.reset()
        logger.info("All challenge results reset")
        console.print("All challenge results were deleted.")
        return
    rows = stats.history(limit)
    if not rows:
        console.print("No completed challenges yet.")
        return
    table = Table(title="Challenge history")
    for heading in (
        "Date",
        "Difficulty",
        "Stages",
        "Examples",
        "Correct",
        "Accuracy",
        "Avg time",
        "Timeouts",
        "Duration",
    ):
        table.add_column(heading)
    for row in rows:
        table.add_row(
            datetime.fromtimestamp(row.started_at).astimezone().strftime("%Y-%m-%d %H:%M"),
            row.difficulty,
            str(row.stages),
            str(row.total_examples),
            str(row.correct_answers),
            f"{row.accuracy:.1%}",
            f"{row.average_response_seconds:.2f}s",
            str(row.timeouts),
            f"{row.actual_duration_seconds:.1f}s",
        )
    console.print(table)
    aggregate = stats.aggregate()
    console.print(
        f"Completed: {aggregate.completed_trainings} · examples: {aggregate.total_examples} · accuracy: {aggregate.accuracy:.1%} · timeouts: {aggregate.timeouts} · average answer: {aggregate.average_response_seconds:.2f}s"
    )
    if aggregate.by_operation:
        console.print(
            "Operations: "
            + ", ".join(
                f"{op} {correct}/{total}"
                for op, (total, correct) in sorted(aggregate.by_operation.items())
            )
        )
    if aggregate.by_difficulty:
        console.print(
            "Difficulty: "
            + ", ".join(
                f"{level} {correct}/{total}"
                for level, (total, correct) in sorted(aggregate.by_difficulty.items())
            )
        )
