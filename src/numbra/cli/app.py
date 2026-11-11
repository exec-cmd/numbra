from __future__ import annotations

import asyncio
import logging
import sys
import time
from collections.abc import Sequence
from datetime import date, datetime
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from .._version import __version__
from ..config import (
    ConfigError,
    ConfigManager,
    default_config_paths,
    default_database_path,
    default_log_path,
    format_value,
    get_value,
    list_values,
    set_value,
    unset_value,
)
from ..core.challenge import (
    Challenge,
    ChallengeOptions,
    CompletedTraining,
    TrainingSession,
    grade_for_score,
)
from ..core.funbox import parse_funbox_modes
from ..core.generator import trick_levels
from ..core.models import (
    Difficulty,
    Operation,
    StageKind,
    Topic,
    format_answer,
    parse_operation_selection,
)
from ..core.report import RECOMMENDATION_TEXT, TrainingReport, build_report
from ..core.stats import GroupStats, Stats
from ..core.tricks import TRICKS
from .input import cooldown, timed_prompt
from .logging import configure_logging

logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer(
    add_completion=False,
    invoke_without_command=True,
    help="Train mental arithmetic from your terminal.",
)


def _parse_operations(value: str | None) -> tuple[Operation | Topic, ...] | None:
    if value is None:
        return None
    parts = tuple(item.strip() for item in value.split(",") if item.strip())
    if not parts:
        raise ValueError("operation list must not be empty")
    return parse_operation_selection(parts)


@app.callback()
def callback(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option("--version", help="Show version and exit.")] = False,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show log messages.")] = False,
) -> None:
    configure_logging(default_log_path(), verbose)
    if version:
        console.print(f"numbra {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        # Piped or scripted runs get the help text; only a terminal gets the interactive UI.
        if sys.stdin.isatty() and sys.stdout.isatty():
            from ..tui import NumbraApp

            NumbraApp().run()
        else:
            typer.echo(ctx.get_help())
        raise typer.Exit()


@app.command(help="Answers are integers; exact fractions such as 6/3 are also accepted.")
def challenge(
    duration: Annotated[
        int | None, typer.Option("-t", "--duration", help="Target duration in minutes.", min=1)
    ] = None,
    difficulty: Annotated[
        Difficulty | None, typer.Option("-d", "--difficulty", help="Difficulty level.")
    ] = None,
    seed: Annotated[int | None, typer.Option("-S", "--seed", help="Integer seed.")] = None,
    operations: Annotated[
        str | None,
        typer.Option(
            "-o",
            "--operations",
            help="Comma-separated: +, -, *, /, sqrt, trig, log, power (^ alias), tricks.",
        ),
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
    advanced: Annotated[
        bool | None,
        typer.Option(
            "--advanced/--no-advanced",
            help="Enable all basic operations, advanced topics and identities.",
        ),
    ] = None,
    identities: Annotated[
        bool | None,
        typer.Option("--identities/--no-identities", help="Enable identity problems."),
    ] = None,
    funbox: Annotated[
        str | None,
        typer.Option(
            "--funbox",
            help="Experimental: comma list of fractions, substitution, equations, logic, "
            "derivatives. Replaces the operation selection.",
        ),
    ] = None,
) -> None:
    try:
        selected_operations = _parse_operations(operations)
        funbox_modes = parse_funbox_modes(funbox) if funbox is not None else None
        if funbox_modes is not None:
            if selected_operations is not None or advanced is not None or identities is not None:
                raise ValueError("--funbox cannot be combined with -o, --advanced or --identities")
        settings = ConfigManager().load_or_create()
        session: TrainingSession = Challenge(settings).create_session(
            ChallengeOptions(
                duration_minutes=duration,
                difficulty=difficulty,
                seed=seed,
                operations=selected_operations,
                stages=stages,
                strict=strict,
                cooldown_seconds=cooldown_seconds,
                advanced=advanced,
                identities=identities,
                funbox=funbox_modes,
            )
        )
    except (ConfigError, ValueError) as exc:
        logger.error("Unable to start challenge: %s", exc)
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    for warning in (*settings.warnings, *session.warnings):
        console.print(f"[yellow]Warning:[/yellow] {warning}")
    kinds = ", ".join(
        f"{kind.value}: {sum(stage.kind is kind for stage in session.stages)}" for kind in StageKind
    )
    styles = settings.styles
    accent_style = styles.get("accent", "bold cyan")
    success_style = styles.get("success", "green")
    error_style = styles.get("error", "bold red")
    timer_style = styles.get("timer", "yellow")
    displayed_operations = ", ".join(
        (
            *session.operations,
            *(topic.value for topic in session.topics if topic is not Topic.IDENTITIES),
        )
    )
    if funbox_modes is not None:
        selection = "[bold]Funbox (experimental):[/bold] " + ", ".join(funbox_modes)
    else:
        selection = f"[bold]Operations:[/bold] {displayed_operations}"
    console.print(
        Panel.fit(
            f"[bold]Difficulty:[/bold] {session.difficulty.value}\n"
            f"[bold]Stages:[/bold] {len(session.stages)} · [bold]Examples:[/bold] {session.total_examples}\n"
            f"[bold]Mode:[/bold] {'strict' if session.strict else 'soft'} · "
            f"[bold]Cooldown:[/bold] {session.cooldown_seconds:g}s\n"
            f"{selection} · [bold]Seed:[/bold] {session.seed}",
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
                # Funbox texts end with their own question, so no "=" is added.
                prompt = (
                    f"{problem.expression} "
                    if session.mode == "funbox"
                    else f"{problem.expression} = "
                )
                answer = asyncio.run(timed_prompt(prompt, limit, strict=session.strict))
                elapsed = time.monotonic() - before
                attempt = session.submit(
                    stage_index, problem_index, answer, elapsed, answer is None
                )
                if attempt.timed_out:
                    console.print(f"[{timer_style}]Time![/] {format_answer(problem.answer)}")
                elif attempt.is_correct:
                    console.print(f"[{success_style}]Correct[/] · score {attempt.score:.2f}")
                else:
                    console.print(
                        f"[{error_style}]Incorrect[/] (answer: {format_answer(problem.answer)})"
                    )
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
    # Funbox has no comparable history or progress group, so its summary stands alone.
    is_funbox = completed.mode == "funbox"
    comparable = [] if is_funbox else stats.comparable_history(completed, limit=1)
    progress = [] if is_funbox else stats.progress_history(completed)
    training_id = stats.save(completed)
    logger.info("Challenge %s saved with %s attempts", training_id, len(completed.attempts))
    report = build_report(
        completed,
        comparable[0] if comparable else None,
        progress,
        stats.streak(date.today()),
    )
    _print_summary(completed, report, success_style)


def _print_summary(
    completed: CompletedTraining, report: TrainingReport, success_style: str
) -> None:
    console.print(
        f"\n[bold]Result:[/bold] {completed.correct_answers}/{completed.total_examples} correct "
        f"({completed.accuracy:.1%}), score {completed.score:.2f}/{completed.max_score:.2f} "
        f"({completed.score_percent:.1%}), grade {completed.grade}, level {completed.grade}"
    )
    console.print(
        f"Target duration: {completed.duration_target_seconds:.1f}s · actual: {completed.actual_duration_seconds:.1f}s"
    )
    for tally in report.stage_kinds:
        console.print(
            f"{tally.kind.value}: {tally.correct}/{tally.total} correct, {tally.timeouts} timeouts"
        )
    if report.operations:
        console.print(
            "Operations: "
            + ", ".join(
                f"{operation.value} {tally.correct}/{tally.total}"
                for operation, tally in report.operations
            )
        )
    if report.topics:
        console.print(
            "Topics: "
            + ", ".join(
                f"{topic.value} {tally.correct}/{tally.total}" for topic, tally in report.topics
            )
        )
    if report.comparison is not None:
        prior = report.comparison.previous
        console.print(
            f"Previous comparable: score {prior.score_percent:.1%}, "
            f"accuracy {prior.accuracy:.1%}, average {prior.average_response_seconds:.2f}s, "
            f"timeouts {prior.timeouts}"
        )
        comparison = report.comparison
        console.print(
            f"Delta: score {comparison.score_delta:+.1%} · "
            f"accuracy {comparison.accuracy_delta:+.1%} · "
            f"average {comparison.average_delta:+.2f}s · "
            f"timeouts {comparison.timeouts_delta:+d}"
        )
    if report.average_correct_seconds is not None:
        parts = [f"Avg correct answer: {report.average_correct_seconds:.2f}s"]
        if report.best_correct_seconds is not None:
            parts.append(f"best {report.best_correct_seconds:.2f}s")
        if report.previous_correct_seconds is not None:
            parts.append(f"previous {report.previous_correct_seconds:.2f}s")
        console.print(" · ".join(parts))
    if completed.mode == "challenge":
        if report.is_new_best:
            console.print(f"[{success_style}]New personal best: {completed.score_percent:.1%}![/]")
        else:
            console.print(
                f"Personal best: {report.personal_best:.1%} ({report.score_vs_best:+.1%})"
            )
    console.print(f"Streak: {_days(report.current_streak)} (best {report.longest_streak})")
    if report.recommendation is not None:
        console.print(RECOMMENDATION_TEXT[report.recommendation])


@app.command(help="List the mental-math tricks used by -o tricks.")
def tricks() -> None:
    levels = trick_levels()
    table = Table(title="Mental-math tricks")
    table.add_column("Trick", no_wrap=True)
    for heading in ("Rule", "Example", "Levels"):
        table.add_column(heading)
    for trick in TRICKS:
        table.add_row(
            trick.id,
            trick.rule,
            trick.example,
            ", ".join(level.value for level in levels.get(trick.id, ())),
        )
    console.print(table)


def _days(count: int) -> str:
    return f"{count} day" if count == 1 else f"{count} days"


_SPARK_LEVELS = "▁▂▃▄▅▆▇█"
_GRADE_STYLES = {"S": "bold green", "A": "green", "B": "cyan", "C": "yellow", "D": "red"}


def _sparkline(values: list[float]) -> str:
    """Scores from 0 to 1 as block characters."""
    return "".join(_SPARK_LEVELS[min(7, max(0, round(value * 7)))] for value in values)


def _grade_markup(score_percent: float) -> str:
    grade = grade_for_score(score_percent)
    return f"[{_GRADE_STYLES[grade]}]{grade}[/]"


def _seconds(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}s"


def _group_table(title: str, sections: Sequence[Sequence[GroupStats]]) -> Table:
    table = Table(title=title)
    table.add_column("Group", no_wrap=True)
    for heading in ("Attempts", "Accuracy", "Avg correct"):
        table.add_column(heading, justify="right")
    for section in sections:
        if not section:
            continue
        if table.row_count:
            table.add_section()
        for item in section:
            table.add_row(
                f"{item.kind}: {item.name}",
                str(item.attempts),
                f"{item.accuracy:.1%}",
                _seconds(item.average_correct_seconds),
            )
    return table


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
    funbox = _funbox_table(stats)
    if not rows:
        console.print("No completed challenges yet.")
        if funbox is not None:
            console.print(funbox)
        return
    aggregate = stats.aggregate()
    current, longest = stats.streak(date.today())
    console.print(
        Panel(
            f"[bold]Sessions:[/bold] {aggregate.completed_trainings} · "
            f"[bold]Examples:[/bold] {aggregate.total_examples} · "
            f"[bold]Accuracy:[/bold] {aggregate.accuracy:.1%} · "
            f"[bold]Average answer:[/bold] {aggregate.average_response_seconds:.2f}s\n"
            f"[bold]Streak:[/bold] {_days(current)} (best {longest}) · "
            f"[bold]Last session:[/bold] {_grade_markup(rows[0].score_percent)} "
            f"({rows[0].score_percent:.1%})\n"
            f"[bold]Score trend:[/bold] "
            f"{_sparkline([row.score_percent for row in reversed(rows)])} · "
            f"[bold]Timeouts:[/bold] {aggregate.timeouts}",
            title="Results",
        )
    )
    table = Table(title="History")
    table.add_column("Date", no_wrap=True)
    table.add_column("Difficulty", no_wrap=True)
    for heading in ("Correct", "Accuracy", "Score"):
        table.add_column(heading, justify="right")
    table.add_column("Grade", justify="center")
    table.add_column("Avg", justify="right")
    for row in rows:
        table.add_row(
            datetime.fromtimestamp(row.started_at).astimezone().strftime("%Y-%m-%d %H:%M"),
            row.difficulty,
            f"{row.correct_answers}/{row.total_examples}",
            f"{row.accuracy:.1%}",
            f"{row.score_percent:.1%}",
            _grade_markup(row.score_percent),
            f"{row.average_response_seconds:.2f}s",
        )
    console.print(table)
    breakdown = stats.breakdown()
    console.print(
        _group_table("Breakdown", (breakdown.difficulties, breakdown.operations, breakdown.topics))
    )
    weak = stats.weak_spots()
    if weak:
        console.print(_group_table("Weak spots", (weak,)))
    records = Table(title="Personal records")
    for heading in (
        "Difficulty",
        "Mode",
        "Operations",
        "Sessions",
        "Best score",
        "Best avg correct",
    ):
        records.add_column(heading)
    for record in stats.records():
        records.add_row(
            record.difficulty,
            "strict" if record.strict else "soft",
            ", ".join((*record.operations, *record.topics)),
            str(record.sessions),
            f"{record.best_score_percent:.1%}",
            "—"
            if record.best_average_correct_seconds is None
            else f"{record.best_average_correct_seconds:.2f}s",
        )
    console.print(records)
    trick_rows = stats.trick_stats()
    if trick_rows:
        trick_table = Table(title="Tricks")
        for heading in ("Trick", "Attempts", "Accuracy", "Avg correct"):
            trick_table.add_column(heading)
        for item in trick_rows:
            trick_table.add_row(
                item.strategy,
                str(item.attempts),
                f"{item.correct / item.attempts:.1%}",
                "—"
                if item.average_correct_seconds is None
                else f"{item.average_correct_seconds:.2f}s",
            )
        console.print(trick_table)
    if funbox is not None:
        console.print(funbox)


def _funbox_table(stats: Stats) -> Table | None:
    groups = stats.funbox_stats()
    if not groups:
        return None
    table = Table(title="Funbox (experimental)")
    for heading in ("Mode", "Attempts", "Accuracy", "Avg correct"):
        table.add_column(heading)
    for item in groups:
        table.add_row(
            item.name,
            str(item.attempts),
            f"{item.accuracy:.1%}",
            _seconds(item.average_correct_seconds),
        )
    return table


config_app = typer.Typer(
    no_args_is_help=True, help="Show and change settings in numbra.toml without editing it."
)
app.add_typer(config_app, name="config")


def _plain(text: str) -> None:
    # Values such as ["+", "-"] must not be read as Rich markup, and long paths must not wrap.
    console.print(text, markup=False, highlight=False, soft_wrap=True)


def _config_error(exc: ConfigError) -> NoReturn:
    logger.error("Configuration command failed: %s", exc)
    console.print(f"[red]Configuration error:[/red] {escape(str(exc))}")
    raise typer.Exit(code=2) from exc


@config_app.command("list", help="Show every setting with its effective value.")
def config_list() -> None:
    try:
        values = list_values(default_config_paths())
    except ConfigError as exc:
        _config_error(exc)
    for key, value in values:
        _plain(f"{key} = {format_value(value)}")


@config_app.command("get", help="Show the effective value of one setting.")
def config_get(
    key: Annotated[str, typer.Argument(help="Dotted key, for example challenge.difficulty.")],
) -> None:
    try:
        value = get_value(default_config_paths(), key)
    except ConfigError as exc:
        _config_error(exc)
    _plain("unset" if value is None else format_value(value))


@config_app.command(
    "set",
    context_settings={"ignore_unknown_options": True},
    help='Save a value. Text is read as TOML; quote lists, for example \'["+", "-"]\'.',
)
def config_set(
    key: Annotated[str, typer.Argument(help="Dotted key, for example challenge.difficulty.")],
    value: Annotated[str, typer.Argument(help="New value, for example hard or 42.")],
) -> None:
    paths = default_config_paths()
    try:
        set_value(paths, key, value)
        current = get_value(paths, key)
    except ConfigError as exc:
        _config_error(exc)
    _plain(f"{key} = {format_value(current)}")


@config_app.command("unset", help="Remove a saved value so the built-in default applies again.")
def config_unset(
    key: Annotated[str, typer.Argument(help="Dotted key, for example challenge.seed.")],
) -> None:
    paths = default_config_paths()
    try:
        unset_value(paths, key)
        current = get_value(paths, key)
    except ConfigError as exc:
        _config_error(exc)
    _plain("unset" if current is None else f"{key} = {format_value(current)}")


@config_app.command("path", help="Print the path of numbra.toml.")
def config_path() -> None:
    _plain(str(default_config_paths().main))
