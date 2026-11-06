"""Tricks reference table, the same content as ``numbra tricks``."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header

from ..core.generator import trick_levels
from ..core.tricks import TRICKS


class TricksScreen(Screen[None]):
    BINDINGS = [Binding("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(cursor_type="row", zebra_stripes=True, id="tricks")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Trick", "Rule", "Example", "Levels")
        levels = trick_levels()
        for trick in TRICKS:
            table.add_row(
                trick.id,
                trick.rule,
                trick.example,
                ", ".join(level.value for level in levels.get(trick.id, ())),
            )
        table.focus()

    def action_back(self) -> None:
        self.app.pop_screen()
