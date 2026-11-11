"""Funbox setup: the training form with one checkbox per funbox mode."""

from __future__ import annotations

from collections.abc import Sequence

from textual.widgets import SelectionList

from ..config import Settings
from ..core.funbox import FunboxMode
from ..core.models import Difficulty
from ..i18n import t
from .train import FUNBOX_TITLE, ChoiceList, TrainSetupScreen


class FunboxSetupScreen(TrainSetupScreen):
    """Experimental funbox wizard with the shared level, time and review steps."""

    TITLE = FUNBOX_TITLE
    HAS_START_STEP = False
    CHOICE_STEP_LABEL = "Modes"
    STEP_LABELS = ("Preset", "Level", "Modes", "Time", "Review")

    def _choice_list(self, settings: Settings) -> ChoiceList:
        return ChoiceList(
            *(
                (t(mode.value, "funbox"), mode.value, mode in settings.challenge.funbox_modes)
                for mode in FunboxMode
            ),
            compact=True,
            id="choices",
        )

    def _chosen(self) -> dict[str, object]:
        selected = set(self.query_one("#choices", SelectionList).selected)
        modes = tuple(mode for mode in FunboxMode if mode.value in selected)
        if not modes:
            raise ValueError("choose at least one funbox mode")
        return {"funbox": modes}

    def _practice_summary(self, tokens: Sequence[str], difficulty: Difficulty) -> str:
        del difficulty
        return ", ".join(t(token, "funbox") for token in tokens) or t("Choose at least one")
