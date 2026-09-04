from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..config import ConfigError, ConfigManager, default_database_path, default_log_path
from ..core.challenge import Challenge, ChallengeOptions, TrainingSession, grade_for_score
from ..core.models import Difficulty, Operation, StageKind
from ..core.stats import Stats
from .input import cooldown, timed_prompt
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
        raise ValueError(f"unsupported operation; use +,-,*,/,^ ({exc})") from exc


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
    strict: Annotated[
        bool, typer.Option("--strict", help="Fail immediately when an example reaches its limit.")
    ] = False,
    cooldown_seconds: Annotated[
        float,
        typer.Option(
            "--cooldown",
            help="Seconds between examples (1-3).",
            min=1.0,
            max=3.0,
        ),
    ] = 2.0,
) -> None:
    try:
        selected_operations = _parse_operations(operations)
        settings = ConfigManager().load_or_create()
        session: TrainingSession = Challenge(settings).create_session(
            ChallengeOptions(
                duration,
                difficulty,
                seed,
                selected_operations,
                stages,
                strict,
                cooldown_seconds,
            )
        )
    except (ConfigError, ValueError) as exc:
        logger.error("Unable to start challenge: %s", exc)
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    kinds = ", ".join(
        f"{kind.value}: {sum(stage.kind is kind for stage in session.stages)}" for kind in StageKind
    )
    styles = settings.styles
    accent_style = styles.get("accent", "bold cyan")
    success_style = styles.get("success", "green")
    error_style = styles.get("error", "bold red")
    timer_style = styles.get("timer", "yellow")
    console.print(
        Panel.fit(
            f"[bold]Difficulty:[/bold] {session.difficulty.value}\n"
            f"[bold]Stages:[/bold] {len(session.stages)} · [bold]Examples:[/bold] {session.total_examples}\n"
            f"[bold]Mode:[/bold] {'strict' if session.strict else 'soft'} · "
            f"[bold]Cooldown:[/bold] {session.cooldown_seconds:g}s\n"
            f"[bold]Operations:[/bold] {', '.join(session.operations)} · [bold]Seed:[/bold] {session.seed}",
            title="Numbra challenge",
            border_style=accent_style,
        )
    )
    console.print(f"Planned active budget: up to {session.target_seconds / 60:g} min · {kinds}")
    started = time.monotonic()
    example_number = 0
    try:
        for stage_index, stage in enumerate(session.stages):
            console.print(
                f"\n[{accent_style}]Stage {stage.number}/{len(session.stages)}[/] · "
                f"{stage.kind.value} · {len(stage.problems)} examples"
            )
            for problem_index, problem in enumerate(stage.problems):
                example_number += 1
                limit = session.time_limit_for(stage_index, problem_index)
                console.print(
                    f"[bold]Example {example_number}/{session.total_examples}[/bold] · "
                    f"limit {limit:g}s"
                )
                before = time.monotonic()
                answer = asyncio.run(
                    timed_prompt(f"{problem.expression} = ", limit, strict=session.strict)
                )
                elapsed = time.monotonic() - before
                attempt = session.submit(
                    stage_index, problem_index, answer, elapsed, answer is None
                )
                if attempt.timed_out:
                    console.print(f"[{timer_style}]Time![/] {problem.answer}")
                elif attempt.is_correct:
                    console.print(f"[{success_style}]Correct[/] · score {attempt.score:.2f}")
                else:
                    console.print(f"[{error_style}]Incorrect[/] (answer: {problem.answer})")
                if example_number < session.total_examples:
                    console.print(f"[dim]Next example in {session.cooldown_seconds:g}s[/dim]")
                    asyncio.run(cooldown(session.cooldown_seconds))
    except (KeyboardInterrupt, EOFError):
        session.cancel()
        logger.info("Challenge cancelled")
        console.print("\n[yellow]Challenge cancelled. Nothing was saved.[/yellow]")
        raise typer.Exit(code=130) from None
    completed = session.complete(time.monotonic() - started)
    stats = Stats(default_database_path())
    previous = stats.comparable_history(completed, limit=2)
    training_id = stats.save(completed)
    logger.info("Challenge %s saved with %s attempts", training_id, len(completed.attempts))
    console.print(
        f"\n[bold]Result:[/bold] {completed.correct_answers}/{completed.total_examples} correct "
        f"({completed.accuracy:.1%}), score {completed.score:.2f}/{completed.max_score:.0f} "
        f"({completed.score_percent:.1%}), grade {completed.grade}, level {completed.grade}"
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
        stage = completed.stages[attempt.stage_number - 1]
        problem = stage.problems[attempt.problem_number - 1]
        for operation in problem.operations:
            totals = operation_totals.setdefault(operation, [0, 0])
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
    if previous:
        prior = previous[0]
        console.print(
            f"Previous comparable: score {prior.score_percent:.1%}, "
            f"accuracy {prior.accuracy:.1%}, average {prior.average_response_seconds:.2f}s, "
            f"timeouts {prior.timeouts}"
        )
        console.print(
            f"Delta: score {(completed.score_percent - prior.score_percent):+.1%} · "
            f"accuracy {(completed.accuracy - prior.accuracy):+.1%} · "
            f"average {(completed.average_response_seconds - prior.average_response_seconds):+.2f}s · "
            f"timeouts {completed.timeouts - prior.timeouts:+d}"
        )
    if len(previous) >= 2:
        scores = [completed.score_percent, *(row.score_percent for row in previous[:2])]
        if all(score >= 0.85 for score in scores):
            console.print("Recommendation: try the next difficulty level.")
        elif all(score < 0.40 for score in scores):
            console.print("Recommendation: repeat or lower the difficulty level.")
        else:
            console.print("Recommendation: keep the current difficulty level.")


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
        "Score",
        "Grade",
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
            f"{row.score_percent:.1%}",
            grade_for_score(row.score_percent),
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
