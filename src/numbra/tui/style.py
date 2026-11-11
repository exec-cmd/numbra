"""Shared presentation helpers for the TUI screens."""

from dataclasses import replace

from rich.text import Text
from textual.dom import DOMNode

from ..core.challenge import grade_for_score
from ..core.report import setup_label
from ..i18n import t, tn

GRADE_STYLE = {"S": "bold green", "A": "green", "B": "cyan", "C": "yellow", "D": "red"}


def grade_text(score_percent: float) -> Text:
    grade = grade_for_score(score_percent)
    return Text(grade, style=GRADE_STYLE[grade])


def percent(value: float) -> str:
    return f"{value:.0%}"


def seconds(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f} s"


def days(count: int) -> str:
    return tn(count, "{n} day", "{n} days").format(n=count)


def setup_text(
    difficulty: str, strict: bool, operations: tuple[str, ...], topics: tuple[str, ...]
) -> str:
    label = setup_label(
        t(difficulty, "difficulty"), False, operations, tuple(t(topic) for topic in topics)
    )
    if not strict:
        return label
    prefix = t(difficulty, "difficulty")
    suffix = label.removeprefix(prefix)
    return f"{prefix}, {t('strict')}{suffix}"


def translate_bindings(node: DOMNode) -> None:
    # shortcut: rewrites Textual's per-instance BindingsMap; re-check on a Textual upgrade.
    for key, items in node._bindings.key_to_bindings.items():
        node._bindings.key_to_bindings[key] = [
            replace(binding, description=t(binding.description)) if binding.description else binding
            for binding in items
        ]


def display_expression(expression: str) -> str:
    return expression.replace(" * ", " × ").replace(" / ", " ÷ ").replace(" - ", " − ")
