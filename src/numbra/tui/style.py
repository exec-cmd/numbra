"""Shared presentation helpers for the TUI screens."""

from rich.text import Text

from ..core.challenge import grade_for_score

GRADE_STYLE = {"S": "bold green", "A": "green", "B": "cyan", "C": "yellow", "D": "red"}


def grade_text(score_percent: float) -> Text:
    grade = grade_for_score(score_percent)
    return Text(grade, style=GRADE_STYLE[grade])


def percent(value: float) -> str:
    return f"{value:.0%}"


def seconds(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f} s"


def days(count: int) -> str:
    return f"{count} day" if count == 1 else f"{count} days"


def display_expression(expression: str) -> str:
    return expression.replace(" * ", " × ").replace(" / ", " ÷ ").replace(" - ", " − ")
