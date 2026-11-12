from __future__ import annotations

import random
from fractions import Fraction

from numbra.core.expressions import Expr


def missing_number(tree: Expr, rng: random.Random) -> tuple[str, int, tuple[str, ...]] | None:
    draw = rng.random()
    candidates: list[tuple[Expr, int, tuple[str, ...]]] = []

    def visit(node: Expr, path: tuple[tuple[Expr, int], ...]) -> None:
        if node.kind == "number":
            if not path:
                return
            target = node
            steps: list[str] = []
            value = Fraction(tree.evaluate())
            for parent, side in path:
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
            if value.denominator == 1 and value.numerator == target.value:
                candidates.append((target, value.numerator, tuple(steps)))
            return
        if node.kind not in {"+", "-", "*", "/"}:
            return
        for side, child in enumerate(node.args):
            visit(child, path + ((node, side),))

    visit(tree, ())
    if not candidates:
        return None
    leaf, answer, steps = candidates[min(int(draw * len(candidates)), len(candidates) - 1)]
    marker = 10**100

    def replace_leaf(node: Expr) -> Expr:
        if node is leaf:
            return Expr.number(marker)
        return Expr(node.kind, tuple(replace_leaf(child) for child in node.args), node.value)

    lhs = replace_leaf(tree).render().replace(str(marker), "?", 1)
    return f"{lhs} = {tree.evaluate()}", answer, steps
