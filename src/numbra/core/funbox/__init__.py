"""Experimental funbox exercises. Nothing here imports Typer or Rich."""

from ..models import format_answer
from .generator import FunboxGenerator
from .modes import FunboxMode, parse_funbox_modes

__all__ = [
    "FunboxGenerator",
    "FunboxMode",
    "format_answer",
    "parse_funbox_modes",
]
