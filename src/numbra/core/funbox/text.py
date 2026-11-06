from __future__ import annotations

from collections.abc import Sequence


def polynomial_text(coefficients: Sequence[int]) -> str:
    """Render ascending coefficients highest power first, e.g. [0, -2, 0, 1] -> x^3 - 2x."""
    terms = []
    for power in range(len(coefficients) - 1, -1, -1):
        value = coefficients[power]
        if value == 0:
            continue
        magnitude = abs(value)
        if power == 0:
            body = str(magnitude)
        else:
            variable = "x" if power == 1 else f"x^{power}"
            body = variable if magnitude == 1 else f"{magnitude}{variable}"
        terms.append(("-" if value < 0 else "+", body))
    if not terms:
        return "0"
    sign, body = terms[0]
    text = f"-{body}" if sign == "-" else body
    for sign, body in terms[1:]:
        text += f" {sign} {body}"
    return text
