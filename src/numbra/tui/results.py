"""Results screen: saved sessions, progress and group statistics. Numbers come from ``core``."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, cast

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Sparkline, Static, TabbedContent, TabPane

from ..core.challenge import grade_for_score
from ..core.stats import GroupStats, Stats, TrainingRecord

if TYPE_CHECKING:
    from .app import NumbraApp

# Newest sessions shown in History and Progress; the summary totals cover every session.
HISTORY_LIMIT = 1000
_GROUP_HEADINGS = ("Group", "Attempts", "Accuracy", "Avg correct")


def _days(count: int) -> str:
    return f"{count} day" if count == 1 else f"{count} days"


def _seconds(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}s"


def _when(record: TrainingRecord) -> str:
    return datetime.fromtimestamp(record.started_at).astimezone().strftime("%Y-%m-%d %H:%M")


def _mode(strict: bool) -> str:
    return "strict" if strict else "soft"


def _group_rows(sections: Sequence[Sequence[GroupStats]]) -> list[tuple[str, ...]]:
    return [
        (
            f"{item.kind}: {item.name}",
            str(item.attempts),
            f"{item.accuracy:.1%}",
            _seconds(item.average_correct_seconds),
        )
        for section in sections
        for item in section
    ]


class ResultsScreen(Screen[None]):
    BINDINGS = [Binding("escape", "back", "Back"), Binding("r", "reload", "Reload")]
    DEFAULT_CSS = """
    ResultsScreen #summary { padding: 0 2; height: auto; }
    ResultsScreen #empty { padding: 1 2; }
    ResultsScreen #tabs { height: 1fr; }
    ResultsScreen #progress { padding: 0 2; height: auto; }
    ResultsScreen #trend { height: 3; margin: 1 0; }
    ResultsScreen .note { color: $text-muted; padding: 1 0; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._history: list[TrainingRecord] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="summary")
        yield Static("No completed challenges yet.", id="empty")
        with TabbedContent(id="tabs"):
            with TabPane("History"):
                yield DataTable(id="history", cursor_type="row", zebra_stripes=True)
            with TabPane("Progress"):
                yield Static(id="progress")
                yield Sparkline(id="trend")
                yield Static(
                    "Complete two sessions to see the trend.", id="trend-hint", classes="note"
                )
            with TabPane("Breakdown"):
                yield DataTable(id="breakdown", zebra_stripes=True)
            with TabPane("Weak spots"):
                yield DataTable(id="weak", zebra_stripes=True)
                yield Static(
                    "No weak spots yet: at least 5 attempts with a miss are needed",
                    id="weak-note",
                    classes="note",
                )
            with TabPane("Records"):
                yield DataTable(id="records", zebra_stripes=True)
            with TabPane("Tricks"):
                yield DataTable(id="tricks", zebra_stripes=True)
            # A later change adds the Funbox tab here, after Tricks.
        yield Footer()

    def on_mount(self) -> None:
        headings = {
            "#history": (
                "Date",
                "Difficulty",
                "Mode",
                "Correct",
                "Accuracy",
                "Score",
                "Grade",
                "Avg",
                "Duration",
            ),
            "#breakdown": _GROUP_HEADINGS,
            "#weak": _GROUP_HEADINGS,
            "#records": (
                "Difficulty",
                "Mode",
                "Operations",
                "Sessions",
                "Best score",
                "Best avg correct",
            ),
            "#tricks": ("Trick", "Attempts", "Accuracy", "Avg correct"),
        }
        for selector, columns in headings.items():
            self.query_one(selector, DataTable).add_columns(*columns)
        self.action_reload()
        if self._history:
            self.query_one("#history", DataTable).focus()

    def action_reload(self) -> None:
        stats = Stats(self._numbra().database_path)
        self._history = stats.history(HISTORY_LIMIT)
        empty = not self._history
        self.query_one("#empty").display = empty
        self.query_one("#summary").display = not empty
        self.query_one("#tabs").display = not empty
        if empty:
            return
        self._fill_summary(stats)
        self._fill_history()
        self._fill_progress()
        breakdown = stats.breakdown()
        self._fill(
            "#breakdown",
            _group_rows((breakdown.difficulties, breakdown.operations, breakdown.topics)),
        )
        weak = _group_rows((stats.weak_spots(),))
        self._fill("#weak", weak)
        self.query_one("#weak-note").display = not weak
        self._fill(
            "#records",
            [
                (
                    record.difficulty,
                    _mode(record.strict),
                    ", ".join((*record.operations, *record.topics)),
                    str(record.sessions),
                    f"{record.best_score_percent:.1%}",
                    _seconds(record.best_average_correct_seconds),
                )
                for record in stats.records()
            ],
        )
        self._fill(
            "#tricks",
            [
                (
                    trick.strategy,
                    str(trick.attempts),
                    f"{trick.correct / trick.attempts:.1%}",
                    _seconds(trick.average_correct_seconds),
                )
                for trick in stats.trick_stats()
            ],
        )

    def action_back(self) -> None:
        self.app.pop_screen()

    @on(DataTable.RowSelected, "#history")
    def _open_session(self, event: DataTable.RowSelected) -> None:
        self.app.push_screen(SessionScreen(self._history[event.cursor_row]))

    def _fill_summary(self, stats: Stats) -> None:
        aggregate = stats.aggregate()
        current, longest = stats.streak(self._numbra().today())
        last = self._history[0].score_percent
        self.query_one("#summary", Static).update(
            f"[bold]Sessions:[/bold] {aggregate.completed_trainings} · "
            f"[bold]Examples:[/bold] {aggregate.total_examples} · "
            f"[bold]Accuracy:[/bold] {aggregate.accuracy:.1%} · "
            f"[bold]Average answer:[/bold] {aggregate.average_response_seconds:.2f}s\n"
            f"[bold]Streak:[/bold] {_days(current)} (best {longest}) · "
            f"[bold]Last grade:[/bold] {grade_for_score(last)} ({last:.1%})"
        )

    def _fill_history(self) -> None:
        table = self.query_one("#history", DataTable)
        table.clear()
        for record in self._history:
            table.add_row(
                _when(record),
                record.difficulty,
                _mode(record.strict),
                f"{record.correct_answers}/{record.total_examples}",
                f"{record.accuracy:.1%}",
                f"{record.score_percent:.1%}",
                grade_for_score(record.score_percent),
                _seconds(record.average_response_seconds),
                f"{record.actual_duration_seconds:.1f}s",
            )

    def _fill_progress(self) -> None:
        scores = [record.score_percent for record in self._history]
        self.query_one("#progress", Static).update(
            f"[bold]Best:[/bold] {max(scores):.1%} · [bold]Last:[/bold] {scores[0]:.1%} · "
            f"[bold]Average:[/bold] {sum(scores) / len(scores):.1%} over {len(scores)} sessions"
        )
        trend = len(scores) >= 2
        sparkline = self.query_one("#trend", Sparkline)
        sparkline.display = trend
        sparkline.data = list(reversed(scores)) if trend else None
        self.query_one("#trend-hint").display = not trend

    def _fill(self, selector: str, rows: Iterable[Sequence[str]]) -> None:
        table = self.query_one(selector, DataTable)
        table.clear()
        table.add_rows(rows)

    def _numbra(self) -> NumbraApp:
        return cast("NumbraApp", self.app)


class SessionScreen(Screen[None]):
    """Every example of one saved session; Esc returns to Results."""

    BINDINGS = [Binding("escape", "back", "Back")]
    DEFAULT_CSS = """
    SessionScreen Static { padding: 0 2; }
    SessionScreen DataTable { height: 1fr; }
    """

    def __init__(self, record: TrainingRecord) -> None:
        super().__init__()
        self._record = record

    def compose(self) -> ComposeResult:
        record = self._record
        yield Header()
        yield Static(
            f"{_when(record)} · {record.difficulty} · {_mode(record.strict)} · "
            f"{record.correct_answers}/{record.total_examples} correct · "
            f"score {record.score_percent:.1%}"
        )
        yield DataTable(id="attempts", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns(
            "Stage",
            "Kind",
            "#",
            "Expression",
            "Your answer",
            "Correct answer",
            "Result",
            "Time",
            "Score",
        )
        stats = Stats(cast("NumbraApp", self.app).database_path)
        for item in stats.attempts(self._record.identifier):
            result = "timeout" if item.timed_out else "✓" if item.is_correct else "✗"
            table.add_row(
                str(item.stage_number),
                item.kind,
                str(item.number),
                item.expression,
                item.user_answer or "—",
                item.correct_answer,
                result,
                f"{item.elapsed_seconds:.2f}s",
                f"{item.score:.2f}",
            )
        table.focus()

    def action_back(self) -> None:
        self.app.pop_screen()
