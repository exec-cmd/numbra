"""Training screens: setup form, timed run and summary. Rules live in ``core``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    Select,
    Static,
    Switch,
)

from ..config import ConfigError, Settings
from ..core.challenge import (
    Challenge,
    ChallengeOptions,
    CompletedTraining,
    TrainingSession,
    grade_for_score,
)
from ..core.models import Difficulty, Operation, Topic, parse_operation_selection
from ..core.report import RECOMMENDATION_TEXT, TrainingReport, build_report
from ..core.stats import Stats

if TYPE_CHECKING:
    from .app import NumbraApp

# Checkbox tokens, in the same spelling as `numbra challenge -o`.
_TOKENS = ("+", "-", "*", "/", "^", "sqrt", "trig", "log", "tricks", "identities")


def _enabled_by_default(token: str, settings: Settings) -> bool:
    challenge = settings.challenge
    if token == "identities":
        return challenge.features.get(Topic.IDENTITIES, False)
    enabled = {*challenge.operations, *(topic for topic, on in challenge.features.items() if on)}
    member = parse_operation_selection([token])[0]
    return member in enabled or (member is Operation.POWER and Topic.POWER in enabled)


def _whole(text: str, label: str, minimum: int | None = None) -> int:
    try:
        value = int(text)
    except ValueError:
        raise ValueError(f"{label} must be a whole number") from None
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    return value


class TrainSetupScreen(Screen[None]):
    """Form for one training; Start replaces this screen with the run."""

    BINDINGS = [Binding("escape", "back", "Back")]
    DEFAULT_CSS = """
    TrainSetupScreen VerticalScroll { padding: 0 2; }
    TrainSetupScreen Label { margin-top: 1; }
    TrainSetupScreen Input, TrainSetupScreen Select { width: 30; }
    TrainSetupScreen #error { color: $error; margin-top: 1; height: auto; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._settings: Settings | None = None
        self._boxes: dict[str, Checkbox] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        try:
            self._settings = self._numbra().load_settings()
        except ConfigError as exc:
            yield Static(Text(f"Configuration error: {exc}", style="bold red"))
            yield Footer()
            return
        challenge = self._settings.challenge
        with VerticalScroll():
            yield Label("Difficulty")
            yield Select(
                [(level.value, level) for level in Difficulty],
                value=challenge.difficulty,
                allow_blank=False,
                id="difficulty",
            )
            yield Label("Duration in minutes")
            yield Input(str(challenge.duration_minutes), id="duration")
            yield Label("Stages")
            yield Input(str(challenge.stages), id="stages")
            yield Label("Operations and topics")
            for token in _TOKENS:
                box = Checkbox(token, value=_enabled_by_default(token, self._settings))
                self._boxes[token] = box
                yield box
            yield Label("Strict: an example ends at its time limit")
            yield Switch(value=False, id="strict")
            yield Label("Seed (empty for a random seed)")
            yield Input("" if challenge.seed is None else str(challenge.seed), id="seed")
            yield Static("", id="error")
            yield Button("Start", variant="primary", id="start")
        yield Footer()

    def action_back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#start")
    def start(self) -> None:
        try:
            session = self._create_session()
        except (ConfigError, ValueError) as exc:  # GenerationError is a ValueError
            self.query_one("#error", Static).update(Text(str(exc), style="bold red"))
            return
        assert self._settings is not None
        warnings = (*self._settings.warnings, *session.warnings)
        self.app.switch_screen(TrainingScreen(session, warnings))

    def _create_session(self) -> TrainingSession:
        if self._settings is None:
            raise ConfigError("settings are not loaded")
        tokens = [
            token for token, box in self._boxes.items() if token != "identities" and box.value
        ]
        seed_text = self.query_one("#seed", Input).value.strip()
        options = ChallengeOptions(
            duration_minutes=_whole(self.query_one("#duration", Input).value, "Duration", 1),
            stages=_whole(self.query_one("#stages", Input).value, "Stages", 1),
            difficulty=cast(Difficulty, self.query_one("#difficulty", Select).value),
            seed=_whole(seed_text, "Seed") if seed_text else None,
            operations=parse_operation_selection(tokens),
            strict=self.query_one("#strict", Switch).value,
            identities=self._boxes["identities"].value,
        )
        return Challenge(self._settings, clock=self._numbra().clock).create_session(options)

    def _numbra(self) -> NumbraApp:
        return cast("NumbraApp", self.app)


class TrainingScreen(Screen[None]):
    """One timed run: examples in order, cooldown between them, saved only on completion."""

    BINDINGS = [Binding("escape", "cancel", "Cancel (press twice)")]
    DEFAULT_CSS = """
    TrainingScreen #training { padding: 0 2; }
    TrainingScreen #stage { color: $text-muted; margin-top: 1; }
    TrainingScreen #expression {
        text-style: bold; content-align: center middle; height: 5;
        border: heavy $accent; margin: 1 0;
    }
    TrainingScreen #answer { width: 40; }
    TrainingScreen #timer { margin: 1 0 0 0; }
    TrainingScreen #feedback { height: auto; margin-top: 1; }
    """

    def __init__(self, session: TrainingSession, warnings: Sequence[str] = ()) -> None:
        super().__init__()
        self.session = session
        self._warnings = tuple(warnings)
        self._positions = tuple(
            (stage, problem)
            for stage, plan in enumerate(session.stages)
            for problem in range(len(plan.problems))
        )
        self._index = 0
        self._phase = "answer"  # answer -> cooldown -> answer ... -> done
        self._armed = False
        self._example_started = 0.0
        self._session_started = 0.0
        self._timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="training"):
            yield Static(id="stage")
            yield Static(id="example")
            yield Static(id="expression")
            yield Input(placeholder="Answer, then Enter", id="answer")
            yield ProgressBar(total=1, show_eta=False, show_percentage=False, id="timer")
            yield Static(id="clock")
            yield Static(id="feedback")
            if self._warnings:
                yield Static(
                    Text("\n".join(f"Warning: {item}" for item in self._warnings), style="yellow")
                )
        yield Footer()

    def on_mount(self) -> None:
        self._session_started = self._numbra().clock()
        self._timer = self.set_interval(0.1, self._tick)
        self._show_example()

    def on_unmount(self) -> None:
        self._stop_timer()

    def _show_example(self) -> None:
        stage_number, problem_number = self._positions[self._index]
        plan = self.session.stages[stage_number]
        self.query_one("#stage", Static).update(
            f"Stage {plan.number}/{len(self.session.stages)} · {plan.kind.value}"
        )
        self.query_one("#example", Static).update(
            f"Example {self._index + 1}/{len(self._positions)}"
        )
        self.query_one("#expression", Static).update(plan.problems[problem_number].expression)
        self.query_one("#feedback", Static).update("")
        answer = self.query_one("#answer", Input)
        answer.value = ""
        answer.disabled = False
        answer.focus()
        self._example_started = self._numbra().clock()
        self._phase = "answer"
        self._armed = False

    def _tick(self) -> None:
        if self._phase != "answer":
            return
        stage_number, problem_number = self._positions[self._index]
        limit = self.session.time_limit_for(stage_number, problem_number)
        elapsed = self._numbra().clock() - self._example_started
        if self.session.strict and elapsed >= limit:
            self._record(None, elapsed, timed_out=True)
            return
        remaining = limit - elapsed
        self.query_one(ProgressBar).update(total=limit, progress=max(0.0, remaining))
        label = (
            f"Time left: {remaining:.1f}s" if remaining >= 0 else f"Overtime: +{-remaining:.1f}s"
        )
        self.query_one("#clock", Static).update(label)

    @on(Input.Submitted, "#answer")
    def _answered(self, event: Input.Submitted) -> None:
        if self._phase != "answer":
            return
        elapsed = self._numbra().clock() - self._example_started
        self._record(event.value, elapsed, timed_out=False)

    def _record(self, answer: str | None, elapsed: float, timed_out: bool) -> None:
        stage_number, problem_number = self._positions[self._index]
        attempt = self.session.submit(stage_number, problem_number, answer, elapsed, timed_out)
        expected = self.session.stages[stage_number].problems[problem_number].answer
        if attempt.timed_out:
            message = Text.assemble(("Time! ", "bold yellow"), str(expected))
        elif attempt.is_correct:
            message = Text.assemble(("Correct", "bold green"), f" · score {attempt.score:.2f}")
        else:
            message = Text.assemble(("Incorrect", "bold red"), f" (answer: {expected})")
        self._armed = False
        self.query_one("#answer", Input).disabled = True
        if self._index + 1 == len(self._positions):
            self._finish()
            return
        self._phase = "cooldown"
        cooldown = self.session.cooldown_seconds
        self.query_one("#feedback", Static).update(
            Text.assemble(message, f"\nNext example in {cooldown:g}s")
        )
        self.run_worker(self._advance(), exclusive=True)

    async def _advance(self) -> None:
        await self._numbra().sleeper(self.session.cooldown_seconds)
        if self._phase == "cooldown":
            self._index += 1
            self._show_example()

    def action_cancel(self) -> None:
        if self._phase == "done":
            return
        if not self._armed:
            self._armed = True
            self.query_one("#feedback", Static).update("Press Esc again to cancel.")
            return
        self._phase = "done"
        self.session.cancel()
        self.app.pop_screen()

    def _finish(self) -> None:
        # Order matters: the previous comparable and the progress group are read before this
        # training is saved, and the streak is read after, so it counts today's training.
        self._phase = "done"
        self._stop_timer()
        completed = self.session.complete(self._numbra().clock() - self._session_started)
        stats = Stats(self._numbra().database_path)
        previous = stats.comparable_history(completed, limit=1)
        progress = stats.progress_history(completed)
        stats.save(completed)
        streak = stats.streak(self._numbra().today())
        report = build_report(completed, previous[0] if previous else None, progress, streak)
        self.app.switch_screen(SummaryScreen(completed, report))

    def _stop_timer(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _numbra(self) -> NumbraApp:
        return cast("NumbraApp", self.app)


class SummaryScreen(Screen[None]):
    """Result of a completed training; Enter or Esc returns to the menu."""

    BINDINGS = [Binding("enter", "done", "Menu"), Binding("escape", "done", show=False)]
    DEFAULT_CSS = """
    SummaryScreen VerticalScroll { padding: 0 2; }
    """

    def __init__(self, completed: CompletedTraining, report: TrainingReport) -> None:
        super().__init__()
        self._completed = completed
        self._report = report

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Static(_summary_markup(self._completed, self._report))
        yield Footer()

    def action_done(self) -> None:
        self.app.pop_screen()


def _days(count: int) -> str:
    return f"{count} day" if count == 1 else f"{count} days"


def _summary_markup(completed: CompletedTraining, report: TrainingReport) -> str:
    grade = grade_for_score(completed.score_percent)
    lines = [
        f"[bold]Result:[/bold] {completed.correct_answers}/{completed.total_examples} correct "
        f"({completed.accuracy:.1%})",
        f"[bold]Score:[/bold] {completed.score:.2f}/{completed.max_score:.2f} "
        f"({completed.score_percent:.1%}) · [bold]Grade:[/bold] {grade}",
        f"Target duration: {completed.duration_target_seconds:.1f}s · "
        f"actual: {completed.actual_duration_seconds:.1f}s",
        "",
    ]
    for tally in report.stage_kinds:
        lines.append(
            f"{tally.kind.value}: {tally.correct}/{tally.total} correct, {tally.timeouts} timeouts"
        )
    if report.operations:
        lines.append(
            "Operations: "
            + ", ".join(
                f"{op.value} {tally.correct}/{tally.total}" for op, tally in report.operations
            )
        )
    if report.topics:
        lines.append(
            "Topics: "
            + ", ".join(
                f"{topic.value} {tally.correct}/{tally.total}" for topic, tally in report.topics
            )
        )
    if report.comparison is not None:
        prior = report.comparison.previous
        comparison = report.comparison
        lines.append(
            f"Previous comparable: score {prior.score_percent:.1%}, "
            f"accuracy {prior.accuracy:.1%}, average {prior.average_response_seconds:.2f}s, "
            f"timeouts {prior.timeouts}"
        )
        lines.append(
            f"Delta: score {comparison.score_delta:+.1%} · accuracy {comparison.accuracy_delta:+.1%} · "
            f"average {comparison.average_delta:+.2f}s · timeouts {comparison.timeouts_delta:+d}"
        )
    if report.average_correct_seconds is not None:
        parts = [f"Avg correct answer: {report.average_correct_seconds:.2f}s"]
        if report.best_correct_seconds is not None:
            parts.append(f"best {report.best_correct_seconds:.2f}s")
        if report.previous_correct_seconds is not None:
            parts.append(f"previous {report.previous_correct_seconds:.2f}s")
        lines.append(" · ".join(parts))
    if report.is_new_best:
        lines.append(f"[bold green]New personal best: {completed.score_percent:.1%}![/bold green]")
    else:
        lines.append(f"Personal best: {report.personal_best:.1%} ({report.score_vs_best:+.1%})")
    lines.append(f"Streak: {_days(report.current_streak)} (best {report.longest_streak})")
    if report.recommendation is not None:
        lines.append(RECOMMENDATION_TEXT[report.recommendation])
    return "\n".join(lines)
