"""Interactive entry point: a menu over the training, tricks and later screens."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable
from datetime import date
from pathlib import Path
from typing import cast

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static

from ..config import (
    ConfigError,
    ConfigManager,
    ConfigPaths,
    Settings,
    default_config_paths,
    default_database_path,
)
from ..core.report import area_name
from ..core.stats import Stats
from ..i18n import get_language, resolve_language, set_language, t, tn
from .funbox import FunboxSetupScreen
from .results import ResultsScreen
from .settings import SettingsScreen
from .style import days, grade_text, percent, translate_bindings
from .train import TrainSetupScreen
from .tricks import TricksScreen

MENU: tuple[tuple[str, str, str, str, Callable[[], Screen[None]] | None], ...] = (
    (
        "train",
        "Train",
        "t",
        "A timed run with your saved settings. You can change them before the start.",
        TrainSetupScreen,
    ),
    (
        "results",
        "Results",
        "r",
        "Your progress: scores over time, sessions, and strong and weak areas.",
        ResultsScreen,
    ),
    (
        "settings",
        "Settings",
        "s",
        "Default difficulty, length, topics and time limits.",
        SettingsScreen,
    ),
    ("tricks", "Tricks", "k", "Mental-math shortcuts and the rule behind each one.", TricksScreen),
    (
        "funbox",
        "Funbox",
        "f",
        "Experimental puzzles: fractions, substitution, equations, logic, derivatives. Not counted in records.",
        FunboxSetupScreen,
    ),
    ("quit", "Quit", "q", "Leave numbra.", None),
)


def terminal_theme(colorfgbg: str | None = None) -> str:
    """ANSI theme, so the interface uses the terminal's own colors and background."""
    # COLORFGBG ("15;0": foreground;background) is set by some terminals; 7 and 15 are light.
    value = os.environ.get("COLORFGBG", "") if colorfgbg is None else colorfgbg
    return "ansi-light" if value.rsplit(";", 1)[-1] in ("7", "15") else "ansi-dark"


class MenuScreen(Screen[None]):
    SUB_TITLE = "Menu"
    BINDINGS = [
        *(
            Binding(key, f"open('{item_id}')", label, show=False)
            for item_id, label, key, _, _ in MENU
            if item_id != "quit"
        ),
        Binding("q", "quit_app", "Quit"),
    ]
    DEFAULT_CSS = """
    MenuScreen Horizontal { height: 1fr; }
    MenuScreen #menu-side {
        width: 34; height: 1fr; padding: 1 2;
    }
    MenuScreen #logo { color: $accent; text-style: bold; margin-bottom: 1; }
    MenuScreen OptionList, MenuScreen OptionList:focus {
        width: 1fr; height: auto; border: none; background: transparent;
    }
    MenuScreen #about {
        width: 1fr; height: 1fr; padding: 1 2; border-left: solid $foreground 20%;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.sub_title = t(self.SUB_TITLE)
        self._stats_block: Table | Text | None = None
        translate_bindings(self)

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Vertical(
                Static("numbra", id="logo"),
                OptionList(
                    *(Text.assemble((key, "bold"), "  ", t(label)) for _, label, key, _, _ in MENU),
                    id="menu",
                ),
                id="menu-side",
            ),
            Static(id="about"),
        )
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_stats()
        self._update_about(0)
        self.query_one(OptionList).focus()

    def on_screen_resume(self) -> None:
        self._refresh_stats()
        self._update_about(self.query_one(OptionList).highlighted or 0)

    def _refresh_stats(self) -> None:
        app = cast(NumbraApp, self.app)
        stats = Stats(app.database_path)
        history = stats.history(1)
        if not history:
            self._stats_block = Text(t("No trainings yet. Press t to start one."), style="dim")
            return

        today = app.today()
        current, longest = stats.streak(today)
        last = history[0]
        days_ago = (today - date.fromtimestamp(last.started_at)).days
        when = (
            t("today")
            if days_ago == 0
            else t("yesterday")
            if days_ago == 1
            else tn(days_ago, "{n} day ago", "{n} days ago").format(n=days_ago)
        )
        last_value = Text.assemble(
            grade_text(last.score_percent), f" {percent(last.score_percent)}, {when}"
        )
        table = Table.grid(padding=(0, 3))
        table.add_row(
            t("Streak"), t("{days} (best {best})").format(days=days(current), best=longest)
        )
        table.add_row(t("Last"), last_value)
        weak = stats.weak_spots(limit=1)
        if weak:
            table.add_row(t("Practise"), t(area_name(weak[0].name)))
        self._stats_block = table

    def _update_about(self, index: int) -> None:
        _, label, _, description, _ = MENU[index]
        content: list[RenderableType] = [
            Text(t(label), style="bold"),
            Text(t(description)),
            Text(""),
        ]
        if self._stats_block is not None:
            content.append(self._stats_block)
        self.query_one("#about", Static).update(Group(*content))

    @on(OptionList.OptionHighlighted, "#menu")
    def _highlight(self, event: OptionList.OptionHighlighted) -> None:
        self._update_about(event.option_index)

    @on(OptionList.OptionSelected, "#menu")
    def _choose(self, event: OptionList.OptionSelected) -> None:
        self.action_open(MENU[event.option_index][0])

    def action_open(self, item_id: str) -> None:
        factory = next(factory for candidate, _, _, _, factory in MENU if candidate == item_id)
        if factory is None:
            self.action_quit_app()
            return
        self.app.push_screen(factory())

    def action_quit_app(self) -> None:
        self.app.exit()


class NumbraApp(App[None]):
    TITLE = "Numbra"
    # The palette only offers theme switching, which the ANSI themes make pointless.
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    HeaderIcon { display: none; }
    * {
        scrollbar-size-vertical: 1;
        scrollbar-color: $foreground 30%;
        scrollbar-color-hover: $foreground 45%;
        scrollbar-color-active: $foreground 60%;
        scrollbar-background: $foreground 5%;
    }
    OptionList > .option-list--option-highlighted {
        background: $foreground 15%; color: $foreground; text-style: bold;
    }
    DataTable > .datatable--header { background: transparent; color: $text-muted; text-style: bold; }
    DataTable > .datatable--cursor { background: $foreground 15%; color: $foreground; text-style: bold; }
    DataTable:focus > .datatable--cursor { background: $foreground 25%; }
    """

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
        self._previous_language = get_language()
        self.config_paths = config_paths or default_config_paths()
        self._settings_loader = settings_loader or (
            lambda: ConfigManager(self.config_paths).load_or_create()
        )
        try:
            language = self._settings_loader().language
        except ConfigError:
            language = "auto"
        set_language(resolve_language(language, os.environ))
        self.theme = terminal_theme()
        self.database_path = database_path or default_database_path()
        self.today = today
        self.clock = clock
        self.sleeper = sleeper
        translate_bindings(self)

    def on_unmount(self) -> None:
        set_language(self._previous_language)

    def load_settings(self) -> Settings:
        return self._settings_loader()

    def get_default_screen(self) -> Screen[None]:
        return MenuScreen()
