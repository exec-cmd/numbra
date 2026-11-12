from __future__ import annotations

import random

from .expressions import Expr


def _flatten(expr: Expr, kind: str) -> list[Expr]:
    if expr.kind != kind:
        return [expr]
    return [child for arg in expr.args for child in _flatten(arg, kind)]


def _left_associative(kind: str, children: list[Expr]) -> Expr:
    tree = children[0]
    for child in children[1:]:
        tree = Expr.binary(kind, tree, child)
    return tree


def permute_operands(tree: Expr, rng: random.Random) -> Expr:
    if tree.kind not in {"+", "*"}:
        if tree.kind in {"-", "/", "^"}:
            left, right = tree.args
            return Expr.binary(tree.kind, permute_operands(left, rng), permute_operands(right, rng))
        if tree.args:
            return Expr(tree.kind, tuple(permute_operands(arg, rng) for arg in tree.args))
        return tree

    original_brackets = tree.render().count("(")
    children = [permute_operands(child, rng) for child in _flatten(tree, tree.kind)]
    shuffled = children.copy()
    rng.shuffle(shuffled)
    permuted = _left_associative(tree.kind, shuffled)
    return (
        permuted
        if permuted.render().count("(") <= original_brackets
        else _left_associative(tree.kind, children)
    )
