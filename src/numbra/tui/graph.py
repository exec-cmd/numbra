"""Plot for graph funbox tasks: a character grid with axes, the curve clipped to it, and a cursor."""

from __future__ import annotations

from collections.abc import Sequence

from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Static

from ..core.funbox.graphs import GRID
from ..core.models import GraphSpec

# Two columns per unit, since a terminal cell is about twice as tall as it is wide. Columns
# between two integers are half steps, so a steep line does not break into dots.
COLUMNS_PER_UNIT = 2
_CURSOR_STYLE = "bold reverse"


def plot(coefficients: Sequence[int], cursor: tuple[int, int] | None = None) -> Text:
    """Draw y = sum(c * x**i) on the -GRID..GRID square; parts outside the square are dropped."""
    width = 2 * COLUMNS_PER_UNIT * GRID + 1
    height = 2 * GRID + 1
    cells = [[(" ", "")] * width for _ in range(height)]
    origin_row, origin_col = GRID, COLUMNS_PER_UNIT * GRID
    for col in range(width):
        cells[origin_row][col] = ("-", "dim")
    for row in range(height):
        cells[row][origin_col] = ("|", "dim")
    # Ticks: every unit on the x axis, every five on the y axis; labels at ±5 and ±10.
    for unit in range(-GRID, GRID + 1):
        cells[origin_row][origin_col + COLUMNS_PER_UNIT * unit] = ("+", "dim")
        if unit % 5 == 0:
            cells[GRID - unit][origin_col] = ("+", "dim")
        if unit % 5 == 0 and unit != 0:
            label = str(unit)
            start = min(
                max(origin_col + COLUMNS_PER_UNIT * unit - len(label) // 2, 0), width - len(label)
            )
            for offset, char in enumerate(label):
                cells[origin_row + 1][start + offset] = (char, "dim")
                cells[GRID - unit][origin_col + 2 + offset] = (char, "dim")
    previous: int | None = None
    for col in range(width):
        x = (col - origin_col) / COLUMNS_PER_UNIT
        y = sum(coefficient * x**power for power, coefficient in enumerate(coefficients))
        if abs(y) > GRID:
            previous = None
            continue
        row = round(GRID - y)
        # Join with the previous column so a steep part is drawn as a line, not as dots.
        first, last = (row, row) if previous is None else sorted((row, previous))
        for filled in range(first, last + 1):
            cells[filled][col] = ("*", "bold")
        previous = row
    if cursor is not None:
        x, y = cursor
        cells[GRID - y][COLUMNS_PER_UNIT * (x + GRID)] = ("O", _CURSOR_STYLE)
    text = Text(no_wrap=True)
    for index, line in enumerate(cells):
        for char, style in line:
            text.append(char, style=style)
        if index < height - 1:
            text.append("\n")
    if cursor is not None:
        text.append(f"\nPoint: ({cursor[0]}, {cursor[1]})")
    return text


class GraphCanvas(Static):
    """Plot of one graph task. In a place task the arrow keys move a cursor and Enter sends it."""

    can_focus = True
    DEFAULT_CSS = "GraphCanvas { width: auto; height: auto; }"
    BINDINGS = [
        Binding("left", "move(-1, 0)", show=False),
        Binding("right", "move(1, 0)", show=False),
        Binding("up", "move(0, 1)", show=False),
        Binding("down", "move(0, -1)", show=False),
        Binding("enter", "place", "Place point"),
    ]

    class Placed(Message):
        """The cursor was sent with Enter; x and y are whole grid units."""

        def __init__(self, x: int, y: int) -> None:
            super().__init__()
            self.x = x
            self.y = y

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._spec: GraphSpec | None = None
        self._cursor: tuple[int, int] | None = None

    def show(self, spec: GraphSpec) -> None:
        self._spec = spec
        self._cursor = (0, 0) if spec.kind == "place" else None
        self._draw()

    def action_move(self, dx: int, dy: int) -> None:
        if self._cursor is None:
            return
        x, y = self._cursor
        self._cursor = (max(-GRID, min(GRID, x + dx)), max(-GRID, min(GRID, y + dy)))
        self._draw()

    def action_place(self) -> None:
        if self._cursor is not None:
            self.post_message(self.Placed(*self._cursor))

    def _draw(self) -> None:
        assert self._spec is not None
        self.update(plot(self._spec.coefficients, self._cursor))
