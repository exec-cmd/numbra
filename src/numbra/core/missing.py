from __future__ import annotations

import random
from fractions import Fraction

from numbra.core.expressions import Expr


def missing_number(tree: Expr, rng: random.Random) -> tuple[str, int, tuple[str, ...]] | None:
    draw = rng.random()
    candidates: list[tuple[tuple[int, ...], int, tuple[str, ...]]] = []

    def visit(node: Expr, path: tuple[int, ...]) -> None:
        if node.kind == "number":
            if not path:
                return
            target = node
            steps: list[str] = []
            value = Fraction(tree.evaluate())
            current = tree
            for side in path:
                parent = current
                left, right = parent.args
                sibling = (right if side == 0 else left).evaluate()
                op = parent.kind
                if op == "+":
                    value -= sibling
                elif op == "-":
                    value = value + sibling if side == 0 else sibling - value
                elif op == "*":
                    if sibling == 0:
                        return
                    value /= sibling
                elif op == "/":
                    if side == 0:
                        value *= sibling
                    else:
                        if value == 0:
                            return
                        value = sibling / value
                else:
                    return
                steps.append(f"{parent.render()} -> {value}")
                current = parent.args[side]
            if value.denominator == 1 and value.numerator == target.value:
                candidates.append((path, value.numerator, tuple(steps)))
            return
        if node.kind not in {"+", "-", "*", "/"}:
            return
        for side, child in enumerate(node.args):
            visit(child, path + (side,))

    visit(tree, ())
    if not candidates:
        return None
    path, answer, steps = candidates[min(int(draw * len(candidates)), len(candidates) - 1)]
    marker = 10**100

    def replace_leaf(node: Expr, remaining: tuple[int, ...]) -> Expr:
        if not remaining:
            return Expr.number(marker)
        side, *tail = remaining
        args = list(node.args)
        args[side] = replace_leaf(args[side], tuple(tail))
        return Expr(node.kind, tuple(args), node.value)

    lhs = replace_leaf(tree, path).render().replace(str(marker), "?", 1)
    return f"{lhs} = {tree.evaluate()}", answer, steps
