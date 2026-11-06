"""Settings screen: every key of numbra.toml with its effective value, edited in place."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Static

from ..config import (
    ConfigError,
    ConfigPaths,
    format_value,
    get_value,
    list_values,
    set_value,
    unset_value,
)

if TYPE_CHECKING:
    from .app import NumbraApp


class SettingsScreen(Screen[None]):
    """Enter edits the selected key as a TOML literal; d resets it to the built-in default."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("d", "reset", "Reset to default"),
        Binding("delete", "reset", show=False),
    ]
    DEFAULT_CSS = """
    SettingsScreen DataTable { height: 1fr; }
    SettingsScreen #path { color: $text-muted; padding: 0 1; }
    SettingsScreen #edit { display: none; }
    SettingsScreen #error { color: $error; height: auto; padding: 0 1; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._editing: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"Config file: {self._paths().main}", id="path")
        yield DataTable(cursor_type="row", zebra_stripes=True, id="settings")
        yield Input(placeholder="New value as TOML, then Enter. Esc cancels.", id="edit")
        yield Static(id="error")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Key", "Value")
        self._refresh()
        table.focus()

    @on(DataTable.RowSelected, "#settings")
    def _open_editor(self, event: DataTable.RowSelected) -> None:
        key = str(event.row_key.value)
        try:
            current = get_value(self._paths(), key)
        except ConfigError as exc:
            self._show_error(str(exc))
            return
        self._editing = key
        edit = self.query_one("#edit", Input)
        edit.value = format_value(current)
        edit.display = True
        self._show_error("")
        edit.focus()

    @on(Input.Submitted, "#edit")
    def _save(self, event: Input.Submitted) -> None:
        if self._editing is None:
            return
        key = self._editing
        try:
            set_value(self._paths(), key, event.value.strip())
        except ConfigError as exc:
            self._show_error(str(exc))  # the editor stays open so the value can be fixed
            return
        self._close_editor()
        self._refresh(select=key)

    def action_reset(self) -> None:
        if self._editing is not None or self.query_one(DataTable).row_count == 0:
            return
        table = self.query_one(DataTable)
        key = str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
        try:
            unset_value(self._paths(), key)
        except ConfigError as exc:
            self._show_error(str(exc))
            return
        self._refresh(select=key)

    def action_back(self) -> None:
        if self._editing is not None:
            self._close_editor()
        else:
            self.app.pop_screen()

    def _close_editor(self) -> None:
        self._editing = None
        self.query_one("#edit", Input).display = False
        self._show_error("")
        self.query_one(DataTable).focus()

    def _refresh(self, select: str | None = None) -> None:
        table = self.query_one(DataTable)
        table.clear()
        self._show_error("")
        try:
            values = list_values(self._paths())
        except ConfigError as exc:
            self._show_error(str(exc))
            return
        for key, value in values:
            table.add_row(key, format_value(value), key=key)
        # An unset seed has no row, so the cursor may have nothing to land on.
        if select is not None and select in {row.key.value for row in table.ordered_rows}:
            table.move_cursor(row=table.get_row_index(select))

    def _show_error(self, message: str) -> None:
        self.query_one("#error", Static).update(Text(message, style="bold red"))

    def _paths(self) -> ConfigPaths:
        return cast("NumbraApp", self.app).config_paths
