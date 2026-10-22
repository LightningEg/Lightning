"""Money in and Money out have one rule (`reporting.service.flow_of`), and every path that adds them up
agrees: the cards (cash_flow), the month charts (monthly_flow_between, monthly_trend), the calendars
(flows_by_date), Expense analysis (spending_by_category, money_out_by_category, spending lines),
income by category and Budget (2026-10-04: a refund entered as Money in on an expense category gave
four different Money out figures on four screens)."""
from decimal import Decimal

from lightning.categories.domain import CategoryFamily, Movement
from lightning.core.dates import parse_month
from lightning.core.refs import DocType

D = Decimal
MONTHS = ("2026-09", "2026-10", "2026-11")


def _household(c, setup):
    accounts, cats = setup
    cib, wallet, thndr = accounts["cib"].id, accounts["wallet"].id, accounts["thndr"].id
    tx = c.transactions
    food, transport = cats["EXP.PERSONAL.FOOD"].id, c.categories.get_by_code("EXP.PERSONAL.TRANSPORT").id
    salary = cats["EXP.WORK.SALARY"].id
    dividend = c.categories.get_by_code("EXP.INVEST.DIVIDEND").id
    fees = c.categories.get_by_code("EXP.INVEST.FEES").id
    for month in MONTHS:
        tx.record_inflow(f"{month}-01", cib, "30000", salary)
        tx.record_outflow(f"{month}-05", cib, "1200", food)
        tx.record_outflow(f"{month}-28", wallet, "150", transport)
    tx.record_refund("2026-10-07", cib, "200", food)                     # a refund, as the register records it
    tx.record_inflow("2026-10-09", cib, "90", food)                      # Money in on an expense category
    day, lines = tx._money_lines(Movement.INFLOW, "2026-11-09", cib, "60", food)   # how older profiles hold it
    tx._create(DocType.IN, day, lines, "Older refund", "", "", tx_source())
    tx.record_transfer("2026-10-10", cib, thndr, "5000")                 # never income or spending
    tx.record_inflow("2026-11-12", thndr, "75", dividend)               # investment income
    tx.record_outflow("2026-11-13", thndr, "25", fees)                  # investment spending
    mom = c.counterparties.create("Mom")                                 # money held for Mom: never yours
    tx.record_inflow("2026-10-15", cib, "4000", c.categories.get_by_code("EXP.SYSTEM.CUSTODY").id,
                     allow_system_category=True, owner_id=mom)
    return cats


def tx_source():
    from lightning.transactions.domain import TxnSource
    return TxnSource.MANUAL


def test_every_path_gives_the_same_money_in_and_money_out(c, setup):
    _household(c, setup)
    r = c.reporting
    investment = {cat.id for cat in c.categories.tree() if cat.family == CategoryFamily.INVESTMENT}
    months = {m["month"]: m for m in r.monthly_flow_between("2026-09-01", "2026-11-30")}
    trend = {m["month"]: m for m in r.monthly_trend("2026-11", 3)}
    by_month = r.flows_by_date("2026-09-01", "2026-11-30", "month")
    by_day = r.flows_by_date("2026-09-01", "2026-11-30", "day")
    for month in MONTHS + (None,):
        first, last = parse_month(month) if month else (parse_month(MONTHS[0])[0], parse_month(MONTHS[-1])[1])
        card = r.cash_flow(first, last)
        days = [v for k, v in by_day.items() if month is None or k.startswith(month)]
        outs = {
            "card": card.outflows,
            "days": sum((v["outflows"] for v in days), D(0)),
            "by category, depth 1": sum((g.value for g in r.spending_by_category(first, last, depth=1)), D(0)),
            "by category, depth 2": sum((g.value for g in r.spending_by_category(first, last, depth=2)), D(0)),
            "per category": sum(r.money_out_by_category(first, last).values(), D(0)),
            "spending lines": sum((row["value"] for row in r._spending(first, last)), D(0)),
        }
        ins = {"card": card.inflows, "days": sum((v["inflows"] for v in days), D(0)),
               "income by category": sum((g.value for g in r.money_in_by_category(first, last)), D(0))}
        if month:
            outs |= {"month chart": months[month]["outflows"], "trend": trend[month]["outflows"],
                     "month calendar": by_month[month]["outflows"]}
            ins |= {"month chart": months[month]["inflows"], "trend": trend[month]["inflows"],
                    "month calendar": by_month[month]["inflows"]}
        assert len(set(outs.values())) == 1, (month, outs)
        assert len(set(ins.values())) == 1, (month, ins)
        # Budget leaves investment fees out by design, and nothing else.
        budget = sum(c.budgets.owned_spending(first, last).values(), D(0))
        invest_out = sum((v for k, v in r.money_out_by_category(first, last).items() if k in investment), D(0))
        assert budget == card.outflows - invest_out, month
    october = r.cash_flow("2026-10-01", "2026-10-31")
    assert october.outflows == D("1350") - D("200") - D("90")       # both refunds reduce spending
    assert october.inflows == D("30000")                              # the transfer and Mom's money are not income
    assert r.cash_flow("2026-11-01", "2026-11-30").outflows == D("1350") - D("60") + D("25")
