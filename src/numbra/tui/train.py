"""Training screens: setup form, timed run and summary. Rules live in ``core``."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, cast

from rich.segment import Segment
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.screen import Screen
from textual.strip import Strip
from textual.timer import Timer
from textual.widgets import (
    Button,
    Checkbox,
    ContentSwitcher,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    ProgressBar,
    SelectionList,
    Static,
)
from textual.widgets.option_list import Option, OptionDoesNotExist

from ..cli.summary import summary_card
from ..config import ConfigError, DifficultyConfig, Settings
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
from ..i18n import t, tn
from .style import display_expression, setup_text, translate_bindings

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


class ChoiceList(SelectionList[str]):
    """Selection list drawn with [x] and [ ], so its state does not depend on colour."""

    BINDINGS = [Binding("enter", "screen.next_step", "Next", show=False)]

    def render_line(self, y: int) -> Strip:
        # shortcut: replaces the 3-cell ▐X▌ button SelectionList draws in Textual 8.2.8;
        # ANSI themes cannot hide the X by colour. Re-check on a Textual upgrade.
        strip = super().render_line(y)
        segments = list(strip)
        try:
            selection = self.get_option_at_index(self.scroll_offset.y + y)
        except OptionDoesNotExist:
            return strip
        if len(segments) < 4:
            return strip
        mark = "[x]" if selection.value in self.selected else "[ ]"
        return Strip([Segment(mark, segments[1].style), *segments[3:]])


def _whole(text: str, label: str, minimum: int | None = None) -> int:
    try:
        value = int(text)
    except ValueError:
        raise ValueError(f"{label} must be a whole number") from None
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    return value


class TrainSetupScreen(Screen[None]):
    """Preset and step wizard for one training."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("ctrl+s", "start", "Start"),
        Binding("1", "edit_step(1)", "Edit level", show=False),
        Binding("2", "edit_step(2)", "Edit topics", show=False),
        Binding("3", "edit_step(3)", "Edit time", show=False),
        Binding("4", "edit_step(4)", "Edit preset", show=False),
    ]
    SUB_TITLE = "New training"
    # CSS, not DEFAULT_CSS: the app-wide OptionList highlight would win over DEFAULT_CSS,
    # and in ANSI themes it is bold only, which the bold level names already are; the step bar uses cyan too.
    CSS = """
    TrainSetupScreen #presets > .option-list--option-highlighted { color: ansi_cyan; text-style: bold; }
    TrainSetupScreen #difficulty > .option-list--option-highlighted { color: ansi_cyan; text-style: bold; }
    """
    HAS_START_STEP = True
    CHOICE_STEP_LABEL = "Topics"
    STEP_IDS = ("step-start", "step-level", "step-practise", "step-time", "step-review")
    STEP_LABELS = ("Preset", "Level", "Topics", "Time", "Review")
    DEFAULT_CSS = """
    TrainSetupScreen #wizard { align: center top; height: 1fr; margin-top: 1; }
    TrainSetupScreen #steps { width: 100%; max-width: 72; height: auto; }
    TrainSetupScreen .step { width: 100%; height: auto; }
    TrainSetupScreen #stepbar { width: 100%; max-width: 72; height: 1; margin: 0 0 1 0; text-align: center; }
    TrainSetupScreen .section { border: round $panel-lighten-2; height: auto; padding: 0 1; }
    TrainSetupScreen #presets { height: auto; max-height: 7; border: none; padding: 0; }
    TrainSetupScreen #presets .option-list--option { height: 1; }
    TrainSetupScreen #difficulty { height: auto; border: none; padding: 0; }
    TrainSetupScreen #difficulty .option-list--option { height: 2; }
    TrainSetupScreen #choices { height: auto; max-height: 10; }
    TrainSetupScreen .row { height: 1; }
    TrainSetupScreen .row Label { width: 11; height: 1; content-align: left middle; }
    TrainSetupScreen .row .after { width: auto; margin-left: 3; padding-right: 1; }
    TrainSetupScreen #duration, TrainSetupScreen #stages { width: 7; }
    TrainSetupScreen #seed { width: 16; }
    TrainSetupScreen Input { background: $foreground 8%; }
    TrainSetupScreen Input:focus { background: $foreground 16%; }
    TrainSetupScreen #strict { margin-left: 3; }
    TrainSetupScreen Checkbox, TrainSetupScreen Checkbox:focus { border: none; }
    TrainSetupScreen .hint { color: $text-muted; height: 1; margin-top: 1; text-align: center; }
    TrainSetupScreen #summary { height: auto; }
    TrainSetupScreen #error { color: $error; height: auto; }
    TrainSetupScreen .step-error { color: $error; height: 1; }
    TrainSetupScreen #start-row { height: auto; }
    TrainSetupScreen #start { margin-top: 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.sub_title = t(self.SUB_TITLE)
        if self.TITLE:
            self.title = t(self.TITLE)
        self._settings: Settings | None = None
        self._choices: ChoiceList | None = None
        self._presets: dict[str, dict[str, Any]] = {}
        self._path: list[str] = []
        self._step_ids = self.STEP_IDS if self.HAS_START_STEP else self.STEP_IDS[1:]
        self._step_labels = self.STEP_LABELS if self.HAS_START_STEP else self.STEP_LABELS[1:]
        translate_bindings(self)

    def compose(self) -> ComposeResult:
        yield Header()
        try:
            self._settings = self._numbra().load_settings()
        except ConfigError as exc:
            yield Static(
                Text(t("Configuration error: {error}").format(error=exc), style="bold red")
            )
            yield Footer()
            return
        challenge = self._settings.challenge
        with Center(id="wizard"):
            yield Static(id="stepbar")
            with ContentSwitcher(id="steps", initial=self._step_ids[0]):
                if self.HAS_START_STEP:
                    with Vertical(id="step-start", classes="step"):
                        with Vertical(classes="section") as presets_box:
                            presets_box.border_title = t("Preset", "step")
                            yield self._preset_list(self._settings)
                        yield Static(t("Enter picks, Esc returns to the menu"), classes="hint")
                with Vertical(id="step-level", classes="step"):
                    yield self._difficulty_list(challenge.difficulty, challenge.profiles)
                    yield Static(t("Enter — choose, Esc — back"), classes="hint")
                    yield Static("", classes="step-error", id="level-error")
                with Vertical(id="step-practise", classes="step"):
                    with Vertical(classes="section") as practise:
                        practise.border_title = t(self.CHOICE_STEP_LABEL)
                        self._choices = self._choice_list(self._settings)
                        yield self._choices
                    yield Static("", classes="step-error", id="practise-error")
                    yield Static(t("Space toggles, Enter goes on, Esc goes back"), classes="hint")
                with Vertical(id="step-time", classes="step"):
                    with Vertical(classes="section") as session:
                        session.border_title = t("Time")
                        with Horizontal(classes="row"):
                            yield Label(t("Minutes"))
                            yield Input(
                                str(challenge.duration_minutes), compact=True, id="duration"
                            )
                            yield Label(t("Stages"), classes="after")
                            yield Input(str(challenge.stages), compact=True, id="stages")
                        with Horizontal(classes="row"):
                            yield Label(t("Seed"))
                            yield Input(
                                "" if challenge.seed is None else str(challenge.seed),
                                placeholder=t("random"),
                                compact=True,
                                id="seed",
                            )
                        yield Tick(
                            t("strict: an example ends at its time limit"),
                            compact=True,
                            id="strict",
                        )
                    yield Static("", classes="step-error", id="time-error")
                    yield Static(
                        t("Tab moves between fields, Enter goes on, Esc goes back"), classes="hint"
                    )
                with Vertical(id="step-review", classes="step"):
                    with Vertical(classes="section") as review:
                        review.border_title = t("Review")
                        yield Static(id="summary")
                    yield Static("", id="error")
                    with Center(id="start-row"):
                        yield Button(t("Start"), variant="primary", id="start")
                    yield Static(t("Enter starts, 1–4 edit a step, Esc goes back"), classes="hint")
        yield Footer()

    def on_mount(self) -> None:
        if not self.query("#steps"):
            return
        self._path = [self._step_ids[0]]
        self._update_stepbar()
        self._update_summary()
        self._focus_step(self._step_ids[0])

    def action_back(self) -> None:
        if len(self._path) > 1:
            self._path.pop()
            self._show_step(self._path[-1], push=False)
        else:
            self.app.pop_screen()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action.startswith("edit_step"):
            return (
                bool(self.query("#steps"))
                and self.query_one("#steps", ContentSwitcher).current == "step-review"
            )
        return True

    def action_edit_step(self, number: int) -> None:
        target = {1: "step-level", 2: "step-practise", 3: "step-time", 4: "step-start"}
        step = target.get(number, "step-level")
        if step in self._step_ids:
            self._show_step(step)

    def action_next_step(self) -> None:
        current = self.query_one("#steps", ContentSwitcher).current
        if current in self._step_ids:
            index = self._step_ids.index(current)
            if index < len(self._step_ids) - 1:
                self._show_step(self._step_ids[index + 1])

    def _show_step(self, step: str, *, push: bool = True) -> None:
        switcher = self.query_one("#steps", ContentSwitcher)
        if push and (not self._path or self._path[-1] != step):
            self._path.append(step)
        switcher.current = step
        self._update_stepbar()
        self._focus_step(step)

    def _focus_step(self, step: str) -> None:
        target = {
            "step-start": "#presets",
            "step-level": "#difficulty",
            "step-practise": "#choices",
            "step-time": "#duration",
            "step-review": "#start",
        }[step]
        self.query_one(target).focus()

    def _update_stepbar(self) -> None:
        switcher = self.query_one("#steps", ContentSwitcher)
        current = switcher.current or self._step_ids[0]
        current_index = self._step_ids.index(current)
        value = Text()
        for index, label in enumerate(self._step_labels):
            if index:
                value.append(" › ", style="dim")
            value.append(
                t(label, "step"),
                style="bold cyan"
                if index == current_index
                else "dim"
                if index > current_index
                else "",
            )
        self.query_one("#stepbar", Static).update(value)

    @on(Input.Changed)
    @on(Checkbox.Changed)
    @on(ChoiceList.SelectedChanged)
    def _form_changed(self, event: object) -> None:
        del event
        self._update_summary()

    @on(Input.Submitted)
    def _input_submitted(self, event: Input.Submitted) -> None:
        del event
        self.action_next_step()

    @on(OptionList.OptionSelected)
    def _option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "presets":
            self._apply_preset(event.option.id or "")
        elif event.option_list.id == "difficulty":
            self._show_step("step-practise")

    def _update_summary(self) -> None:
        if not self.query("#summary"):
            return
        try:
            minutes = _whole(self.query_one("#duration", Input).value, "Duration", 1)
            stages = _whole(self.query_one("#stages", Input).value, "Stages", 1)
            difficulty = self._difficulty()
            tokens = self._choices_tokens()
            detail = self._practice_summary(tokens, difficulty)
            table = Table.grid(padding=(0, 2))
            table.add_column(style="bold")
            table.add_column()
            table.add_row(t("Level", "step"), t(difficulty.value, "difficulty"))
            table.add_row(t(self.CHOICE_STEP_LABEL, "step"), detail)
            table.add_row(
                t("Time", "step"),
                f"{t('{minutes} min').format(minutes=minutes)}, {tn(stages, '{n} stage', '{n} stages').format(n=stages)}, {t('strict timing' if self.query_one('#strict', Checkbox).value else 'soft timing')}",
            )
            seed = self.query_one("#seed", Input).value.strip() or t("random")
            table.add_row(t("Seed"), seed)
        except ValueError:
            table = Table.grid()
            table.add_row(t("Check minutes and stages"))
        self.query_one("#summary", Static).update(table)

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
            target = (
                "step-practise"
                if "operation list" in str(exc) or "funbox mode" in str(exc)
                else "step-time"
            )
            field = "practise-error" if target == "step-practise" else "time-error"
            self.query_one(f"#{field}", Static).update(str(exc))
            self._show_step(target)
            return
        warnings = (*settings.warnings, *session.warnings)

        def restart() -> TrainingSession:
            return Challenge(settings, clock=clock).create_session(options)

        self.app.switch_screen(TrainingScreen(session, warnings, restart=restart))

    def action_start(self) -> None:
        self.start()

    def _choice_list(self, settings: Settings) -> ChoiceList:
        selections = []
        for token in _TOKENS:
            label = (
                f"{OPERATION_SYMBOLS[token]} {t(area_name(token))}"
                if token in OPERATION_SYMBOLS
                else f"{token} {t(area_name(token))}"
                if token in {"sqrt", "trig", "log"}
                else t(token)
            )
            selections.append((label, token, _enabled_by_default(token, settings)))
        return ChoiceList(*selections, compact=True, id="choices")

    def _difficulty_list(
        self, difficulty: Difficulty, profiles: Mapping[Difficulty, DifficultyConfig]
    ) -> OptionList:
        options = []
        for level in Difficulty:
            prompt = Text(t(level.value, "difficulty"), style="bold")
            profile = profiles[level]
            terms = (
                str(profile.min_terms)
                if profile.min_terms == profile.max_terms
                else f"{profile.min_terms}–{profile.max_terms}"
            )
            description = t("{terms} numbers, values up to {limit}").format(
                terms=terms, limit=profile.max_value
            )
            prompt.append("\n" + description, style="dim")
            options.append(Option(prompt, id=level.value))
        result = OptionList(*options, id="difficulty")
        result.highlighted = list(Difficulty).index(difficulty)
        return result

    def _difficulty(self) -> Difficulty:
        option = self.query_one("#difficulty", OptionList).get_option_at_index(
            self.query_one("#difficulty", OptionList).highlighted or 0
        )
        return Difficulty(option.id or Difficulty.NORMAL)

    def _choices_tokens(self) -> list[str]:
        return list(self.query_one("#choices", ChoiceList).selected)

    @staticmethod
    def _split_tokens(tokens: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return (
            tuple(token for token in tokens if token in {"+", "-", "*", "/", "^"}),
            tuple(token for token in tokens if token not in {"+", "-", "*", "/", "^"}),
        )

    def _practice_summary(self, tokens: Sequence[str], difficulty: Difficulty) -> str:
        operations, topics = self._split_tokens(tokens)
        detail = setup_text(
            difficulty.value, self.query_one("#strict", Checkbox).value, operations, topics
        )
        return detail.split(": ", 1)[-1] if ": " in detail else t("Choose at least one")

    def _chosen(self) -> dict[str, Any]:
        """ChallengeOptions fields set by the checkboxes; raises ValueError for an empty choice."""
        tokens = [token for token in self._choices_tokens() if token != "identities"]
        return {
            "operations": parse_operation_selection(tokens),
            "identities": "identities" in self._choices_tokens(),
        }

    def _settings_tokens(self) -> list[str]:
        assert self._settings is not None
        return [token for token in _TOKENS if _enabled_by_default(token, self._settings)]

    def _preset_list(self, settings: Settings) -> OptionList:
        self._presets = {}
        rows: list[tuple[str, str, dict[str, Any]]] = []
        record = Stats(self._numbra().database_path).history(1)
        if record:
            try:
                difficulty = Difficulty(record[0].difficulty)
            except ValueError:
                pass
            else:
                saved = record[0]
                tokens = list(
                    dict.fromkeys(
                        [token for token in saved.operations if token in _TOKENS]
                        + [
                            "^" if token == "power" else token
                            for token in saved.topics
                            if token in _TOKENS or token == "power"
                        ]
                    )
                )
                rows.append(
                    (
                        "repeat",
                        "Repeat last",
                        {
                            "difficulty": difficulty,
                            "tokens": tokens,
                            "strict": saved.strict,
                            "minutes": max(1, round(saved.target_duration_seconds / 60)),
                            "stages": saved.stages,
                            "seed": "",
                        },
                    )
                )
        for spot in Stats(self._numbra().database_path).weak_spots(limit=5):
            token = "^" if spot.name == "power" else spot.name
            if spot.kind in {"operation", "topic"} and token in _TOKENS:
                name = OPERATION_SYMBOLS.get(token, t(area_name(spot.name)))
                rows.append(
                    (
                        "weak",
                        t("Weak spot: {name}").format(name=name),
                        {
                            "difficulty": settings.challenge.difficulty,
                            "tokens": [token],
                            "strict": False,
                            "minutes": settings.challenge.duration_minutes,
                            "stages": settings.challenge.stages,
                            "seed": "",
                        },
                    )
                )
                break
        if settings.challenge.duration_minutes != 2:
            rows.append(
                (
                    "quick",
                    "Quick",
                    {
                        "difficulty": settings.challenge.difficulty,
                        "tokens": self._settings_tokens(),
                        "strict": False,
                        "minutes": 2,
                        "stages": settings.challenge.stages,
                        "seed": "",
                    },
                )
            )
        rows.extend(
            (
                (
                    "settings",
                    "From settings",
                    {
                        "difficulty": settings.challenge.difficulty,
                        "tokens": self._settings_tokens(),
                        "strict": False,
                        "minutes": settings.challenge.duration_minutes,
                        "stages": settings.challenge.stages,
                        "seed": "",
                    },
                ),
                ("custom", "Custom…", {}),
            )
        )
        options = []
        names = [name if identifier == "weak" else t(name) for identifier, name, _ in rows]
        name_width = max(len(name) for name in names)
        for (identifier, _, values), shown in zip(rows, names, strict=True):
            self._presets[identifier] = values
            table = Table.grid(padding=(0, 2))
            table.add_column(width=name_width, no_wrap=True)
            table.add_column()
            if identifier == "custom":
                description = t("choose every option")
            else:
                ops, topics = self._split_tokens(values["tokens"])
                setup = setup_text(values["difficulty"].value, values["strict"], ops, topics)
                description = f"{setup}, {t('{minutes} min').format(minutes=values['minutes'])}, {tn(values['stages'], '{n} stage', '{n} stages').format(n=values['stages'])}"
            table.add_row(
                Text(shown, style="bold"),
                Text(description, style="dim"),
            )
            options.append(Option(table, id=identifier))
        return OptionList(*options, id="presets")

    def _apply_preset(self, identifier: str) -> None:
        if identifier == "custom":
            self._show_step("step-level")
            return
        values = self._presets[identifier]
        self.query_one("#duration", Input).value = str(values["minutes"])
        self.query_one("#stages", Input).value = str(values["stages"])
        self.query_one("#seed", Input).value = values["seed"]
        self.query_one("#strict", Checkbox).value = values["strict"]
        self.query_one("#choices", ChoiceList).deselect_all()
        for token in values["tokens"]:
            if token in _TOKENS:
                self.query_one("#choices", ChoiceList).select(token)
        levels = self.query_one("#difficulty", OptionList)
        levels.highlighted = list(Difficulty).index(values["difficulty"])
        self._update_summary()
        self._show_step("step-review")

    def _options(self) -> ChallengeOptions:
        if self._settings is None:
            raise ConfigError("settings are not loaded")
        seed_text = self.query_one("#seed", Input).value.strip()
        return ChallengeOptions(
            duration_minutes=_whole(self.query_one("#duration", Input).value, "Duration", 1),
            stages=_whole(self.query_one("#stages", Input).value, "Stages", 1),
            difficulty=self._difficulty(),
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
        self.sub_title = t(self.SUB_TITLE)
        self.session = session
        self._restart = restart
        if session.mode == "funbox":
            self.title = t(FUNBOX_TITLE)
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
        translate_bindings(self)

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
                yield Input(placeholder=t("Answer, then Enter"), id="answer")
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
        card.border_subtitle = t(plan.kind.value, "stage")
        self.query_one("#stage", Static).update(
            f"{t('Stage')} {plan.number}/{len(self.session.stages)} {t(plan.kind.value, 'stage')}"
        )
        self.query_one("#example", Static).update(
            f"{t('Example')} {self._index + 1}/{len(self._positions)}"
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
            t("{value} s").format(value=f"{remaining:.1f}")
            if remaining >= 0
            else t("+{seconds} s over").format(seconds=f"{-remaining:.1f}")
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
            message = Text.assemble(
                (t("Time's up"), "bold yellow"), "  " + t("answer {answer}").format(answer=expected)
            )
        elif attempt.is_correct:
            message = Text.assemble((f"✓ {t('Correct')}", "bold green"), f"  +{attempt.score:.2f}")
        else:
            message = Text.assemble(
                (f"✗ {t('Incorrect')}", "bold red"),
                "  " + t("answer {answer}").format(answer=expected),
            )
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
        self.query_one("#next", Static).update(
            Text(t("Next in {seconds} s").format(seconds=f"{cooldown:g}"), style="dim")
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
            self.query_one("#feedback", Static).update(
                t("Press Esc again to stop. Nothing is saved.")
            )
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
        self.sub_title = t(self.SUB_TITLE)
        self._completed = completed
        self._report = report
        self._record = record
        self._restart = restart
        if completed.mode == "funbox":
            self.title = t(FUNBOX_TITLE)
        translate_bindings(self)

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
