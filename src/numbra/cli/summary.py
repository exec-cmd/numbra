"""Rich summary card shared by the terminal and Textual interfaces."""

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..core.challenge import CompletedTraining, grade_for_score
from ..core.report import RECOMMENDATION_TEXT, TrainingReport, area_name
from ..i18n import t, tn

_GRADE_STYLE = {"S": "bold green", "A": "green", "B": "cyan", "C": "yellow", "D": "red"}


def _percent(value: float) -> str:
    return f"{value:.0%}"


def _seconds(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f} s"


def _days(count: int) -> str:
    return tn(count, "{n} day", "{n} days").format(n=count)


def _delta(value: float, *, suffix: str = "") -> Text:
    if value > 0.0005:
        return Text(
            t("▲ {value}{suffix}").format(value=f"{value:.0%}", suffix=suffix), style="green"
        )
    if value < -0.0005:
        return Text(
            t("▼ {value}{suffix}").format(value=f"{-value:.0%}", suffix=suffix), style="red"
        )
    return Text(t("= same as previous" if suffix else "= same"), style="dim")


def summary_card(completed: CompletedTraining, report: TrainingReport) -> RenderableType:
    """Render the same compact post-training summary in both terminal interfaces."""
    funbox = completed.mode == "funbox"
    comparison = None if funbox else report.comparison
    grade = grade_for_score(completed.score_percent)
    numbers = Table.grid(padding=(0, 2))
    numbers.add_column()
    numbers.add_column()
    numbers.add_column()
    numbers.add_row(
        t("Score"),
        _percent(completed.score_percent),
        Text() if comparison is None else _delta(comparison.score_delta, suffix=t(" vs previous")),
    )
    numbers.add_row(
        t("Accuracy"),
        f"{completed.correct_answers}/{completed.total_examples}",
        Text() if comparison is None else _delta(comparison.accuracy_delta),
    )
    time_delta: Text | str = ""
    if comparison is not None and comparison.correct_time_delta is not None:
        delta = comparison.correct_time_delta
        if delta < -0.0005:
            time_delta = Text(
                t("▼ {seconds} s faster").format(seconds=f"{-delta:.1f}"), style="green"
            )
        elif delta > 0.0005:
            time_delta = Text(t("▲ {seconds} s slower").format(seconds=f"{delta:.1f}"), style="red")
        else:
            time_delta = Text(t("= same"), style="dim")
    numbers.add_row(t("Time"), _seconds(completed.average_correct_seconds), time_delta)
    if not funbox and (report.personal_best is not None or report.is_new_best):
        if report.is_new_best:
            best = Text(t("New personal best!"), style="bold green")
            value = _percent(completed.score_percent)
        else:
            best = Text(
                t("{percent} to go").format(percent=_percent(-report.score_vs_best))
                if report.score_vs_best is not None and report.score_vs_best < 0
                else t("matched"),
                style="dim",
            )
            value = _percent(report.personal_best or 0)
        numbers.add_row(t("Best"), value, best)

    grade_box = Panel(
        Text(grade, style=f"{_GRADE_STYLE[grade]} bold", justify="center"),
        box=box.ROUNDED,
        width=7,
        padding=(0, 1),
    )
    heading = Table.grid(padding=(0, 2))
    heading.add_column()
    heading.add_column()
    heading.add_row(grade_box, numbers)

    stages = Table(box=None, padding=(0, 2), show_edge=False)
    stages.add_column(t("Stage"))
    stages.add_column(t("Correct"), justify="right")
    stages.add_column(t("Timeouts"), justify="right")
    order = ("slow", "normal", "fast")
    for stage_tally in sorted(report.stage_kinds, key=lambda item: order.index(item.kind.value)):
        stages.add_row(
            t(stage_tally.kind.value, "stage"),
            f"{stage_tally.correct}/{stage_tally.total}",
            str(stage_tally.timeouts),
        )

    parts: list[RenderableType] = []
    if funbox:
        parts.append(Text(t("Funbox (experimental)"), style="bold"))
    parts.extend((heading, Text(""), stages, Text("")))
    if report.weakest is not None:
        name, weak_tally = report.weakest
        parts.append(
            Text(f"{t('Weakest')}: {t(area_name(name))} {weak_tally.correct}/{weak_tally.total}")
        )
    parts.append(
        Text(
            t("Streak: {days} (best {best})").format(
                days=_days(report.current_streak), best=report.longest_streak
            )
        )
    )
    if report.recommendation is not None:
        parts.append(Text(t(RECOMMENDATION_TEXT[report.recommendation])))
    return Group(*parts)
