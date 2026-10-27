from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache


@dataclass(frozen=True, slots=True)
class Expr:
    kind: str
    args: tuple[Expr, ...] = ()
    value: int = 0
    _hash: int = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_hash", hash((self.kind, self.args, self.value)))

    def __hash__(self) -> int:
        return self._hash

    def __reduce__(self) -> tuple[type[Expr], tuple[str, tuple[Expr, ...], int]]:
        # String hashes are process-local; reconstruct rather than serialize the cached hash.
        return type(self), (self.kind, self.args, self.value)

    @classmethod
    def number(cls, n: int) -> Expr:
        if isinstance(n, bool) or not isinstance(n, int):
            raise ValueError("number nodes require an integer")
        return cls("number", value=n)

    @classmethod
    def binary(cls, op: str, left: Expr, right: Expr) -> Expr:
        if op not in {"+", "-", "*", "/", "^"}:
            raise ValueError(f"unsupported binary operation: {op}")
        return cls(op, (left, right))

    @classmethod
    def function(cls, name: str, *args: Expr) -> Expr:
        if name not in {"sqrt", "sin", "cos", "tan", "log"}:
            raise ValueError(f"unsupported function: {name}")
        expected = 2 if name == "log" else 1
        if len(args) != expected:
            raise ValueError(f"{name} expects {expected} argument(s)")
        return cls(name, tuple(args))

    def evaluate(self) -> Fraction:
        return _evaluate(self)

    def render(self) -> str:
        return _render(self)


def _trig_value(name: str, degrees: int) -> Fraction:
    angle = degrees % 360
    table: dict[int, int | Fraction]
    if name == "sin":
        table = {
            0: 0,
            30: Fraction(1, 2),
            90: 1,
            150: Fraction(1, 2),
            180: 0,
            210: Fraction(-1, 2),
            270: -1,
            330: Fraction(-1, 2),
        }
    elif name == "cos":
        table = {
            0: 1,
            60: Fraction(1, 2),
            90: 0,
            120: Fraction(-1, 2),
            180: -1,
            240: Fraction(-1, 2),
            270: 0,
            300: Fraction(1, 2),
        }
    else:
        table = {0: 0, 180: 0, 45: 1, 135: -1, 225: 1, 315: -1}
    try:
        return Fraction(table[angle])
    except KeyError as exc:
        raise ValueError(f"{name}({degrees} degrees) is irrational or undefined") from exc


@lru_cache(maxsize=16384)
def _evaluate(expr: Expr) -> Fraction:
    if expr.kind == "number":
        if expr.args:
            raise ValueError("number node cannot have arguments")
        return Fraction(expr.value)
    if expr.kind in {"+", "-", "*", "/", "^"}:
        if len(expr.args) != 2:
            raise ValueError("binary operation requires two arguments")
        left, right = (arg.evaluate() for arg in expr.args)
        if expr.kind == "+":
            return left + right
        if expr.kind == "-":
            return left - right
        if expr.kind == "*":
            return left * right
        if expr.kind == "/":
            if right == 0:
                raise ValueError("division by zero is undefined")
            return left / right
        if right.denominator != 1 or right.numerator not in {2, 3}:
            raise ValueError("powers must use an exponent of 2 or 3")
        return left**right.numerator
    values = tuple(arg.evaluate() for arg in expr.args)
    if expr.kind == "sqrt":
        if len(values) != 1 or values[0] < 0:
            raise ValueError("sqrt requires a non-negative value")
        number = values[0]
        numerator, denominator = math.isqrt(number.numerator), math.isqrt(number.denominator)
        if (
            numerator * numerator != number.numerator
            or denominator * denominator != number.denominator
        ):
            raise ValueError("sqrt result must be rational")
        return Fraction(numerator, denominator)
    if expr.kind in {"sin", "cos", "tan"}:
        if len(values) != 1 or values[0].denominator != 1:
            raise ValueError("trigonometric angle must be an integer number of degrees")
        return _trig_value(expr.kind, values[0].numerator)
    if expr.kind == "log":
        if len(values) != 2:
            raise ValueError("log requires base and argument")
        base, argument = values
        if (
            base.denominator != 1
            or base.numerator not in {2, 3, 5, 10}
            or argument <= 0
            or base == 1
        ):
            raise ValueError("log requires base 2, 3, 5, or 10 and a positive argument")
        for exponent in range(-3, 5):
            candidate = (
                Fraction(base.numerator**exponent)
                if exponent >= 0
                else Fraction(1, base.numerator**-exponent)
            )
            if candidate == argument:
                return Fraction(exponent)
        raise ValueError("logarithm result must be an integer from -3 through 4")
    raise ValueError(f"unsupported expression kind: {expr.kind}")


def _precedence(expr: Expr) -> int:
    return {"+": 1, "-": 1, "*": 2, "/": 2, "^": 3}.get(expr.kind, 4)


def _render(expr: Expr, parent: int = 0) -> str:
    if expr.kind == "number":
        rendered_number = str(expr.value)
        return f"({rendered_number})" if expr.value < 0 and parent > 3 else rendered_number
    if expr.kind in {"+", "-", "*", "/", "^"}:
        left, right = expr.args
        symbol = "^" if expr.kind == "^" else expr.kind
        left_parent = _precedence(expr)
        if expr.kind == "^":
            left_parent += 1
        left_text = _render(left, left_parent)
        right_parent = _precedence(expr) + (1 if expr.kind in {"-", "/"} else 0)
        if expr.kind in {"+", "*"} and right.kind in ({"-"} if expr.kind == "+" else {"/"}):
            right_parent += 1
        right_text = _render(right, right_parent)
        rendered = f"{left_text} {symbol} {right_text}"
        return f"({rendered})" if _precedence(expr) < parent else rendered
    if expr.kind in {"sin", "cos", "tan"}:
        return f"{expr.kind}({_render(expr.args[0])}°)"
    if expr.kind == "log":
        return f"log({_render(expr.args[0])}, {_render(expr.args[1])})"
    return f"{expr.kind}({', '.join(_render(arg) for arg in expr.args)})"


_AST_BINARY: dict[type[ast.operator], str] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.Pow: "^",
}
_FUNCTIONS = {"sqrt", "sin", "cos", "tan", "log"}


def parse_expression(text: str) -> Expr:
    """Parse a small arithmetic expression without executing Python code."""
    normalized = re.sub(r"(?<=\d)°", "", text.strip()).replace("^", "**")
    try:
        parsed = ast.parse(normalized, mode="eval")
        return _from_ast(parsed.body)
    except (SyntaxError, ValueError, TypeError) as exc:
        raise ValueError("expression contains unsupported or invalid syntax") from exc


def _from_ast(node: ast.expr) -> Expr:
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return Expr.number(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        operand = _from_ast(node.operand)
        if isinstance(node.op, ast.USub) and operand.kind == "number":
            return Expr.number(-operand.value)
        return (
            Expr.binary("-", Expr.number(0), operand) if isinstance(node.op, ast.USub) else operand
        )
    if isinstance(node, ast.BinOp) and type(node.op) in _AST_BINARY:
        op = _AST_BINARY[type(node.op)]
        return Expr.binary(op, _from_ast(node.left), _from_ast(node.right))
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCTIONS
    ):
        if node.keywords:
            raise ValueError("keyword arguments are unsupported")
        return Expr.function(node.func.id, *(_from_ast(arg) for arg in node.args))
    raise ValueError("expression contains an unsupported value")


@lru_cache(maxsize=16384)
def expression_operations(expr: Expr) -> tuple[str, ...]:
    found: list[str] = []

    def visit(node: Expr) -> None:
        for child in node.args:
            visit(child)
        if node.kind in {"+", "-", "*", "/", "^"}:
            found.append(node.kind)

    visit(expr)
    return tuple(found)


type Key = tuple[object, ...]


@lru_cache(maxsize=16384)
def canonical_key(expr: Expr) -> Key:
    if expr.kind == "number":
        return ("number", expr.value)
    if expr.kind in {"+", "*"}:
        parts: list[Key] = []

        def flatten(node: Expr) -> None:
            if node.kind == expr.kind:
                for child in node.args:
                    flatten(child)
            else:
                parts.append(canonical_key(node))

        flatten(expr)
        return (expr.kind, *sorted(parts, key=repr))
    return (expr.kind, *(canonical_key(arg) for arg in expr.args))


def _additive_terms(expr: Expr) -> dict[Key, int]:
    terms: dict[Key, int] = {}

    def visit(node: Expr, sign: int = 1) -> None:
        if node.kind == "+":
            visit(node.args[0], sign)
            visit(node.args[1], sign)
        elif node.kind == "-":
            visit(node.args[0], sign)
            visit(node.args[1], -sign)
        else:
            key = canonical_key(node)
            terms[key] = terms.get(key, 0) + sign

    visit(expr)
    return {key: coeff for key, coeff in terms.items() if coeff}


def _additive_leaf_count(expr: Expr) -> int:
    if expr.kind == "+":
        return sum(_additive_leaf_count(child) for child in expr.args)
    if expr.kind == "-":
        return sum(_additive_leaf_count(child) for child in expr.args)
    return 1


def _multiplicative_factors(expr: Expr) -> dict[Key, int]:
    factors: dict[Key, int] = {}

    def visit(node: Expr, power: int = 1) -> None:
        if node.kind == "*":
            visit(node.args[0], power)
            visit(node.args[1], power)
        elif node.kind == "/":
            visit(node.args[0], power)
            visit(node.args[1], -power)
        elif node.kind == "^" and node.args[1].kind == "number" and node.args[1].value in {2, 3}:
            visit(node.args[0], power * node.args[1].value)
        else:
            key = canonical_key(node)
            factors[key] = factors.get(key, 0) + power

    visit(expr)
    return {key: value for key, value in factors.items() if value}


def _multiplicative_leaf_count(expr: Expr) -> int:
    if expr.kind in {"*", "/"}:
        return sum(_multiplicative_leaf_count(child) for child in expr.args)
    if expr.kind == "^" and expr.args[1].kind == "number" and expr.args[1].value in {2, 3}:
        return expr.args[1].value * _multiplicative_leaf_count(expr.args[0])
    return 1


@lru_cache(maxsize=16384)
def meaningful(expr: Expr) -> bool:
    if expr.kind == "number":
        return True
    if not all(meaningful(child) for child in expr.args):
        return False
    if expr.kind == "*":
        if any(child.evaluate() in {0, 1} for child in expr.args):
            return False
    if expr.kind == "^" and abs(expr.args[0].evaluate()) <= 1:
        return False
    if expr.kind == "/":
        left, right = expr.args
        left_value, right_value = left.evaluate(), right.evaluate()
        if right_value in {0, 1} or left_value == right_value:
            return False
    if expr.kind in {"+", "-"} and any(
        child.kind != "number" and child.evaluate() == 0 for child in expr.args
    ):
        return False
    if expr.kind == "+" and any(child.evaluate() == 0 for child in expr.args):
        return False
    if expr.kind == "-" and expr.args[1].evaluate() == 0:
        return False
    if expr.kind == "-" and canonical_key(expr.args[0]) == canonical_key(expr.args[1]):
        return False
    if expr.kind in {"+", "-"}:
        terms = _additive_terms(expr)
        if sum(abs(coeff) for coeff in terms.values()) < _additive_leaf_count(expr):
            return False
    if expr.kind in {"*", "/"}:
        factors = _multiplicative_factors(expr)
        if sum(abs(power) for power in factors.values()) < _multiplicative_leaf_count(expr):
            return False
    try:
        if expr.evaluate() == 0 and expr.kind not in {"number", "sin", "cos", "tan", "log"}:
            return False
    except ValueError:
        return False
    return True


@lru_cache(maxsize=16384)
def valid_bounds(expr: Expr, max_result: int) -> bool:
    if max_result < 0:
        return False

    return _bounded_value(expr, max_result) is not None


@lru_cache(maxsize=16384)
def _bounded_value(expr: Expr, max_result: int) -> Fraction | None:
    if any(_bounded_value(child, max_result) is None for child in expr.args):
        return None
    try:
        value = expr.evaluate()
    except (ValueError, OverflowError, ZeroDivisionError):
        return None
    if abs(value) > max_result or value.denominator > 12:
        return None
    return value


def _carry_actions(left: int, right: int, subtract: bool = False) -> int:
    a, b = str(abs(left))[::-1], str(abs(right))[::-1]
    carry = borrow = actions = 0
    for index in range(max(len(a), len(b))):
        da = int(a[index]) if index < len(a) else 0
        db = (int(b[index]) if index < len(b) else 0) + carry
        if subtract:
            if da < db:
                actions += 1
                borrow = 1
            else:
                borrow = 0
            carry = borrow
        else:
            if da + db >= 10:
                actions += 1
                carry = 1
            else:
                carry = 0
    return min(actions, 1)


@lru_cache(maxsize=16384)
def work_units(expr: Expr) -> int:
    """Estimate short mental-solution effort from visible arithmetic structure."""
    if expr.kind == "number":
        return 0
    child_cost = sum(work_units(child) for child in expr.args)
    if expr.kind in {"+", "-"}:
        terms = _additive_terms(expr)
        if sum(abs(coeff) for coeff in terms.values()) < _additive_leaf_count(expr):
            return min(work_units(expr.args[0]), work_units(expr.args[1]))
    if expr.kind in {"*", "/"}:
        factors = _multiplicative_factors(expr)
        if sum(abs(power) for power in factors.values()) < _multiplicative_leaf_count(expr):
            return min(work_units(expr.args[0]), work_units(expr.args[1]))
    if expr.kind in {"*", "/"}:
        left_expr, right_expr = expr.args
        left_power = _power_parts(left_expr)
        right_power = _power_parts(right_expr)
        if left_power is not None and right_power is not None and left_power[1] == right_power[1]:
            base_op = "*" if expr.kind == "*" else "/"
            reduced_base = Expr.binary(base_op, left_power[0], right_power[0])
            reduced = Expr.binary("^", reduced_base, Expr.number(left_power[1]))
            if expr.kind == "/":
                return work_units(reduced)
            return min(child_cost + 2, work_units(reduced))
    try:
        values = tuple(arg.evaluate() for arg in expr.args)
        if expr.kind in {"+", "-"}:
            left, right = values
            if left.denominator == right.denominator == 1:
                a, b = left.numerator, right.numerator
                if expr.kind == "+" and max(abs(a), abs(b)) <= 10:
                    base = 1 + _carry_actions(a, b)
                elif expr.kind == "+" and (a % 10 == 0 or b % 10 == 0 or (a % 10 + b % 10 < 10)):
                    base = 1 if a % 10 == 0 or b % 10 == 0 else 2
                elif expr.kind == "+" and (a + b) % 10 == 0:
                    base = 2
                elif expr.kind == "-" and (b % 10 == 0 or a % 10 >= b % 10):
                    base = 1 if b % 10 == 0 else 2
                else:
                    base = 2
                    base += _carry_actions(a, b, expr.kind == "-")
            else:
                base = 2
            return child_cost + base
        if expr.kind == "*":
            left, right = values
            if left.denominator == right.denominator == 1:
                a, b = abs(left.numerator), abs(right.numerator)
                if a in {0, 1} or b in {0, 1}:
                    base = 1
                elif a <= 10 and b <= 10:
                    base = 1
                elif a % 10 == 0 or b % 10 == 0 or a * b % 100 == 0:
                    base = 1
                elif a < 10 or b < 10:
                    base = 2
                elif abs(a - b) == 2 and (a + b) % 4 == 0:
                    base = 2
                else:
                    base = 3
            else:
                base = 3
            return child_cost + base
        if expr.kind == "/":
            left, right = values
            divisor = abs(right.numerator)
            decimal_shift = (
                right.denominator == 1
                and divisor > 0
                and divisor % 10 == 0
                and set(str(divisor)[1:]) <= {"0"}
            )
            table_division = (
                left.denominator == right.denominator == 1
                and 2 <= divisor <= 10
                and left.numerator % right.numerator == 0
                and abs(left.numerator // right.numerator) <= 10
            )
            base = (
                1
                if right.denominator == 1
                and (divisor in {2, 5, 10} or decimal_shift or table_division)
                else 3
            )
            return child_cost + base
        if expr.kind == "^":
            base = (
                1
                if abs(values[0]).denominator == 1 and abs(values[0].numerator) in {0, 1, 10}
                else 2
            )
            return child_cost + base
        if expr.kind == "sqrt":
            return child_cost + 1
        if expr.kind == "log":
            return child_cost + 1
        if expr.kind in {"sin", "cos", "tan"}:
            return child_cost + 1
    except (ValueError, ZeroDivisionError):
        return child_cost + 3
    return child_cost + 3


def _power_parts(expr: Expr) -> tuple[Expr, int] | None:
    if expr.kind == "^" and expr.args[1].kind == "number" and expr.args[1].value in {2, 3}:
        return expr.args[0], expr.args[1].value
    return None


@lru_cache(maxsize=16384)
def solution_steps(expr: Expr) -> tuple[str, ...]:
    """Return a compact exact calculation trail, including recognizable shortcuts."""
    steps: list[str] = []

    def visit(node: Expr) -> Fraction:
        child_values = tuple(visit(child) for child in node.args)
        value = node.evaluate()
        if node.kind == "number":
            return value

        rendered = node.render()
        if node.kind == "*" and all(item.denominator == 1 for item in child_values):
            left, right = (item.numerator for item in child_values)
            if abs(left - right) == 2 and (left + right) % 4 == 0:
                center, delta = (left + right) // 2, abs(left - right) // 2
                steps.append(
                    f"{rendered}: {center}^2 - {delta}^2 = "
                    f"{center * center} - {delta * delta} = {value}"
                )
                return value
            if left != 0 and right != 0:
                left_zeros, right_zeros = _trailing_zeroes(left), _trailing_zeroes(right)
                if left_zeros or right_zeros:
                    reduced_left = left // (10**left_zeros)
                    reduced_right = right // (10**right_zeros)
                    zeros = left_zeros + right_zeros
                    product = reduced_left * reduced_right
                    steps.append(
                        f"{rendered}: {reduced_left} * {reduced_right} = {product}; "
                        f"restore {zeros} zero(s) = {value}"
                    )
                    return value
        if node.kind == "+" and all(item.denominator == 1 for item in child_values):
            left, right = (item.numerator for item in child_values)
            center = (left + right) // 2
            if left + right == center * 2 and center % 10 == 0 and abs(left - right) <= 18:
                steps.append(f"{rendered}: {center} + {center} = {value}")
                return value
        if node.kind == "sqrt":
            steps.append(f"{rendered} = {value}")
        elif node.kind == "log":
            base, argument = child_values
            exponent = value.numerator
            steps.append(f"{base}^{exponent} = {argument}, so {rendered} = {value}")
        elif node.kind in {"sin", "cos", "tan"}:
            steps.append(f"{rendered} = {value} (exact degree-table value)")
        else:
            steps.append(f"{rendered} = {value}")
        return value

    visit(expr)
    return tuple(steps)


def _trailing_zeroes(number: int) -> int:
    if number == 0:
        return 0
    count = 0
    while number % 10 == 0:
        number //= 10
        count += 1
    return count
