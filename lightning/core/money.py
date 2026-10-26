"""Exact money and quantity handling.

Rules:
- Every amount, quantity, price and rate is a ``Decimal`` — never a float.
- In SQLite they are stored as integers scaled by 1,000,000 (columns end in ``_e6``),
  so SQL ``SUM()`` stays exact. ``to_e6`` / ``from_e6`` are the only conversions.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, Inexact, InvalidOperation, localcontext

from .errors import ValidationError

SCALE_PLACES = 6
SCALE = 10**SCALE_PLACES
ZERO = Decimal("0")
ONE = Decimal("1")
TOO_LARGE = Decimal("1000000000000")


_ARABIC_DIGITS = {**{0x0660 + i: str(i) for i in range(10)}, **{0x06F0 + i: str(i) for i in range(10)},
                  0x066B: ".", 0x066C: ","}


def ascii_digits(text: str) -> str:
    """Arabic-Indic digits (٠١٢, ۰۱۲) and the Arabic decimal and thousands marks as plain ASCII."""
    return text.translate(_ARABIC_DIGITS)


def to_decimal(value: object, field: str = "amount") -> Decimal:
    """Parse user or code input into a Decimal.

    Accepts ``Decimal``, ``int`` and strings such as ``"1,250.50"`` or ``" 450 "``.
    Floats are rejected on purpose: they cannot represent money exactly.
    """
    if isinstance(value, bool):
        raise ValidationError("Enter a number.", field)
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        cleaned = ascii_digits(value).strip().replace("−", "-").replace("–", "-")
        if cleaned == "":
            raise ValidationError("Enter an amount.", field)
        result = _sum(cleaned, value, field) if _is_sum(cleaned) else _number(cleaned, value, field)
    elif isinstance(value, float):
        raise ValidationError("Internal error: floats are not allowed for money.", field)
    else:
        raise ValidationError("Enter a number.", field)
    if not result.is_finite():
        raise ValidationError("Enter a finite number.", field)
    if abs(result) >= TOO_LARGE:
        raise ValidationError("That amount is too large.", field)
    return result


def _number(text: str, value: str, field: str) -> Decimal:
    """One plain number: 1250, 1,250.50, -40."""
    if re.fullmatch(r"[+-]?\d{1,3},\d{1,2}", text):
        raise ValidationError("Use a dot for decimals, for example 12.5.", field)
    if not re.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", text):
        raise ValidationError(f"'{value}' is not a valid number. Use commas only as thousands separators.", field)
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        raise ValidationError(f"'{value}' is not a valid number.", field) from None


# Sums in amount fields: 120+35*2 is 190. The order is the usual one, as in a spreadsheet or a
# phone calculator: brackets first, then powers (^), then * and /, then + and -, each left to right.
# So 3+5*8 is 43, (3+5)*8 is 64, 2+3^2 is 11, and a bracket right after a number or a bracket
# multiplies: 2(3+5) is 16. Anything unclear is refused with the reason, never guessed: a sign at
# the end, two signs in a row, two numbers with no sign between them, -2^2, 2^3^2 and 8/2(2+2)
# (each has two common readings), a power that is not a whole number, a division that does not
# come out even, %, or a date typed in the wrong field. Messages show the signs as typed.
SUM_MAX_LENGTH = 100
SUM_MAX_POWER = 40  # 2^40 is already over a trillion
_SUM_SIGNS = {"+": "+", "-": "-", "*": "*", "x": "*", "X": "*", "×": "*", "/": "/", "÷": "/", "^": "^"}
_SUM_MARKS = "+-*/×÷xX^()=²³%[]{}"  # a character the plain number rules refuse; the same list is in app.js
_SUM_TOKEN = re.compile(r"\s*(?:(?P<number>[\d.,]+)|(?P<sign>[-+*/×÷xX^])|(?P<open>\()|(?P<close>\))|(?P<other>\S))")


def _is_sum(text: str) -> bool:
    """True when the text is more than one signed number: a sign after the start, a bracket, = or ^."""
    body = text[1:] if text[0] in "+-" else text
    return any(ch in _SUM_MARKS for ch in body)


def _sum(text: str, value: str, field: str) -> Decimal:
    if len(text) > SUM_MAX_LENGTH:
        raise ValidationError(f"That sum is too long. Keep it under {SUM_MAX_LENGTH} characters.", field)
    body = text[1:] if text.startswith("=") else text      # =120+35, as in a spreadsheet
    body = (body[:-1] if body.endswith("=") else body).strip()  # 120+35=, as on a calculator
    if not body:
        raise ValidationError("Enter an amount.", field)
    if "=" in body:
        raise ValidationError(f"'{value}' has = in the middle. Keep only the sum, for example 120+35.", field)
    if not _is_sum(body):
        return _number(body, value, field)
    from .dates import parse_date  # imported here: dates imports this module
    try:
        parse_date(body)
    except ValidationError:
        pass
    else:
        raise ValidationError(f"'{value}' looks like a date. Put the date in the date field. "
                              "To divide, put spaces around the /, for example 12 / 3.", field)
    tokens = []
    for match in _SUM_TOKEN.finditer(body.replace("²", "^2").replace("³", "^3")):
        kind = match.lastgroup
        if kind == "other":
            other = match.group(kind)
            raise ValidationError("% can't be used in an amount. For 10% of 200, type 200*10/100." if other == "%" else
                                  "Use round brackets ( ) to group." if other in "[]{}" else
                                  f"'{other}' can't be used in an amount. Use numbers, + - * / ^ and brackets.", field)
        tokens.append((kind, match.group(kind)))
    try:
        result = _SumParser(tokens, value, field).run(exact=True)
    except Inexact:
        about = _SumParser(tokens, value, field).run(exact=False)
        raise ValidationError(f"'{value}' doesn't come out even. Type the amount you mean, "
                              f"for example {quantize(about)}.", field) from None
    return ZERO if result == 0 else result


class _SumParser:
    """Reads a sum's tokens: brackets, then ^, then * and /, then + and -; left to right within each."""

    def __init__(self, tokens: list[tuple[str, str]], value: str, field: str):
        self.tokens, self.value, self.field, self.at = tokens, value, field, 0

    def fail(self, message: str):
        raise ValidationError(message, self.field)

    def peek(self) -> tuple[str | None, str]:
        return self.tokens[self.at] if self.at < len(self.tokens) else (None, "")

    def sign(self) -> str | None:
        kind, text = self.peek()
        return _SUM_SIGNS[text] if kind == "sign" else None

    def run(self, exact: bool) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = SUM_MAX_LENGTH * SUM_MAX_POWER + 100  # any typed sum fits; only uneven division is inexact
            ctx.traps[Inexact] = exact
            result = self.expression()
        if self.peek()[0] == "close":
            self.fail("A closing bracket ) has no opening one. Remove it, or add the (.")
        return result

    def checked(self, value: Decimal) -> Decimal:
        if abs(value) >= TOO_LARGE:
            self.fail("That amount is too large.")
        return value

    def expression(self) -> Decimal:
        negative = self.sign() == "-"
        if self.sign() in ("+", "-"):  # a sign only at the start, or just after (
            self.at += 1
        total = self.term()
        total = -total if negative else total
        while (op := self.sign()) in ("+", "-"):
            self.at += 1
            right = self.term()
            total = self.checked(total + right if op == "+" else total - right)
        return total

    def term(self) -> Decimal:
        product, divided = self.power(), False
        while True:
            op = self.sign()
            if op in ("*", "/"):
                self.at += 1
            elif self.peek()[0] == "open":  # 2(3+5) is 2*(3+5)
                if divided:
                    self.fail(f"'{self.value}' is unclear: 8/2(2+2) can mean 16 or 1. "
                              "Add the sign: 8/2*(2+2) for 16, or 8/(2*(2+2)) for 1.")
                op = "*"
            else:
                return product
            right = self.power()
            if op == "*":
                product = self.checked(product * right)
            elif right == 0:
                self.fail("You can't divide by zero.")
            else:
                product, divided = self.checked(product / right), True

    def power(self) -> Decimal:
        start = self.at
        base = self.factor()
        if self.sign() != "^":
            return base
        if start and self.tokens[start - 1] == ("sign", "-") and (start == 1 or self.tokens[start - 2][0] == "open"):
            self.fail(f"'{self.value}' is unclear: -2^2 can mean 4 or -4. "
                      "Add brackets: (-2)^2 for 4, or -(2^2) for -4.")
        self.at += 1
        exponent = self.factor()
        if self.sign() == "^":
            self.fail(f"'{self.value}' is unclear: 2^3^2 can mean 64 or 512. "
                      "Add brackets: (2^3)^2 or 2^(3^2).")
        if exponent != exponent.to_integral_value():
            self.fail("A power must be a whole number, like 2^3.")
        if abs(exponent) > SUM_MAX_POWER:
            self.fail(f"That power is too large. Use {SUM_MAX_POWER} or less.")
        if base == 0 and exponent <= 0:
            self.fail("0^0 has no single answer." if exponent == 0 else "You can't divide by zero.")
        return self.checked(base ** int(exponent))

    def factor(self) -> Decimal:
        before_kind, before = self.tokens[self.at - 1] if self.at else (None, "")
        kind, text = self.peek()
        self.at += 1
        if kind == "number":
            whole = text.split(".")[0].replace(",", "")
            if len(whole) > 1 and whole[0] == "0":
                self.fail(f"'{text}' starts with 0. Remove the 0, or check this is an amount.")
            value = self.checked(_number(text, text, self.field))
        elif kind == "open":
            value = self.expression()
            if self.peek()[0] != "close":
                self.fail("A bracket ( is not closed. Add the ), or remove the (.")
            self.at += 1
        elif before_kind == "sign":
            if kind == "sign":
                hint = "; for a power, use ^" if _SUM_SIGNS[before] == _SUM_SIGNS[text] == "*" else (
                    f", or put the negative number in brackets: 2{before}(-2)" if text == "-" else "")
                self.fail(f"Two signs in a row: {before} then {text}. Remove one{hint}.")
            self.fail(f"'{self.value}' has nothing after the {before}. Finish the sum, or remove the {before}.")
        elif before_kind == "open":
            self.fail("Empty brackets. Put a number inside, or remove them." if kind == "close" else
                      "A bracket ( is not closed. Add the ), or remove the (." if kind is None else
                      f"A bracket can't start with {text}. Put a number first.")
        elif kind == "sign":
            self.fail(f"'{self.value}' starts with {text}. Put a number before it, or remove it.")
        else:
            self.fail("A closing bracket ) has no opening one. Remove it, or add the (.")
        if self.peek()[0] == "number":
            self.fail(f"Put a sign between {self.tokens[self.at - 1][1]} and {self.peek()[1]}: + - * / or ^.")
        return value


def decimal_places(value: Decimal) -> int:
    exponent = value.normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def check_places(value: Decimal, places: int, field: str = "amount") -> Decimal:
    """Reject values with more decimal places than allowed (e.g. 12.345 EGP)."""
    if decimal_places(value) > places:
        if places == 0:
            raise ValidationError("Use whole numbers only.", field)
        raise ValidationError(f"Use at most {places} decimal places.", field)
    return value


def quantize(value: Decimal, places: int = 2) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def to_e6(value: Decimal) -> int:
    """Decimal -> integer micro-units for storage. Refuses to lose precision."""
    if not value.is_finite():
        raise ValidationError("Enter a finite number.")
    if decimal_places(value) > SCALE_PLACES:
        raise ValidationError(f"At most {SCALE_PLACES} decimal places can be stored.")
    if value < Decimal(-2**63) / SCALE or value > Decimal(2**63 - 1) / SCALE:
        raise ValidationError("That amount is too large.", "amount")
    return int(value.scaleb(SCALE_PLACES))


def from_e6(value: int | None) -> Decimal:
    """Integer micro-units from storage -> Decimal."""
    if value is None:
        return ZERO
    # normalize() drops trailing zeros; adding 0.00 keeps at least two decimals (450 -> 450.00)
    return Decimal(int(value)).scaleb(-SCALE_PLACES).normalize() + Decimal("0.00")


def fmt(value: Decimal | None, places: int = 2, signed: bool = False) -> str:
    """Human format: ``1,234.50`` / ``-1,234.50`` (``+`` prefix when signed)."""
    if value is None:
        return "—"
    q = quantize(value, places)
    text = f"{abs(q):,.{places}f}"
    if q < 0:
        return f"-{text}"
    if signed and q > 0:
        return f"+{text}"
    return text
