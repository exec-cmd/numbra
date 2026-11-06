"""Funbox setup: the training form with one checkbox per funbox mode."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.widgets import Checkbox, Label

from ..config import Settings
from ..core.funbox import FunboxMode
from .train import FUNBOX_TITLE, TrainSetupScreen


class FunboxSetupScreen(TrainSetupScreen):
    """Experimental funbox run; the form, timing and summary are the training ones."""

    TITLE = FUNBOX_TITLE

    def _choices(self, settings: Settings) -> ComposeResult:
        yield Label("Funbox modes (at least one)")
        for mode in FunboxMode:
            box = Checkbox(mode.value, value=mode in settings.challenge.funbox_modes)
            self._boxes[mode.value] = box
            yield box

    def _chosen(self) -> dict[str, Any]:
        modes = tuple(mode for mode in FunboxMode if self._boxes[mode.value].value)
        if not modes:
            raise ValueError("choose at least one funbox mode")
        return {"funbox": modes}
