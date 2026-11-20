"""How Lightning works (IV-11N1): the four example cards a new person can read from Welcome before any profile exists.

The owner's order (2026-11-20): recording is quick (a bank SMS logs itself), where the money went, Safe to spend, then
Net worth. The figures are one invented month, the same on every card so they agree; every total is worked out here,
never in the template, the way real figures are (AGENTS §4). Labels are English keys that the page translates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

D = Decimal


@dataclass(frozen=True)
class Row:
    label: str
    amount: Decimal
    note: str = ""


@dataclass(frozen=True)
class Group:
    label: str            # "" for a group with no heading
    rows: tuple[Row, ...]


@dataclass(frozen=True)
class Card:
    key: str
    question: str         # the card's one question, its heading
    answer: str           # one sentence under it
    lead_label: str       # the example's figure name
    lead: Decimal         # the example's figure, worked out from its rows
    line: str             # one sentence under the figure: what it compares with, or what to do
    foot: str             # what this card leaves the person knowing, and what comes next
    groups: tuple[Group, ...] = ()
    message: str = ""     # card 1: the bank message, as the phone receives it
    bars: tuple[Row, ...] = field(default=())  # card 2: the share of each category, as a bar


SPENT_LAST_MONTH = D("12000")


def _sum(rows) -> Decimal:
    return sum((r.amount for r in rows), D("0"))


def cards() -> tuple[Card, ...]:
    # 1. Recording is quick: the message, the row it becomes, and cash in one tap.
    logged = (Row("Carrefour", D("-1240"), "Groceries · From SMS"), Row("Uber", D("-165"), "Transport · From SMS"),
              Row("Koshary at lunch", D("-90"), "Eating out · Added by you"))
    quick = Card(
        "quick", "How do I record my money?",
        "Your bank texts you after every card payment. Lightning reads the message and logs the payment for you.",
        "Logged today", -_sum(logged), "Two from bank messages, one typed in two taps.",
        "Only messages from banks like CIB and NBE are read, never from people. Next: where your money went.",
        groups=(Group("", logged),),
        message="CIB: Your card ending 4321 was charged EGP 1,240.00 at CARREFOUR MAADI.")

    # 2. Where the money went: four categories, then Other (A16), each with its share of the month.
    spent = (Row("Groceries", D("4200")), Row("Bills", D("2800")), Row("Transport", D("1650")),
             Row("Eating out", D("1300")), Row("Other", D("950")))
    total = _sum(spent)
    biggest = max(r.amount for r in spent)
    went = Card(
        "went", "Where did my money go?",
        "Every payment lands in a category, so the month sorts itself.",
        "Spent this month", total,
        "{amt} less than last month.",
        "Lightning suggests a budget from what you actually spend. Next: what you can spend today.",
        bars=tuple(Row(r.label, r.amount, f"{int(r.amount / biggest * 100)}") for r in spent))  # not money: a bar's length

    # 3. Safe to spend: free cash, minus what is already planned until payday.
    free = Row("Free cash", D("10500"))
    planned = (Row("Bills before payday", D("-2800")), Row("Budget until payday", D("-4700")),
               Row("Savings still planned", D("-2000")))
    safe = Card(
        "safe", "What can I spend today?",
        "Your bills, your budget and your savings are set aside first. What is left is safe.",
        "Safe to spend today", free.amount + _sum(planned),
        "Spend up to this today and every plan still holds until payday.",
        "Free cash is what is left after money that already has a job, like a bill due or cash held for family. "
        "Next: everything you own.",
        groups=(Group("", (free,)), Group("Already planned for", planned)))

    # 4. Net worth: what you own minus what you owe.
    own = (Row("Cash and bank accounts", D("15000")), Row("Certificates and gold", D("68000")))
    owe = (Row("Car loan and gam'eya", D("-38500")), Row("Bills due now", D("-1500")))
    worth = Card(
        "worth", "What do I have?",
        "Net worth is what you would keep if you paid everything you owe today.",
        "Net worth", _sum(own) + _sum(owe),
        "{amt} more than at the start of the month.",
        "Not money to spend: it grows as you pay debts and save. Your profile starts empty and fills as you go.",
        groups=(Group("You own", own), Group("You owe", owe)))
    return quick, went, safe, worth


# What each card's {amt} compares with: card 2 against last month, card 4 against the start of the month.
def comparison(card: Card) -> Decimal | None:
    if card.key == "went":
        return SPENT_LAST_MONTH - card.lead
    if card.key == "worth":
        return D("2100")
    return None
