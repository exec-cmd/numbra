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
from textual.widgets import DataTable, Footer, Header, Static, TabbedContent, TabPane

from ..core.challenge import grade_for_score
from ..core.report import METRIC_HELP, area_name
from ..core.stats import AttemptRecord, GroupStats, Stats, TrainingRecord
from ..i18n import t, tn
from .style import (
    GRADE_STYLE,
    days,
    display_expression,
    grade_text,
    percent,
    seconds,
    setup_text,
    translate_bindings,
)

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
        return f"{t('Today')} {moment:%H:%M}"
    if days_ago == 1:
        return f"{t('Yesterday')} {moment:%H:%M}"
    if moment.year == today.year:
        return f"{moment:%b} {moment.day} {moment:%H:%M}"
    return f"{moment:%Y-%m-%d %H:%M}"


def _setup(record: TrainingRecord, *, funbox: bool = False) -> str:
    if funbox:
        return f"{t('funbox')}: {', '.join(t(mode, 'funbox') for mode in (record.operations or record.topics))}"
    return setup_text(record.difficulty, record.strict, record.operations, record.topics)


def _right(value: object) -> Text:
    return Text(str(value), justify="right")


def _bar(accuracy: float) -> Text:
    filled = round(accuracy * _BAR_WIDTH)
    return Text.assemble(
        ("█" * filled, "green" if accuracy >= 0.8 else "yellow" if accuracy >= 0.6 else "red"),
        ("░" * (_BAR_WIDTH - filled), "dim"),
        f" {percent(accuracy)}",
    )


def _group_row(item: GroupStats, context: str = "") -> tuple[Text, ...]:
    accuracy = item.correct / item.attempts if item.attempts else 0.0
    return (
        Text(f"  {t(area_name(item.name), context)}"),
        _bar(accuracy),
        _right(item.attempts),
        _right(seconds(item.average_correct_seconds)),
    )


def _section(title: str, items: Sequence[GroupStats]) -> list[tuple[Text, ...]]:
    if not items:
        return []
    return [
        (Text(title, style="bold"), Text(""), Text(""), Text("")),
        *(
            _group_row(
                item,
                "difficulty"
                if title == t("Difficulty")
                else "trick"
                if title == t("Tricks")
                else "",
            )
            for item in items
        ),
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
    ResultsScreen #trend { height: 1; margin-bottom: 1; }
    ResultsScreen #details { height: auto; }
    ResultsScreen #last, ResultsScreen #practice { width: 1fr; height: auto; }
    ResultsScreen .note { color: $text-muted; }
    ResultsScreen #bests-title { margin-top: 1; text-style: bold; }
    ResultsScreen #skills-note { margin: 1 2; }
    """

    def __init__(self) -> None:
        super().__init__()
        self.sub_title = t(self.SUB_TITLE)
        self._history: list[TrainingRecord] = []
        self._sessions: list[TrainingRecord] = []
        self._funbox_ids: set[int] = set()
        translate_bindings(self)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            t(
                "No finished trainings yet. Choose Train in the menu, finish a run, and your results appear here."
            ),
            id="empty",
        )
        with TabbedContent(id="tabs"):
            with TabPane(t("Overview"), id="overview-tab"):
                with VerticalScroll(id="overview"):
                    with Horizontal(id="tiles"):
                        for name in ("sessions", "accuracy", "time", "streak"):
                            yield Static(id=f"tile-{name}", classes="tile")
                    yield Static(id="trend-title")
                    yield Static(id="trend")
                    yield Static(
                        t("Complete two sessions to see the trend."),
                        id="trend-hint",
                        classes="note",
                    )
                    with Horizontal(id="details"):
                        yield Static(id="last")
                        yield Static(id="practice")
                    yield Static(t("Personal bests"), id="bests-title")
                    yield DataTable(id="bests", cursor_type="none", show_cursor=False)
            with TabPane(t("Sessions"), id="sessions-tab"):
                yield DataTable(id="sessions", cursor_type="row", zebra_stripes=True)
            with TabPane(t("Skills"), id="skills-tab"):
                yield DataTable(id="skills", cursor_type="none")
                yield Static(
                    t(
                        "Accuracy bar: green 80%+, yellow 60%+, red below. Time is per correct answer."
                    ),
                    id="skills-note",
                    classes="note",
                )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#sessions", DataTable).add_columns(*(t(item) for item in _SESSION_HEADINGS))
        self.query_one("#bests", DataTable).add_columns(
            t("Setup"), t("Sessions"), t("Best score"), t("Best time")
        )
        self.query_one("#skills", DataTable).add_columns(*(t(item) for item in _GROUP_HEADINGS))
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
            *_section(t("Operations"), breakdown.operations),
            *_section(t("Topics"), breakdown.topics),
            *_section(t("Tricks"), tricks),
            *_section(t("Difficulty"), breakdown.difficulties),
            *_section(t("Funbox (experimental)"), stats.funbox_stats()),
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
                    setup_text(record.difficulty, record.strict, record.operations, record.topics),
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
            "sessions": (
                str(aggregate.completed_trainings),
                tn(aggregate.completed_trainings, "session", "sessions"),
                t("completed"),
            ),
            "accuracy": (percent(aggregate.accuracy), t("accuracy"), t("share correct")),
            "time": (
                seconds(aggregate.average_correct_seconds),
                t("time"),
                t("per correct answer"),
            ),
            "streak": (
                days(current),
                t("streak, best {best}").format(best=longest),
                t("days in a row"),
            ),
        }
        for name, (value, label, hint) in tiles.items():
            self.query_one(f"#tile-{name}", Static).update(
                Text.assemble((value, "bold"), "\n", label, "\n", (hint, "dim"))
            )

        scores = [record.score_percent for record in self._history]
        trend = len(scores) >= 2
        trend_widget = self.query_one("#trend", Static)
        available_width = max(1, self.size.width - 4) if self.size.width else 60
        shown_scores = list(reversed(scores))[-available_width:]
        trend_title = t("Score, last {sessions} (oldest left)").format(
            sessions=tn(len(shown_scores), "{n} session", "{n} sessions").format(
                n=len(shown_scores)
            )
        )
        title = (
            Text.assemble(
                (
                    trend_title,
                    "bold",
                ),
                "   "
                + t("best {best}, average {average}").format(
                    best=percent(max(scores)), average=percent(sum(scores) / len(scores))
                ),
                (f"   {t('scale 0–100%')}", "dim"),
            )
            if trend
            else Text(
                trend_title,
                style="bold",
            )
        )
        self.query_one("#trend-title", Static).update(title)
        bars = Text()
        for score in shown_scores:
            grade = grade_for_score(score)
            index = min(8, max(1, round(score * 8))) if score > 0 else 0
            bars.append("·" if index == 0 else " ▁▂▃▄▅▆▇█"[index], GRADE_STYLE[grade])
        trend_widget.update(bars)
        trend_widget.display = trend
        self.query_one("#trend-hint").display = not trend

        last_widget = self.query_one("#last", Static)
        if self._history:
            last = self._history[0]
            last_widget.display = True
            last_widget.update(
                Text.assemble(
                    (t("Last session") + "\n", "bold"),
                    grade_text(last.score_percent),
                    f" {percent(last.score_percent)}, {_when(last, self._numbra().today())}\n",
                    t("{correct} of {total} correct").format(
                        correct=last.correct_answers, total=last.total_examples
                    )
                    + f", {_setup(last)}\n",
                    f"{seconds(last.average_correct_seconds)} {t('per correct answer')}",
                )
            )
        else:
            last_widget.display = False
        weak = stats.weak_spots()
        practice = Text.assemble((f"{t('Practise next')}\n", "bold"))
        if weak:
            width = max(len(t(area_name(item.name))) for item in weak)
            for item in weak:
                practice.append(f"{t(area_name(item.name)):<{width}}  ")
                practice.append_text(_bar(item.accuracy))
                practice.append("\n")
        else:
            practice.append(
                t(
                    "Nothing stands out yet. Areas with at least 5 attempts and a miss show up here."
                ),
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

    def __init__(self) -> None:
        super().__init__()
        translate_bindings(self)

    def compose(self) -> ComposeResult:
        table = Table.grid(padding=(0, 2))
        for name, meaning in METRIC_HELP.items():
            table.add_row(Text(t(name), style="bold"), t(meaning))
        box = Static(table, id="legend")
        box.border_title = t("Metrics")
        box.border_subtitle = t("Esc closes")
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
        self.sub_title = t(self.SUB_TITLE)
        self._record = record
        self._funbox = funbox
        self._attempts: list[AttemptRecord] = []
        self._mistakes_only = False
        translate_bindings(self)

    def compose(self) -> ComposeResult:
        record = self._record
        today = cast("NumbraApp", self.app).today()
        yield Header()
        yield Static(
            Text.assemble(
                grade_text(record.score_percent),
                (f" {percent(record.score_percent)}", "bold"),
                f"   {t('{correct} of {total} correct').format(correct=record.correct_answers, total=record.total_examples)}   "
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
            *(
                t(item)
                for item in (
                    "#",
                    "Stage",
                    "Expression",
                    "Your answer",
                    "Answer",
                    "Result",
                    "Time",
                    "Score",
                )
            )
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
            note.update(t("No mistakes"))
        elif self._mistakes_only:
            note.update(t("Showing mistakes only (m: show all)"))
        else:
            note.update(
                f"✗ {tn(n, '{n} mistake', '{n} mistakes').format(n=n)}   ({t('m: show mistakes only')})"
            )
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
                Text(
                    f"{item.stage_number} {t(item.kind, 'stage')}",
                    style=style if style != "green" else "",
                ),
                Text(display_expression(item.expression), style=style if style != "green" else ""),
                _right(item.user_answer or "—"),
                _right(item.correct_answer),
                Text(result if result in ("✓", "✗") else t(result), style=style),
                _right(seconds(item.elapsed_seconds)),
                _right(f"{item.score:.2f}"),
            )
            row_style = style if style != "green" else ""
            for cell in values:
                cell.stylize(row_style)
            table.add_row(*values)

    def action_back(self) -> None:
        self.app.pop_screen()
