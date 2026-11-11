"""Training screens: setup form, timed run and summary. Rules live in ``core``."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, cast

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.content import Content
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
)

from ..cli.summary import summary_card
from ..config import ConfigError, Settings
from ..core.challenge import (
    Challenge,
    ChallengeOptions,
    CompletedTraining,
    TrainingSession,
)
from ..core.models import (
    Difficulty,
    Operation,
    Topic,
    format_answer,
    parse_operation_selection,
)
from ..core.report import OPERATION_SYMBOLS, TrainingReport, area_name, build_report
from ..core.stats import Stats, TrainingRecord
from .style import display_expression

if TYPE_CHECKING:
    from .app import NumbraApp

# Checkbox tokens, in the same spelling as `numbra challenge -o`.
_TOKENS = ("+", "-", "*", "/", "^", "sqrt", "trig", "log", "tricks", "identities")
FUNBOX_TITLE = "Funbox (experimental)"


def _enabled_by_default(token: str, settings: Settings) -> bool:
    challenge = settings.challenge
    if token == "identities":
        return challenge.features.get(Topic.IDENTITIES, False)
    enabled = {*challenge.operations, *(topic for topic, on in challenge.features.items() if on)}
    member = parse_operation_selection([token])[0]
    return member in enabled or (member is Operation.POWER and Topic.POWER in enabled)


class Tick(Checkbox):
    """Checkbox drawn as [x] or [ ], so its state does not depend on color alone."""

    @property
    def _button(self) -> Content:
        # shortcut: overrides a private Textual property; re-check on a Textual upgrade.
        mark = "[x] " if self.value else "[ ] "
        return Content.assemble((mark, self.get_visual_style("toggle--button")))


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

    BINDINGS = [Binding("escape", "back", "Back"), Binding("ctrl+s", "start", "Start")]
    SUB_TITLE = "New training"
    CHOICES_LABEL = "Operations and topics"
    DEFAULT_CSS = """
    TrainSetupScreen VerticalScroll { padding: 1 2; }
    TrainSetupScreen .row { height: 1; }
    TrainSetupScreen .row Label { width: 11; height: 1; content-align: left middle; }
    TrainSetupScreen .row .after { width: auto; margin-left: 3; padding-right: 1; }
    TrainSetupScreen #difficulty { width: 16; }
    TrainSetupScreen #duration, TrainSetupScreen #stages { width: 7; }
    TrainSetupScreen #seed { width: 16; }
    TrainSetupScreen #strict { margin-left: 3; }
    TrainSetupScreen Checkbox, TrainSetupScreen Checkbox:focus { border: none; }
    TrainSetupScreen .section {
        border: round $panel-lighten-2; height: auto; padding: 0 1; margin-bottom: 1;
    }
    TrainSetupScreen #choices {
        grid-size: 3; height: auto;
    }
    TrainSetupScreen #summary { color: $text-muted; height: 1; }
    TrainSetupScreen #error { color: $error; height: auto; }
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
            with Vertical(id="session", classes="section") as session:
                session.border_title = "Session"
                with Horizontal(classes="row"):
                    yield Label("Difficulty")
                    yield Select(
                        [(level.value, level) for level in Difficulty],
                        value=challenge.difficulty,
                        allow_blank=False,
                        compact=True,
                        id="difficulty",
                    )
                    yield Label("Minutes", classes="after")
                    yield Input(str(challenge.duration_minutes), compact=True, id="duration")
                    yield Label("Stages", classes="after")
                    yield Input(str(challenge.stages), compact=True, id="stages")
                with Horizontal(classes="row"):
                    yield Label("Seed")
                    yield Input(
                        "" if challenge.seed is None else str(challenge.seed),
                        placeholder="random",
                        compact=True,
                        id="seed",
                    )
                with Horizontal(classes="row"):
                    yield Tick(
                        "strict: an example ends at its time limit", compact=True, id="strict"
                    )
            with Vertical(id="practise", classes="section") as practise:
                practise.border_title = self.CHOICES_LABEL
                with Grid(id="choices"):
                    yield from self._choices(self._settings)
            yield Static("", id="error")
            yield Static(id="summary")
            yield Button("Start", variant="primary", id="start")
        yield Footer()

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_mount(self) -> None:
        self._update_summary()

    @on(Input.Changed)
    @on(Select.Changed)
    @on(Checkbox.Changed)
    def _form_changed(self, event: object) -> None:
        del event
        self._update_summary()

    def _update_summary(self) -> None:
        if not self.query("#summary"):
            return
        try:
            minutes = _whole(self.query_one("#duration", Input).value, "Minutes", 1)
            stages = _whole(self.query_one("#stages", Input).value, "Stages", 1)
        except ValueError:
            value = "Check minutes and stages"
        else:
            strict = self.query_one("#strict", Checkbox).value
            difficulty = self.query_one("#difficulty", Select).value
            value = f"{minutes} min, {stages} stages, {'strict' if strict else 'soft'} timing, {difficulty}"
        self.query_one("#summary", Static).update(value)

    @on(Button.Pressed, "#start")
    def start(self) -> None:
        try:
            options = self._options()
            assert self._settings is not None
            settings = self._settings
            clock = self._numbra().clock
            session = Challenge(settings, clock=clock).create_session(options)
        except (ConfigError, ValueError) as exc:  # GenerationError is a ValueError
            self.query_one("#error", Static).update(Text(str(exc), style="bold red"))
            return
        warnings = (*settings.warnings, *session.warnings)

        def restart() -> TrainingSession:
            return Challenge(settings, clock=clock).create_session(options)

        self.app.switch_screen(TrainingScreen(session, warnings, restart=restart))

    def action_start(self) -> None:
        self.start()

    def _choices(self, settings: Settings) -> ComposeResult:
        """Operation and topic checkboxes; the funbox setup yields its own."""
        for token in _TOKENS:
            label = (
                f"{OPERATION_SYMBOLS[token]} {area_name(token)}"
                if token in OPERATION_SYMBOLS
                else f"{token} {area_name(token)}"
                if token in {"sqrt", "trig", "log"}
                else token
            )
            box = Tick(label, value=_enabled_by_default(token, settings), compact=True)
            self._boxes[token] = box
            yield box

    def _chosen(self) -> dict[str, Any]:
        """ChallengeOptions fields set by the checkboxes; raises ValueError for an empty choice."""
        tokens = [
            token for token, box in self._boxes.items() if token != "identities" and box.value
        ]
        return {
            "operations": parse_operation_selection(tokens),
            "identities": self._boxes["identities"].value,
        }

    def _options(self) -> ChallengeOptions:
        if self._settings is None:
            raise ConfigError("settings are not loaded")
        seed_text = self.query_one("#seed", Input).value.strip()
        return ChallengeOptions(
            duration_minutes=_whole(self.query_one("#duration", Input).value, "Duration", 1),
            stages=_whole(self.query_one("#stages", Input).value, "Stages", 1),
            difficulty=cast(Difficulty, self.query_one("#difficulty", Select).value),
            seed=_whole(seed_text, "Seed") if seed_text else None,
            strict=self.query_one("#strict", Checkbox).value,
            **self._chosen(),
        )

    def _numbra(self) -> NumbraApp:
        return cast("NumbraApp", self.app)


class TrainingScreen(Screen[None]):
    """One timed run: examples in order, cooldown between them, saved only on completion."""

    BINDINGS = [Binding("escape", "cancel", "Cancel (press twice)")]
    SUB_TITLE = "Training"
    DEFAULT_CSS = """
    TrainingScreen #training { align: center top; }
    TrainingScreen #status { height: 1; margin: 1 2 0 2; }
    TrainingScreen #status #stage { width: 1fr; text-align: left; }
    TrainingScreen #status #example { width: 1fr; text-align: center; }
    TrainingScreen #status #counts { width: 1fr; text-align: right; }
    TrainingScreen #overall { margin: 0 2; width: 1fr; }
    TrainingScreen #overall, TrainingScreen #overall Bar { width: 1fr; }
    TrainingScreen #card-row, TrainingScreen #answer-row { width: 1fr; height: auto; }
    TrainingScreen .spacer { width: 1fr; height: 1; }
    TrainingScreen #card {
        width: 64; max-width: 64; height: auto; border: round $accent;
        padding: 1 2; margin-top: 1;
    }
    TrainingScreen #expression {
        width: 1fr; height: 3; content-align: center middle; text-style: bold;
    }
    TrainingScreen #timer-row { height: 1; margin-top: 1; }
    TrainingScreen #timer { width: 1fr; }
    TrainingScreen #timer, TrainingScreen #timer Bar { width: 1fr; }
    TrainingScreen #clock { width: 12; text-align: right; }
    TrainingScreen #card.-low #timer Bar > .bar--bar { color: $warning; }
    TrainingScreen #card.-low #clock { color: $warning; }
    TrainingScreen #answer { width: 24; content-align: center middle; }
    TrainingScreen #answer-row { margin-top: 1; }
    TrainingScreen #feedback, TrainingScreen #next {
        width: 1fr; text-align: center; height: 1;
    }
    TrainingScreen #next { color: $text-muted; }
    """

    def __init__(
        self,
        session: TrainingSession,
        warnings: Sequence[str] = (),
        *,
        restart: Callable[[], TrainingSession] | None = None,
    ) -> None:
        super().__init__()
        self.session = session
        self._restart = restart
        if session.mode == "funbox":
            self.title = FUNBOX_TITLE
        self._warnings = tuple(warnings)
        self._positions = tuple(
            (stage, problem)
            for stage, plan in enumerate(session.stages)
            for problem in range(len(plan.problems))
        )
        self._index = 0
        self._phase = "answer"  # answer -> cooldown -> answer ... -> done
        self._armed = False
        self._correct = 0
        self._wrong = 0
        self._example_started = 0.0
        self._session_started = 0.0
        self._timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="training"):
            with Horizontal(id="status"):
                yield Static(id="stage")
                yield Static(id="example")
                yield Static(self._counts(), id="counts")
            yield ProgressBar(
                total=len(self._positions), show_eta=False, show_percentage=False, id="overall"
            )
            with Horizontal(id="card-row"):
                yield Static(classes="spacer")
                with Vertical(id="card"):
                    yield Static(id="expression")
                    with Horizontal(id="timer-row"):
                        yield ProgressBar(
                            total=1, show_eta=False, show_percentage=False, id="timer"
                        )
                        yield Static(id="clock")
                yield Static(classes="spacer")
            with Horizontal(id="answer-row"):
                yield Static(classes="spacer")
                yield Input(placeholder="Answer, then Enter", id="answer")
                yield Static(classes="spacer")
            yield Static(id="feedback")
            yield Static(id="next")
        yield Footer()

    def on_mount(self) -> None:
        for item in self._warnings:
            self.notify(item, severity="warning", timeout=8)
        self._session_started = self._numbra().clock()
        self._timer = self.set_interval(0.1, self._tick)
        self._show_example()

    def on_unmount(self) -> None:
        self._stop_timer()

    def _show_example(self) -> None:
        stage_number, problem_number = self._positions[self._index]
        plan = self.session.stages[stage_number]
        card = self.query_one("#card", Vertical)
        card.border_title = f"{self._index + 1}/{len(self._positions)}"
        card.border_subtitle = plan.kind.value
        self.query_one("#stage", Static).update(
            f"Stage {plan.number}/{len(self.session.stages)} {plan.kind.value}"
        )
        self.query_one("#example", Static).update(
            f"Example {self._index + 1}/{len(self._positions)}"
        )
        problem = plan.problems[problem_number]
        self.query_one("#expression", Static).update(display_expression(problem.expression))
        self.query_one("#feedback", Static).update("")
        self.query_one("#next", Static).update("")
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
        self.query_one("#timer", ProgressBar).update(total=limit, progress=max(0.0, remaining))
        self.query_one("#clock", Static).update(
            f"{remaining:.1f} s" if remaining >= 0 else f"+{-remaining:.1f} s over"
        )
        self.query_one("#card", Vertical).set_class(remaining < 0.3 * limit, "-low")

    @on(Input.Submitted, "#answer")
    def _answered(self, event: Input.Submitted) -> None:
        if self._phase != "answer":
            return
        elapsed = self._numbra().clock() - self._example_started
        self._record(event.value, elapsed, timed_out=False)

    def _record(self, answer: str | None, elapsed: float, timed_out: bool) -> None:
        stage_number, problem_number = self._positions[self._index]
        attempt = self.session.submit(stage_number, problem_number, answer, elapsed, timed_out)
        expected = format_answer(self.session.stages[stage_number].problems[problem_number].answer)
        if attempt.timed_out:
            message = Text.assemble(("Time's up", "bold yellow"), f"  answer {expected}")
        elif attempt.is_correct:
            message = Text.assemble(("✓ Correct", "bold green"), f"  +{attempt.score:.2f}")
        else:
            message = Text.assemble(("✗ Incorrect", "bold red"), f"  answer {expected}")
        if attempt.is_correct:
            self._correct += 1
        else:
            self._wrong += 1
        self.query_one("#counts", Static).update(self._counts())
        self.query_one("#overall", ProgressBar).update(progress=self._index + 1)
        self._armed = False
        self.query_one("#answer", Input).disabled = True
        if self._index + 1 == len(self._positions):
            self._finish()
            return
        self._phase = "cooldown"
        cooldown = self.session.cooldown_seconds
        self.query_one("#feedback", Static).update(message)
        self.query_one("#next", Static).update(Text(f"Next in {cooldown:g} s", style="dim"))
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
            self.query_one("#feedback", Static).update("Press Esc again to stop. Nothing is saved.")
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
        # Funbox has no comparable history or progress group, as in `numbra challenge`.
        funbox = completed.mode == "funbox"
        previous = [] if funbox else stats.comparable_history(completed, limit=1)
        progress = [] if funbox else stats.progress_history(completed)
        stats.save(completed)
        record = (stats.funbox_history(1) if funbox else stats.history(1))[0]
        streak = stats.streak(self._numbra().today())
        report = build_report(completed, previous[0] if previous else None, progress, streak)
        self.app.switch_screen(SummaryScreen(completed, report, record, self._restart))

    def _counts(self) -> Text:
        return Text.assemble(
            ("✓ ", "green"), str(self._correct), "  ", ("✗ ", "red"), str(self._wrong)
        )

    def _stop_timer(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _numbra(self) -> NumbraApp:
        return cast("NumbraApp", self.app)


class SummaryScreen(Screen[None]):
    """Result of a completed training; Enter or Esc returns to the menu."""

    BINDINGS = [
        Binding("enter", "done", "Menu"),
        Binding("escape", "done", show=False),
        Binding("d", "review", "Review answers"),
        Binding("t", "again", "Train again"),
    ]
    SUB_TITLE = "Summary"
    DEFAULT_CSS = """
    SummaryScreen VerticalScroll { padding: 0 2; }
    """

    def __init__(
        self,
        completed: CompletedTraining,
        report: TrainingReport,
        record: TrainingRecord,
        restart: Callable[[], TrainingSession] | None = None,
    ) -> None:
        super().__init__()
        self._completed = completed
        self._report = report
        self._record = record
        self._restart = restart
        if completed.mode == "funbox":
            self.title = FUNBOX_TITLE

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Static(summary_card(self._completed, self._report), id="summary")
        yield Footer()

    def action_done(self) -> None:
        self.app.pop_screen()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "again" and self._restart is None:
            return False
        return super().check_action(action, parameters)

    def action_review(self) -> None:
        from .results import SessionScreen

        self.app.push_screen(SessionScreen(self._record))

    def action_again(self) -> None:
        if self._restart is None:
            return
        self.app.switch_screen(TrainingScreen(self._restart(), restart=self._restart))
