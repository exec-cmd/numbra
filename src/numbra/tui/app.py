"""Interactive entry point: a menu over the training, tricks and later screens."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import date
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList

from ..config import (
    ConfigManager,
    ConfigPaths,
    Settings,
    default_config_paths,
    default_database_path,
)
from .results import ResultsScreen
from .settings import SettingsScreen
from .train import TrainSetupScreen
from .tricks import TricksScreen

# (id, label, screen factory). Add a row to add a menu entry; a None factory quits the app.
MENU: tuple[tuple[str, str, Callable[[], Screen[None]] | None], ...] = (
    ("train", "Train", TrainSetupScreen),
    ("results", "Results", ResultsScreen),
    ("settings", "Settings", SettingsScreen),
    ("tricks", "Tricks", TricksScreen),
    ("quit", "Quit", None),
)


class MenuScreen(Screen[None]):
    BINDINGS = [Binding("q", "quit_app", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield OptionList(*(label for _, label, _ in MENU), id="menu")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    @on(OptionList.OptionSelected, "#menu")
    def _choose(self, event: OptionList.OptionSelected) -> None:
        _, _, factory = MENU[event.option_index]
        if factory is None:
            self.app.exit()
        else:
            self.app.push_screen(factory())

    def action_quit_app(self) -> None:
        self.app.exit()


class NumbraApp(App[None]):
    TITLE = "Numbra"

    def __init__(
        self,
        *,
        settings_loader: Callable[[], Settings] | None = None,
        config_paths: ConfigPaths | None = None,
        database_path: Path | None = None,
        today: Callable[[], date] = date.today,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], Awaitable[object]] = asyncio.sleep,
    ) -> None:
        super().__init__()
        self.config_paths = config_paths or default_config_paths()
        self._settings_loader = settings_loader or (
            lambda: ConfigManager(self.config_paths).load_or_create()
        )
        self.database_path = database_path or default_database_path()
        self.today = today
        self.clock = clock
        self.sleeper = sleeper

    def load_settings(self) -> Settings:
        return self._settings_loader()

    def get_default_screen(self) -> Screen[None]:
        return MenuScreen()
