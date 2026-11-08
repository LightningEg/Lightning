"""Sums in amount fields: 120+35*2 is saved as 190, and anything unclear is refused, never guessed.

The order is brackets, then ^, then * and /, then + and -, left to right within each, as in a
spreadsheet or a phone calculator; 2(3+5) is 2*(3+5). The rules live in lightning/core/money.py.
"""

import re
from decimal import Decimal as D
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lightning.core.errors import ValidationError
from lightning.core.money import _SUM_MARKS, to_decimal
from lightning.ui.web import create_app


@pytest.mark.parametrize("typed, saved", [
    # * and / before + and -: 3+5*8 is 43, not 64
    ("3+5*8", "43"), ("(3+5)*8", "64"), ("120+35*2", "190"), ("2*150+3*40", "420"),
    ("100-20+5", "85"), ("100-20-30", "50"), ("100/4/5", "5"), ("2*3/4", "1.5"), ("900/3", "300"),
    # powers before × and ÷, and before a minus between two numbers
    ("2^3", "8"), ("2+3^2", "11"), ("2*3^2", "18"), ("(2+3)^2", "25"), ("3-2^2", "-1"),
    ("2^(1+2)", "8"), ("2^(-2)", "0.25"), ("(-2)^2", "4"), ("-(2^2)", "-4"), ("+2^2", "4"),
    ("5²+1", "26"), ("2³", "8"), ("0^2", "0"),
    # a bracket right after a number or a bracket multiplies
    ("2(3+5)", "16"), ("(1+2)(3+4)", "21"), ("3(2)(2)", "12"), ("2 (3)", "6"), ("-2(3)", "-6"), ("2(3)^2", "18"),
    ("2^3(4)", "32"), ("2(3)/4", "1.5"), ("8/2*(2+2)", "16"), ("8/(2*(2+2))", "1"), ("1,000(2)", "2000"),
    # brackets, signs at the start, other ways to write the signs
    ("((5))", "5"), ("(5)", "5"), ("-5+10", "5"), ("-(5+2)", "-7"), ("5*(-2)", "-10"), ("(-450-120)", "-570"),
    ("900÷3", "300"), ("3×120", "360"), ("3x120", "360"), ("12 / 3", "4"), ("−450−120", "-570"),
    # thousands commas, Arabic-Indic digits, spaces, = at either end
    ("1,250.50+249.50", "1500"), ("١٢٠+٣٥", "155"), ("  120 + 35 ", "155"), ("=120+35", "155"),
    ("120+35=", "155"), ("=120", "120"), ("5-5", "0"),
])
def test_a_sum_is_saved_as_its_result(typed, saved):
    result = to_decimal(typed)
    assert result == D(saved) and str(result) != "-0"


@pytest.mark.parametrize("typed, says", [
    # misclicks: a sign too many, too few, or in the wrong place
    ("120+", "nothing after the +"), ("120++35", "Two signs in a row: + then +"),
    ("120+-35", "brackets: 2+(-2)"), ("5*-2", "brackets: 2*(-2)"), ("--5", "Two signs in a row"),
    ("*120", "starts with *"), ("x12", "starts with x"), ("12x", "nothing after the x"),
    ("2**3", "for a power, use ^"), ("2^^3", "Two signs in a row: ^ then ^"), ("2^-2", "brackets: 2^(-2)"),
    ("2^", "nothing after the ^"), ("^2", "starts with ^"),
    ("120 35", "not a valid number"), ("100+120 35", "Put a sign between 120 and 35"),
    # brackets
    ("(120+35", "is not closed"), ("(", "is not closed"), ("120+35)", "has no opening one"), (")", "has no opening one"),
    ("1)(2", "has no opening one"), ("()", "Empty brackets"), ("( )", "Empty brackets"), ("(*5)", "can't start with *"),
    ("(2)3", "Put a sign between ) and 3: + - * / or ^"),
    ("[1+2]*3", "round brackets"), ("{1+2}", "round brackets"),
    # readings that differ: never guessed
    ("-2^2", "-2^2 can mean 4 or -4"), ("(-2^2)", "-2^2 can mean 4 or -4"), ("2^3^2", "can mean 64 or 512"),
    ("8/2(2+2)", "can mean 16 or 1"), ("8/(2)(2+2)", "Add the sign: 8/2*(2+2) for 16"),
    # numbers that cannot be right
    ("12..5+1", "'12..5' is not a valid number"), ("12,5+1", "Use a dot for decimals"), ("05+1", "'05' starts with 0"),
    ("1e5+1", "'e' can't be used"), ("10%", "For 10% of 200, type 200*10/100"), ("200*10%", "type 200*10/100"),
    ("120+35=155", "= in the middle"), ("==120", "= in the middle"), ("=", "Enter an amount"),
    # results that cannot be saved exactly
    ("100/0", "can't divide by zero"), ("0/0", "can't divide by zero"), ("0^(-1)", "can't divide by zero"),
    ("100/3", "doesn't come out even. Type the amount you mean, for example 33.33"), ("3^(-1)", "for example 0.33"),
    ("2^0.5", "whole number"), ("0^0", "no single answer"), ("2^41", "power is too large"),
    ("999999999999*10", "too large"), ("999999^3", "too large"), ("1+" * 50 + "1", "too long"),
    # a date typed into the amount field
    ("10/5", "looks like a date"), ("31/12/2026", "looks like a date"), ("2026-10-15", "looks like a date"),
])
def test_an_unclear_sum_is_refused_with_the_reason(typed, says):
    with pytest.raises(ValidationError) as refused:
        to_decimal(typed)
    assert says in refused.value.message


def test_plain_numbers_read_as_before():
    assert to_decimal("1,250.50") == D("1250.50") and to_decimal("-40") == D("-40") and to_decimal("+40") == D("40")
    for typed, says in (("12,5", "Use a dot for decimals"), ("abc", "'abc' is not a valid number"),
                        ("1e5", "not a valid number"), ("-", "not a valid number"), ("", "Enter an amount")):
        with pytest.raises(ValidationError, match=re.escape(says)):
            to_decimal(typed)


def test_the_window_shows_the_result_before_saving_and_the_server_checks_it_again(c):
    client = TestClient(create_app(c))
    assert client.get("/amount-sum", params={"text": "3+5*8"}).json() == {"value": "43"}
    assert client.get("/amount-sum", params={"text": "0.5^2"}).json() == {"value": "0.25"}
    assert "can mean 64 or 512" in client.get("/amount-sum", params={"text": "2^3^2"}).json()["error"]

    cib = c.account_flows.open_account("CIB Current", "BANK", "2026-09-01", "50,000", institution="CIB")
    saved = client.post(f"/accounts/{cib.id}/register", data={
        "date": "2026-09-25", "counterparty": "Carrefour", "counterparty_choice": "create",
        "category": "Personal › Food & Groceries", "amount": "-(450+60*2)"})
    assert saved.status_code == 200 and "Saved." in saved.text
    line, = [x for x in c.transactions.get_by_ref("OUT-2026-09-25-001").lines if x.account_id == cib.id]
    assert line.amount == D("-570")

    refused = client.post(f"/accounts/{cib.id}/register", data={
        "date": "2026-09-26", "counterparty": "Carrefour", "category": "Personal › Food & Groceries", "amount": "-450+"})
    assert refused.status_code == 400 and "nothing after the +" in refused.text
    assert "OUT-2026-09-26-001" not in client.get(f"/accounts/{cib.id}").text


def test_the_window_knows_the_same_sum_marks_as_the_server():
    script = (Path(__file__).parents[1] / "lightning" / "ui" / "static" / "app.js").read_text(encoding="utf-8")
    marks = re.search(r"return /\[(.+?)\]/\.test\(.*as _SUM_MARKS", script).group(1).replace("\\", "")
    assert set(_SUM_MARKS) <= set(marks), "app.js treats fewer characters as a sum than money.py"
