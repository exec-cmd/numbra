from __future__ import annotations

import random


def group_terms(text: str, rng: random.Random) -> str:
    """Add value-preserving parentheses around short top-level additive runs."""
    draws = rng.random(), rng.random()
    lhs, separator, rhs = text.partition(" = ")
    pair_count = lhs.count("(")
    if pair_count >= 2:
        return text

    terms: list[tuple[int, int]] = []
    operators: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(lhs):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0 and char in "+-" and index > 0 and lhs[index - 1] == " ":
            terms.append((start, index - 1))
            operators.append(char)
            start = index + 2
    terms.append((start, len(lhs)))
    if len(terms) < 4:
        return text

    candidates = [
        (begin, end)
        for begin in range(len(terms))
        if begin == 0 or operators[begin - 1] == "+"
        for end in (begin + 2, begin + 3)
        if end <= len(terms)
        and all("(" not in lhs[terms[i][0] : terms[i][1]] for i in range(begin, end))
    ]
    if not candidates:
        return text

    chosen = [candidates[int(draws[0] * len(candidates)) % len(candidates)]]
    if pair_count == 0 and len(candidates) > 1 and draws[1] < 0.5:
        second = next(
            (item for item in candidates if item[0] >= chosen[0][1] or item[1] <= chosen[0][0]),
            None,
        )
        if second is not None:
            chosen.append(second)

    insertions: list[tuple[int, str]] = []
    for begin, end in chosen:
        insertions.extend(((terms[end - 1][1], ")"), (terms[begin][0], "(")))
    for position, char in sorted(insertions, reverse=True):
        lhs = lhs[:position] + char + lhs[position:]
    return lhs + (separator + rhs if separator else "")
