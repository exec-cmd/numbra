"""Results screen: overview, saved sessions and group statistics. Numbers come from ``core``."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime
from typing import TYPE_CHECKING, cast

from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import DataTable, Footer, Header, Sparkline, Static, TabbedContent, TabPane

from ..core.report import METRIC_HELP, area_name, setup_label
from ..core.stats import AttemptRecord, GroupStats, Stats, TrainingRecord
from .style import days, display_expression, grade_text, percent, seconds

if TYPE_CHECKING:
    from .app import NumbraApp

HISTORY_LIMIT = 1000
_SESSION_HEADINGS = ("When", "Setup", "Correct", "Score", "Grade", "Time")
_GROUP_HEADINGS = ("Area", "Accuracy", "Attempts", "Time")
_BAR_WIDTH = 10


def _when(record: TrainingRecord, today: date) -> str:
    moment = datetime.fromtimestamp(record.started_at).astimezone()
    days_ago = (today - moment.date()).days
    if days_ago == 0:
        return f"Today {moment:%H:%M}"
    if days_ago == 1:
        return f"Yesterday {moment:%H:%M}"
    if moment.year == today.year:
        return f"{moment:%b} {moment.day} {moment:%H:%M}"
    return f"{moment:%Y-%m-%d %H:%M}"


def _setup(record: TrainingRecord, *, funbox: bool = False) -> str:
    if funbox:
        return f"funbox: {', '.join(record.operations or record.topics)}"
    return setup_label(record.difficulty, record.strict, record.operations, record.topics)


def _right(value: object) -> Text:
    return Text(str(value), justify="right")


def _bar(accuracy: float) -> Text:
    filled = round(accuracy * _BAR_WIDTH)
    return Text.assemble(
        ("█" * filled, "green" if accuracy >= 0.8 else "yellow" if accuracy >= 0.6 else "red"),
        ("░" * (_BAR_WIDTH - filled), "dim"),
        f" {percent(accuracy)}",
    )


def _group_row(item: GroupStats) -> tuple[Text, ...]:
    accuracy = item.correct / item.attempts if item.attempts else 0.0
    return (
        Text(f"  {area_name(item.name)}"),
        _bar(accuracy),
        _right(item.attempts),
        _right(seconds(item.average_correct_seconds)),
    )


def _section(title: str, items: Sequence[GroupStats]) -> list[tuple[Text, ...]]:
    if not items:
        return []
    return [
        (Text(title, style="bold"), Text(""), Text(""), Text("")),
        *(_group_row(item) for item in items),
    ]


class ResultsScreen(Screen[None]):
    SUB_TITLE = "Results"
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("r", "reload", "Reload"),
        Binding("question_mark", "legend", "Legend", key_display="?"),
    ]
    DEFAULT_CSS = """
    ResultsScreen #empty { padding: 1 2; }
    ResultsScreen #tabs { height: 1fr; }
    ResultsScreen #overview { padding: 1 2; }
    ResultsScreen #tiles { height: 3; margin-bottom: 1; }
    ResultsScreen .tile { width: 1fr; height: 3; }
    ResultsScreen #trend-title { margin-top: 1; }
    ResultsScreen #trend { height: 3; margin-bottom: 1; }
    ResultsScreen #details { height: auto; }
    ResultsScreen #last, ResultsScreen #practice { width: 1fr; height: auto; }
    ResultsScreen .note { color: $text-muted; }
    ResultsScreen #bests-title { margin-top: 1; text-style: bold; }
    ResultsScreen #skills-note { margin: 1 2; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._history: list[TrainingRecord] = []
        self._sessions: list[TrainingRecord] = []
        self._funbox_ids: set[int] = set()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "No finished trainings yet. Choose Train in the menu, finish a run, and your results appear here.",
            id="empty",
        )
        with TabbedContent(id="tabs"):
            with TabPane("Overview", id="overview-tab"):
                with VerticalScroll(id="overview"):
                    with Horizontal(id="tiles"):
                        for name in ("sessions", "accuracy", "time", "streak"):
                            yield Static(id=f"tile-{name}", classes="tile")
                    yield Static(id="trend-title")
                    yield Sparkline(id="trend")
                    yield Static(
                        "Complete two sessions to see the trend.", id="trend-hint", classes="note"
                    )
                    with Horizontal(id="details"):
                        yield Static(id="last")
                        yield Static(id="practice")
                    yield Static("Personal bests", id="bests-title")
                    yield DataTable(id="bests", cursor_type="none", show_cursor=False)
            with TabPane("Sessions", id="sessions-tab"):
                yield DataTable(id="sessions", cursor_type="row", zebra_stripes=True)
            with TabPane("Skills", id="skills-tab"):
                yield DataTable(id="skills", cursor_type="none")
                yield Static(
                    "Accuracy bar: green 80%+, yellow 60%+, red below. Time is per correct answer.",
                    id="skills-note",
                    classes="note",
                )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#sessions", DataTable).add_columns(*_SESSION_HEADINGS)
        self.query_one("#bests", DataTable).add_columns(
            "Setup", "Sessions", "Best score", "Best time"
        )
        self.query_one("#skills", DataTable).add_columns(*_GROUP_HEADINGS)
        self.action_reload()

    def action_reload(self) -> None:
        stats = Stats(self._numbra().database_path)
        self._history = stats.history(HISTORY_LIMIT)
        funbox_history = stats.funbox_history(HISTORY_LIMIT)
        self._funbox_ids = {record.identifier for record in funbox_history}
        self._sessions = sorted(
            [*self._history, *funbox_history], key=lambda record: record.started_at, reverse=True
        )
        empty = not self._sessions
        self.query_one("#empty").display = empty
        self.query_one("#tabs").display = not empty
        self._fill("#sessions", self._session_rows(self._sessions, self._funbox_ids))
        self._fill_overview(stats)
        breakdown = stats.breakdown()
        tricks = [
            GroupStats(
                "trick", item.strategy, item.attempts, item.correct, item.average_correct_seconds
            )
            for item in stats.trick_stats()
        ]
        skills = [
            *_section("Operations", breakdown.operations),
            *_section("Topics", breakdown.topics),
            *_section("Tricks", tricks),
            *_section("Difficulty", breakdown.difficulties),
            *_section("Funbox (experimental)", stats.funbox_stats()),
        ]
        self._fill("#skills", skills)
        records = sorted(stats.records(), key=lambda item: item.best_score_percent, reverse=True)[
            :5
        ]
        bests = self.query_one("#bests", DataTable)
        bests.display = bool(records)
        self.query_one("#bests-title").display = bool(records)
        self._fill(
            "#bests",
            [
                (
                    setup_label(record.difficulty, record.strict, record.operations, record.topics),
                    _right(record.sessions),
                    _right(percent(record.best_score_percent)),
                    _right(seconds(record.best_average_correct_seconds)),
                )
                for record in records
            ],
        )

    def _session_rows(
        self, records: Sequence[TrainingRecord], funbox_ids: set[int]
    ) -> list[tuple[str | Text, ...]]:
        today = self._numbra().today()
        return [
            (
                _when(record, today),
                _setup(record, funbox=record.identifier in funbox_ids),
                _right(f"{record.correct_answers}/{record.total_examples}"),
                _right(percent(record.score_percent)),
                grade_text(record.score_percent),
                _right(seconds(record.average_correct_seconds)),
            )
            for record in records
        ]

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_legend(self) -> None:
        self.app.push_screen(LegendScreen())

    @on(TabbedContent.TabActivated)
    def _focus_table(self, event: TabbedContent.TabActivated) -> None:
        tables = event.pane.query(DataTable)
        if tables:
            tables.first().focus()

    @on(DataTable.RowSelected, "#sessions")
    def _open_session(self, event: DataTable.RowSelected) -> None:
        record = self._sessions[event.cursor_row]
        self.app.push_screen(SessionScreen(record, funbox=record.identifier in self._funbox_ids))

    def _fill_overview(self, stats: Stats) -> None:
        aggregate = stats.aggregate()
        current, longest = stats.streak(self._numbra().today())
        tiles = {
            "sessions": (str(aggregate.completed_trainings), "sessions", "completed"),
            "accuracy": (percent(aggregate.accuracy), "accuracy", "share correct"),
            "time": (seconds(aggregate.average_correct_seconds), "time", "per correct answer"),
            "streak": (days(current), f"streak, best {longest}", "days in a row"),
        }
        for name, (value, label, hint) in tiles.items():
            self.query_one(f"#tile-{name}", Static).update(
                Text.assemble((value, "bold"), "\n", label, "\n", (hint, "dim"))
            )

        scores = [record.score_percent for record in self._history]
        trend = len(scores) >= 2
        title = (
            Text.assemble(
                (f"Score, last {len(scores)} sessions (oldest left)", "bold"),
                f"   best {percent(max(scores))}, average {percent(sum(scores) / len(scores))}",
            )
            if trend
            else Text(f"Score, last {len(scores)} sessions (oldest left)", style="bold")
        )
        self.query_one("#trend-title", Static).update(title)
        sparkline = self.query_one("#trend", Sparkline)
        sparkline.display = trend
        sparkline.data = list(reversed(scores)) if trend else None
        self.query_one("#trend-hint").display = not trend

        last_widget = self.query_one("#last", Static)
        if self._history:
            last = self._history[0]
            last_widget.display = True
            last_widget.update(
                Text.assemble(
                    ("Last session\n", "bold"),
                    grade_text(last.score_percent),
                    f" {percent(last.score_percent)}, {_when(last, self._numbra().today())}\n",
                    f"{last.correct_answers} of {last.total_examples} correct, {_setup(last)}\n",
                    f"{seconds(last.average_correct_seconds)} per correct answer",
                )
            )
        else:
            last_widget.display = False
        weak = stats.weak_spots()
        practice = Text.assemble(("Practise next\n", "bold"))
        if weak:
            width = max(len(area_name(item.name)) for item in weak)
            for item in weak:
                practice.append(f"{area_name(item.name):<{width}}  ")
                practice.append_text(_bar(item.accuracy))
                practice.append("\n")
        else:
            practice.append(
                "Nothing stands out yet. Areas with at least 5 attempts and a miss show up here.",
                style="dim",
            )
        self.query_one("#practice", Static).update(practice)

    def _fill(self, selector: str, rows: Iterable[Sequence[str | Text]]) -> None:
        table = self.query_one(selector, DataTable)
        table.clear()
        table.add_rows(rows)

    def _numbra(self) -> NumbraApp:
        return cast("NumbraApp", self.app)


class LegendScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "close", show=False),
        Binding("question_mark", "close", show=False),
        Binding("enter", "close", show=False),
    ]
    DEFAULT_CSS = """
    LegendScreen { align: center middle; }
    LegendScreen #legend { width: 72; max-width: 100%; max-height: 100%; overflow-y: auto; border: round $accent; padding: 1 2; background: $surface; }
    """

    def compose(self) -> ComposeResult:
        table = Table.grid(padding=(0, 2))
        for name, meaning in METRIC_HELP.items():
            table.add_row(Text(name, style="bold"), meaning)
        box = Static(table, id="legend")
        box.border_title = "Metrics"
        box.border_subtitle = "Esc closes"
        yield box

    def action_close(self) -> None:
        self.dismiss()


_RESULT_TEXT = {
    "timeout": ("time", "yellow"),
    "correct": ("✓", "green"),
    "wrong": ("✗", "red"),
}


class SessionScreen(Screen[None]):
    """Every example of one saved session; Esc returns to Results."""

    SUB_TITLE = "Session"
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("m", "toggle_mistakes", "Mistakes only"),
    ]
    DEFAULT_CSS = """
    SessionScreen #session-summary { padding: 1 2; height: auto; }
    SessionScreen #session-note { padding: 0 2 1 2; height: auto; color: $text-muted; }
    SessionScreen DataTable { height: 1fr; }
    """

    def __init__(self, record: TrainingRecord, *, funbox: bool = False) -> None:
        super().__init__()
        self._record = record
        self._funbox = funbox
        self._attempts: list[AttemptRecord] = []
        self._mistakes_only = False

    def compose(self) -> ComposeResult:
        record = self._record
        today = cast("NumbraApp", self.app).today()
        yield Header()
        yield Static(
            Text.assemble(
                grade_text(record.score_percent),
                (f" {percent(record.score_percent)}", "bold"),
                f"   {record.correct_answers} of {record.total_examples} correct   "
                f"{_setup(record, funbox=self._funbox)}   {_when(record, today)}",
            ),
            id="session-summary",
        )
        yield Static("", id="session-note", classes="note")
        yield DataTable(id="attempts", cursor_type="none", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#attempts", DataTable)
        table.add_columns(
            "#", "Stage", "Expression", "Your answer", "Answer", "Result", "Time", "Score"
        )
        self._attempts = Stats(cast("NumbraApp", self.app).database_path).attempts(
            self._record.identifier
        )
        self._refresh_attempts()

    def action_toggle_mistakes(self) -> None:
        if not any(not item.is_correct for item in self._attempts):
            return
        self._mistakes_only = not self._mistakes_only
        self._refresh_attempts()

    def _refresh_attempts(self) -> None:
        table = self.query_one("#attempts", DataTable)
        table.clear()
        note = self.query_one("#session-note", Static)
        mistakes = [item for item in self._attempts if not item.is_correct]
        n = len(mistakes)
        if not mistakes:
            note.update("No mistakes")
        elif self._mistakes_only:
            note.update("Showing mistakes only (m: show all)")
        else:
            note.update(f"✗ {n} mistake{'s' if n != 1 else ''}   (m: show mistakes only)")
        visible = [
            (number, item)
            for number, item in enumerate(self._attempts, 1)
            if not self._mistakes_only or not item.is_correct
        ]
        for number, item in visible:
            result, style = _RESULT_TEXT[
                "timeout" if item.timed_out else "correct" if item.is_correct else "wrong"
            ]
            values = (
                _right(number),
                Text(f"{item.stage_number} {item.kind}", style=style if style != "green" else ""),
                Text(display_expression(item.expression), style=style if style != "green" else ""),
                _right(item.user_answer or "—"),
                _right(item.correct_answer),
                Text(result, style=style),
                _right(seconds(item.elapsed_seconds)),
                _right(f"{item.score:.2f}"),
            )
            row_style = style if style != "green" else ""
            for cell in values:
                cell.stylize(row_style)
            table.add_row(*values)

    def action_back(self) -> None:
        self.app.pop_screen()
