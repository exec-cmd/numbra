"""Settings screen for editing the effective values in numbra.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, cast

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    OptionList,
    SelectionList,
    Static,
)
from textual.widgets.selection_list import Selection

from ..config import (
    ConfigError,
    ConfigPaths,
    format_value,
    get_value,
    list_values,
    set_value,
    unset_value,
)
from ..core.funbox import FunboxMode
from ..core.models import Difficulty, Operation
from ..core.report import OPERATION_SYMBOLS, area_name
from ..i18n import t
from .style import translate_bindings

if TYPE_CHECKING:
    from .app import NumbraApp


_LABELS: dict[str, tuple[str, str, str]] = {
    "ui.language": (
        "Interface",
        "Language",
        "auto follows the system locale; applies after restart",
    ),
    "challenge.duration_minutes": ("Training", "Length, minutes", "How long one training lasts."),
    "challenge.difficulty": (
        "Training",
        "Difficulty",
        "The default level for new trainings: easy, normal or hard.",
    ),
    "challenge.stages": (
        "Training",
        "Stages",
        "How many timed stages a training has; they cycle slow, normal, fast.",
    ),
    "challenge.operations": ("Training", "Operations", "Operations used by default."),
    "features.sqrt": ("Topics", "Square roots", "Include square roots in new trainings."),
    "features.trig": ("Topics", "Trigonometry", "Include trigonometry in new trainings."),
    "features.log": ("Topics", "Logarithms", "Include logarithms in new trainings."),
    "features.power": ("Topics", "Powers", "Include powers in new trainings."),
    "features.identities": ("Topics", "Identities", "Include identities in new trainings."),
    "features.tricks": ("Topics", "Tricks", "Include tricks in new trainings."),
    "funbox.modes": ("Funbox", "Modes", "Funbox modes preselected on the Funbox screen."),
    "timing.operation_bonus_enabled": (
        "Time limits",
        "Operation bonus",
        "Give extra seconds for harder operations.",
    ),
    **{
        f"timing.operation_bonus_seconds.{op}": (
            "Time limits",
            f"Extra time for {OPERATION_SYMBOLS[op]}, seconds",
            f"Extra seconds per {OPERATION_SYMBOLS[op]} in an example.",
        )
        for op in ("+", "-", "*", "/", "^")
    },
    **{
        f"stages.{kind}.limit_seconds": (
            "Time limits",
            f"{kind.title()} stage, seconds",
            f"Time for one example in a {kind} stage.",
        )
        for kind in ("slow", "normal", "fast")
    },
    **{
        f"difficulties.{level}.{field}": (
            f"Difficulty: {level}",
            label,
            f"{help_text} used to build examples at this level.",
        )
        for level in ("easy", "normal", "hard")
        for field, label, help_text in (
            ("min_value", "Smallest number", "The smallest number"),
            ("max_value", "Largest number", "The largest number"),
            ("min_terms", "Fewest numbers", "The fewest numbers in an example"),
            ("max_terms", "Most numbers", "The most numbers in an example"),
            ("max_result", "Largest result", "The largest result"),
        )
    },
}

_INTEGER_KEYS = {
    "challenge.duration_minutes",
    "challenge.stages",
    *(f"stages.{kind}.limit_seconds" for kind in ("slow", "normal", "fast")),
    *(
        f"difficulties.{level}.{field}"
        for level in ("easy", "normal", "hard")
        for field in ("min_value", "max_value", "min_terms", "max_terms", "max_result")
    ),
    *(f"timing.operation_bonus_seconds.{op}" for op in ("+", "-", "*", "/", "^")),
    "challenge.seed",
}
_CANONICAL = {
    "challenge.operations": tuple(op.value for op in Operation),
    "funbox.modes": tuple(mode.value for mode in FunboxMode),
}


class SettingsScreen(Screen[None]):
    """Edit a setting or restore its built-in default."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("d", "reset", "Reset to default"),
        Binding("delete", "reset", show=False),
    ]
    DEFAULT_CSS = """
    SettingsScreen DataTable { height: 1fr; }
    SettingsScreen #path, SettingsScreen #help { color: $text-muted; padding: 0 1; }
    SettingsScreen #path { height: 1; text-wrap: nowrap; text-overflow: ellipsis; }
    SettingsScreen #help { height: auto; }
    SettingsScreen #error { color: $error; height: auto; padding: 0 1; }
    """
    SUB_TITLE = "Settings"

    def __init__(self) -> None:
        super().__init__()
        self.sub_title = t(self.SUB_TITLE)
        translate_bindings(self)

    def compose(self) -> ComposeResult:
        path = f"Config file: {self._paths().main}".replace(str(Path.home()), "~", 1)
        yield Header()
        yield Static(t("Config file: {path}").format(path=path), id="path")
        yield DataTable(cursor_type="row", zebra_stripes=True, id="settings")
        yield Static(id="help")
        yield Static(id="error")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns(t("Setting"), t("Value"))
        self._refresh()
        table.focus()

    @on(DataTable.RowHighlighted, "#settings")
    def _highlighted(self, event: DataTable.RowHighlighted) -> None:
        key = str(event.row_key.value)
        self.query_one("#help", Static).update(
            "" if key.startswith("group:") else t(_metadata(key)[2])
        )

    @on(DataTable.RowSelected, "#settings")
    def _open_editor(self, event: DataTable.RowSelected) -> None:
        key = str(event.row_key.value)
        if key.startswith("group:"):
            return
        try:
            current = get_value(self._paths(), key)
        except ConfigError as exc:
            self._show_error(str(exc))
            return
        _, label, help_text = _metadata(key)
        if isinstance(current, bool):
            self._save(key, format_value(not current))
            return
        modal = SettingEditor(self._paths(), key, label, help_text, current)
        self.app.push_screen(modal, lambda saved: self._after_edit(key, saved))

    def _after_edit(self, key: str | None, saved: bool | None) -> None:
        if saved and key is not None:
            self._refresh(select=key)
            if key == "ui.language":
                self.notify(t("Language changes after restart"))
        self.query_one(DataTable).focus()

    def action_reset(self) -> None:
        table = self.query_one(DataTable)
        if table.row_count == 0:
            return
        key = str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
        if key.startswith("group:"):
            return
        try:
            unset_value(self._paths(), key)
        except ConfigError as exc:
            self._show_error(str(exc))
            return
        self._refresh(select=key)

    def action_back(self) -> None:
        self.app.pop_screen()

    def _save(self, key: str, raw: str) -> bool:
        try:
            set_value(self._paths(), key, raw)
        except ConfigError as exc:
            self._show_error(str(exc))
            return False
        self._show_error("")
        self._refresh(select=key)
        return True

    def _refresh(self, select: str | None = None) -> None:
        table = self.query_one(DataTable)
        table.clear()
        self._show_error("")
        try:
            values = list_values(self._paths())
        except ConfigError as exc:
            self._show_error(str(exc))
            return
        grouped: dict[str, list[tuple[str, object]]] = {}
        for key, value in values:
            grouped.setdefault(_metadata(key)[0], []).append((key, value))
        order = [
            "Training",
            "Topics",
            "Funbox",
            "Time limits",
            *(f"Difficulty: {level}" for level in ("easy", "normal", "hard")),
            "Other",
            "Interface",
        ]
        for group in order:
            rows = grouped.get(group, [])
            if not rows:
                continue
            table.add_row(Text(t(group), style="bold"), Text(""), key=f"group:{group}")
            for key, value in rows:
                _, label, _ = _metadata(key)
                table.add_row(Text(f"  {t(label)}"), _display_value(key, value), key=key)
        if select is not None and select in {row.key.value for row in table.ordered_rows}:
            table.move_cursor(row=table.get_row_index(select))
        elif table.row_count > 1:
            table.move_cursor(row=1)
        key = str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
        self.query_one("#help", Static).update(t(_metadata(key)[2]))

    def _show_error(self, message: str) -> None:
        self.query_one("#error", Static).update(Text(message, style="bold red"))

    def _paths(self) -> ConfigPaths:
        return cast("NumbraApp", self.app).config_paths


class SettingEditor(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    SettingEditor { align: center middle; }
    SettingEditor > Vertical { width: 60; height: auto; border: round $accent; padding: 1 2; background: $surface; }
    SettingEditor #modal-help { color: $text-muted; height: auto; }
    SettingEditor #modal-error { color: $error; height: auto; }
    SettingEditor SelectionList { height: auto; max-height: 12; }
    """

    def __init__(
        self, paths: ConfigPaths, key: str, label: str, help_text: str, current: object
    ) -> None:
        super().__init__()
        self.paths = paths
        self.key = key
        self.label = label
        self.help_text = help_text
        self.current = current
        self.kind = (
            "difficulty"
            if key == "challenge.difficulty"
            else "language"
            if key == "ui.language"
            else "list"
            if key in _CANONICAL
            else "text"
        )
        translate_bindings(self)

    def compose(self) -> ComposeResult:
        box = Vertical(
            Static(Text(t(self.label), style="bold"), id="modal-title"),
            Static(t(self.help_text), id="modal-help"),
            self._control(),
            Static(id="modal-error"),
            Button(t("Save"), id="save"),
        )
        box.border_subtitle = t("Enter saves, Esc cancels")
        yield box

    def on_mount(self) -> None:
        if self.kind == "text":
            self.query_one(Input).focus()
        else:
            self.query_one(
                OptionList if self.kind in ("difficulty", "language") else SelectionList
            ).focus()

    def _control(self) -> Input | OptionList | SelectionList:
        if self.kind == "difficulty":
            control = OptionList(
                *(t(difficulty.value, "difficulty") for difficulty in Difficulty), id="value"
            )
            control.highlighted = [difficulty.value for difficulty in Difficulty].index(
                str(self.current)
            )
            return control
        if self.kind == "language":
            choices = ("auto", "en", "ru")
            labels = ("auto (system)", "English", "Русский")
            control = OptionList(*(t(label) for label in labels), id="value")
            control.highlighted = choices.index(str(self.current))
            return control
        if self.kind == "list":
            selected = set(self.current) if isinstance(self.current, list) else set()
            if self.key == "challenge.operations":
                return SelectionList(
                    *(
                        Selection(
                            f"{OPERATION_SYMBOLS[item]} {t(area_name(item))}",
                            item,
                            item in selected,
                        )
                        for item in _CANONICAL[self.key]
                    ),
                    id="value",
                )
            return SelectionList(
                *(Selection(t(item), item, item in selected) for item in _CANONICAL[self.key]),
                id="value",
            )
        initial = str(self.current) if self.current is not None else ""
        return Input(value=initial, id="value")

    @on(OptionList.OptionSelected, "#value")
    def _difficulty_selected(self, event: OptionList.OptionSelected) -> None:
        if self.kind == "difficulty":
            self._save(format_value(tuple(Difficulty)[event.option_index].value))
        elif self.kind == "language":
            self._save(format_value(("auto", "en", "ru")[event.option_index]))
        elif self.kind == "list":
            self._save_list()

    @on(Button.Pressed, "#save")
    def _save_pressed(self) -> None:
        if self.kind == "difficulty":
            options = self.query_one(OptionList)
            if options.highlighted is not None:
                self._save(format_value(tuple(Difficulty)[options.highlighted].value))
        elif self.kind == "language":
            options = self.query_one(OptionList)
            if options.highlighted is not None:
                self._save(format_value(("auto", "en", "ru")[options.highlighted]))
        elif self.kind == "list":
            self._save_list()
        else:
            self._save_input()

    def _save_list(self) -> None:
        selected = set(cast(SelectionList[str], self.query_one(SelectionList)).selected)
        values = [value for value in _CANONICAL[self.key] if value in selected]
        self._save(format_value(values))

    @on(Input.Submitted, "#value")
    def _input_submitted(self) -> None:
        self._save_input()

    def _save_input(self) -> None:
        text = self.query_one(Input).value.strip()
        if self.key in _INTEGER_KEYS:
            try:
                value = int(text)
            except ValueError:
                self._error("Enter a whole number")
                return
            raw = format_value(value)
        else:
            try:
                tomllib.loads(f"value = {text}")
            except tomllib.TOMLDecodeError:
                raw = format_value(text)
            else:
                raw = text
        self._save(raw)

    def _save(self, raw: str) -> None:
        try:
            set_value(self.paths, self.key, raw)
        except ConfigError as exc:
            self._error(str(exc))
            return
        self.dismiss(True)

    def _error(self, message: str) -> None:
        self.query_one("#modal-error", Static).update(message)

    def action_cancel(self) -> None:
        self.dismiss(False)


def _metadata(key: str) -> tuple[str, str, str]:
    if key in _LABELS:
        return _LABELS[key]
    if key.startswith("timing.operation_bonus_seconds."):
        symbol = key.rsplit(".", 1)[-1]
        symbol = OPERATION_SYMBOLS.get(symbol, symbol)
        return (
            "Time limits",
            f"Extra time for {symbol}, seconds",
            f"Extra seconds per {symbol} in an example.",
        )
    return "Other", key, ""


def _display_value(key: str, value: object) -> str:
    if isinstance(value, bool):
        return t("on" if value else "off")
    if key == "challenge.difficulty":
        return t(str(value), "difficulty")
    if key == "ui.language":
        return t({"auto": "auto (system)", "en": "English", "ru": "Русский"}[str(value)])
    if isinstance(value, list):
        return " ".join(
            OPERATION_SYMBOLS[str(item)] if str(item) in OPERATION_SYMBOLS else t(str(item))
            for item in value
        ) or t("none")
    return str(value)
