from __future__ import annotations

from enum import StrEnum


class FunboxMode(StrEnum):
    FRACTIONS = "fractions"
    SUBSTITUTION = "substitution"
    EQUATIONS = "equations"
    LOGIC = "logic"
    GRAPHS = "graphs"
    DERIVATIVES = "derivatives"


def parse_funbox_modes(text: str) -> tuple[FunboxMode, ...]:
    """Parse a comma list such as "logic,equations"; the result keeps the FunboxMode order."""
    names = [item.strip().lower() for item in text.split(",") if item.strip()]
    if not names:
        raise ValueError("funbox mode list must not be empty")
    requested = set()
    for name in names:
        try:
            requested.add(FunboxMode(name))
        except ValueError as exc:
            known = ", ".join(mode.value for mode in FunboxMode)
            raise ValueError(f"unsupported funbox mode '{name}'; use {known}") from exc
    return tuple(mode for mode in FunboxMode if mode in requested)
