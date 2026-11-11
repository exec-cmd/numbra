"""Tricks reference: the same content as ``numbra tricks``, with the full rule of the selected row."""

from __future__ import annotations

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from ..core.generator import trick_levels
from ..core.tricks import TRICKS


class TricksScreen(Screen[None]):
    SUB_TITLE = "Tricks"
    BINDINGS = [Binding("escape", "back", "Back")]
    DEFAULT_CSS = """
    TricksScreen DataTable { height: 1fr; }
    TricksScreen #rule { height: auto; padding: 1 2; border-top: solid $foreground 20%; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(cursor_type="row", zebra_stripes=True, id="tricks")
        yield Static(id="rule")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Trick", "Problem", "Levels")
        levels = trick_levels()
        for trick in TRICKS:
            table.add_row(
                trick.id,
                trick.example.split(" = ", 1)[0],
                " ".join(level.value[0].upper() for level in levels.get(trick.id, ())),
            )
        table.focus()

    @on(DataTable.RowHighlighted)
    def _show_rule(self, event: DataTable.RowHighlighted) -> None:
        trick = TRICKS[event.cursor_row]
        self.query_one("#rule", Static).update(
            Text.assemble(
                (trick.id, "bold"),
                "\n",
                trick.rule,
                "\n",
                (trick.example, "dim"),
                "\n",
                (
                    f"Levels: {', '.join(level.value for level in trick_levels().get(trick.id, ()))}",
                    "dim",
                ),
            )
        )

    def action_back(self) -> None:
        self.app.pop_screen()
