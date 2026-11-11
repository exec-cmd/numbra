"""Results screen: overview, saved sessions and group statistics. Numbers come from ``core``."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime
from typing import TYPE_CHECKING, cast

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Sparkline, Static, TabbedContent, TabPane

from ..core.report import area_name
from ..core.stats import GroupStats, Stats, TrainingRecord
from .style import days, grade_text, percent, seconds

if TYPE_CHECKING:
    from .app import NumbraApp

# Newest sessions shown in History and the score trend; the overview totals cover every session.
HISTORY_LIMIT = 1000
_HISTORY_HEADINGS = ("When", "Level", "Correct", "Score", "Grade", "Per answer", "Length")
_GROUP_HEADINGS = ("", "Accuracy", "Attempts", "Per correct answer")
_BAR_WIDTH = 10


def _when(record: TrainingRecord, today: date) -> str:
    moment = datetime.fromtimestamp(record.started_at).astimezone()
    days = (today - moment.date()).days
    if days == 0:
        return f"Today {moment:%H:%M}"
    if days == 1:
        return f"Yesterday {moment:%H:%M}"
    if moment.year == today.year:
        return f"{moment:%b} {moment.day} {moment:%H:%M}"
    return f"{moment:%Y-%m-%d %H:%M}"


def _level(difficulty: str, strict: bool) -> str:
    return f"{difficulty}, strict" if strict else difficulty


def _length(seconds: float) -> str:
    minutes, rest = divmod(round(seconds), 60)
    return f"{minutes}:{rest:02d}"


def _bar(accuracy: float) -> Text:
    filled = round(accuracy * _BAR_WIDTH)
    return Text.assemble(
        ("█" * filled, "green" if accuracy >= 0.8 else "yellow" if accuracy >= 0.6 else "red"),
        ("░" * (_BAR_WIDTH - filled), "dim"),
        f" {percent(accuracy)}",
    )


def _history_rows(records: Sequence[TrainingRecord], today: date) -> list[tuple[str | Text, ...]]:
    return [
        (
            _when(record, today),
            _level(record.difficulty, record.strict),
            f"{record.correct_answers}/{record.total_examples}",
            percent(record.score_percent),
            grade_text(record.score_percent),
            seconds(record.average_response_seconds),
            _length(record.actual_duration_seconds),
        )
        for record in records
    ]


def _group_row(
    name: str, attempts: int, correct: int, average_seconds: float | None
) -> tuple[Text, ...]:
    accuracy = correct / attempts if attempts else 0.0
    return (Text(f"  {name}"), _bar(accuracy), Text(str(attempts)), Text(seconds(average_seconds)))


def _section(title: str, items: Sequence[GroupStats]) -> list[tuple[Text, ...]]:
    if not items:
        return []
    heading = (Text(title, style="bold"), Text(""), Text(""), Text(""))
    return [
        heading,
        *(
            _group_row(
                area_name(item.name), item.attempts, item.correct, item.average_correct_seconds
            )
            for item in items
        ),
    ]


class ResultsScreen(Screen[None]):
    BINDINGS = [Binding("escape", "back", "Back"), Binding("r", "reload", "Reload")]
    DEFAULT_CSS = """
    ResultsScreen #empty { padding: 1 2; }
    ResultsScreen #tabs { height: 1fr; }
    ResultsScreen #overview { padding: 1 2; }
    ResultsScreen #tiles { height: 2; margin-bottom: 1; }
    ResultsScreen .tile { width: 1fr; }
    ResultsScreen #trend-title { margin-top: 1; }
    ResultsScreen #trend { height: 3; margin-bottom: 1; }
    ResultsScreen #details { height: auto; }
    ResultsScreen #last, ResultsScreen #practice { width: 1fr; height: auto; }
    ResultsScreen .note { color: $text-muted; }
    ResultsScreen #funbox-history { margin-top: 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._history: list[TrainingRecord] = []
        self._funbox_history: list[TrainingRecord] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "No completed challenges yet. Choose Train in the menu to start one.", id="empty"
        )
        with TabbedContent(id="tabs"):
            with TabPane("Overview", id="overview-tab"):
                with VerticalScroll(id="overview"):
                    with Horizontal(id="tiles"):
                        for name in ("sessions", "examples", "accuracy", "per-answer", "streak"):
                            yield Static(id=f"tile-{name}", classes="tile")
                    yield Static(id="trend-title")
                    yield Sparkline(id="trend")
                    yield Static(
                        "Complete two sessions to see the trend.", id="trend-hint", classes="note"
                    )
                    with Horizontal(id="details"):
                        yield Static(id="last")
                        yield Static(id="practice")
            with TabPane("History", id="history-tab"):
                yield DataTable(id="history", cursor_type="row", zebra_stripes=True)
            with TabPane("Breakdown", id="breakdown-tab"):
                yield DataTable(id="breakdown", cursor_type="none")
            with TabPane("Records", id="records-tab"):
                yield DataTable(id="records", cursor_type="none", zebra_stripes=True)
            with TabPane("Funbox", id="funbox-tab"):
                yield DataTable(id="funbox", cursor_type="none")
                yield DataTable(id="funbox-history", cursor_type="row", zebra_stripes=True)
                yield Static("No funbox sessions yet.", id="funbox-empty", classes="note")
        yield Footer()

    def on_mount(self) -> None:
        headings = {
            "#history": _HISTORY_HEADINGS,
            "#funbox-history": _HISTORY_HEADINGS,
            "#funbox": _GROUP_HEADINGS,
            "#breakdown": _GROUP_HEADINGS,
            "#records": ("Level", "Operations", "Sessions", "Best score", "Best per answer"),
        }
        for selector, columns in headings.items():
            self.query_one(selector, DataTable).add_columns(*columns)
        self.action_reload()

    def action_reload(self) -> None:
        stats = Stats(self._numbra().database_path)
        self._history = stats.history(HISTORY_LIMIT)
        self._funbox_history = stats.funbox_history(HISTORY_LIMIT)
        empty = not self._history and not self._funbox_history
        self.query_one("#empty").display = empty
        self.query_one("#tabs").display = not empty
        self._fill_funbox(stats)
        if not self._history:
            if self._funbox_history:
                self.query_one(TabbedContent).active = "funbox-tab"
            return
        self._fill_overview(stats)
        self._fill("#history", _history_rows(self._history, self._numbra().today()))
        breakdown = stats.breakdown()
        tricks = [
            GroupStats(
                "trick",
                trick.strategy,
                trick.attempts,
                trick.correct,
                trick.average_correct_seconds,
            )
            for trick in stats.trick_stats()
        ]
        self._fill(
            "#breakdown",
            [
                *_section("Difficulty", breakdown.difficulties),
                *_section("Operations", breakdown.operations),
                *_section("Topics", breakdown.topics),
                *_section("Tricks", tricks),
            ],
        )
        self._fill(
            "#records",
            [
                (
                    _level(record.difficulty, record.strict),
                    " ".join((*record.operations, *record.topics)),
                    str(record.sessions),
                    percent(record.best_score_percent),
                    seconds(record.best_average_correct_seconds),
                )
                for record in stats.records()
            ],
        )

    def action_back(self) -> None:
        self.app.pop_screen()

    @on(TabbedContent.TabActivated)
    def _focus_table(self, event: TabbedContent.TabActivated) -> None:
        # Arrow keys then move through the rows of the tab just opened.
        tables = event.pane.query(DataTable)
        if tables:
            tables.last().focus()

    @on(DataTable.RowSelected, "#history")
    def _open_session(self, event: DataTable.RowSelected) -> None:
        self.app.push_screen(SessionScreen(self._history[event.cursor_row]))

    @on(DataTable.RowSelected, "#funbox-history")
    def _open_funbox_session(self, event: DataTable.RowSelected) -> None:
        self.app.push_screen(SessionScreen(self._funbox_history[event.cursor_row]))

    def _fill_funbox(self, stats: Stats) -> None:
        self._fill("#funbox", _section("Modes", stats.funbox_stats()))
        self._fill("#funbox-history", _history_rows(self._funbox_history, self._numbra().today()))
        has_sessions = bool(self._funbox_history)
        self.query_one("#funbox-empty").display = not has_sessions
        self.query_one("#funbox").display = has_sessions
        self.query_one("#funbox-history").display = has_sessions

    def _fill_overview(self, stats: Stats) -> None:
        aggregate = stats.aggregate()
        current, longest = stats.streak(self._numbra().today())
        tiles = {
            "sessions": (str(aggregate.completed_trainings), "sessions"),
            "examples": (str(aggregate.total_examples), "examples"),
            "accuracy": (percent(aggregate.accuracy), "accuracy"),
            "per-answer": (seconds(aggregate.average_response_seconds), "per answer"),
            "streak": (days(current), f"streak, best {longest}"),
        }
        for name, (value, label) in tiles.items():
            self.query_one(f"#tile-{name}", Static).update(
                Text.assemble((value, "bold"), "\n", (label, "dim"))
            )

        scores = [record.score_percent for record in self._history]
        trend = len(scores) >= 2
        self.query_one("#trend-title", Static).update(
            Text.assemble(
                (f"Score over the last {len(scores)} sessions", "bold"),
                f"   best {percent(max(scores))}   average {percent(sum(scores) / len(scores))}",
            )
            if trend
            else Text("Score", style="bold")
        )
        sparkline = self.query_one("#trend", Sparkline)
        sparkline.display = trend
        sparkline.data = list(reversed(scores)) if trend else None
        self.query_one("#trend-hint").display = not trend

        last = self._history[0]
        self.query_one("#last", Static).update(
            Text.assemble(
                ("Last session\n", "bold"),
                grade_text(last.score_percent),
                f"  {percent(last.score_percent)}  {_when(last, self._numbra().today())}\n",
                f"{last.correct_answers} of {last.total_examples} correct, "
                f"{_level(last.difficulty, last.strict)}\n",
                f"{seconds(last.average_response_seconds)} per answer",
            )
        )
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


_RESULT_TEXT = {
    "timeout": Text("time", style="yellow"),
    "correct": Text("✓", style="green"),
    "wrong": Text("✗", style="red"),
}


class SessionScreen(Screen[None]):
    """Every example of one saved session; Esc returns to Results."""

    BINDINGS = [Binding("escape", "back", "Back")]
    DEFAULT_CSS = """
    SessionScreen #session-summary { padding: 1 2; height: auto; }
    SessionScreen DataTable { height: 1fr; }
    """

    def __init__(self, record: TrainingRecord) -> None:
        super().__init__()
        self._record = record

    def compose(self) -> ComposeResult:
        record = self._record
        today = cast("NumbraApp", self.app).today()
        yield Header()
        yield Static(
            Text.assemble(
                grade_text(record.score_percent),
                (f"  {percent(record.score_percent)}", "bold"),
                f"   {record.correct_answers} of {record.total_examples} correct   "
                f"{_level(record.difficulty, record.strict)}   {_when(record, today)}",
            ),
            id="session-summary",
        )
        yield DataTable(id="attempts", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns(
            "#", "Stage", "Expression", "Your answer", "Answer", "Result", "Time", "Score"
        )
        stats = Stats(cast("NumbraApp", self.app).database_path)
        for item in stats.attempts(self._record.identifier):
            result = "timeout" if item.timed_out else "correct" if item.is_correct else "wrong"
            table.add_row(
                str(item.number),
                f"{item.stage_number} {item.kind}",
                item.expression,
                item.user_answer or "—",
                item.correct_answer,
                _RESULT_TEXT[result],
                seconds(item.elapsed_seconds),
                f"{item.score:.2f}",
            )
        table.focus()

    def action_back(self) -> None:
        self.app.pop_screen()
