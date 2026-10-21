"""A sample household for demos: Mohab's last three months, dated relative to today.

    python -m lightning --demo        # opens a separate demo database, rebuilt on every start

The welcome page also offers it, but only while the database is still empty. Everything is
entered through the same services the screens use, so the demo behaves exactly like real data:
posted transactions (the ledger), a budget, reserves, recurring bills and a car loan (the plan).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from lightning.core.dates import fmt_date, today
from lightning.core.errors import NotFoundError

D = Decimal


def _month_start(day: date, back: int) -> date:
    index = day.year * 12 + day.month - 1 - back
    return date(index // 12, index % 12 + 1, 1)


def _on(start: date, day_of_month: int, until: date) -> str | None:
    """The date in ``start``'s month, or None when it would be after ``until`` (nothing is posted ahead)."""
    try:
        wanted = start.replace(day=day_of_month)
    except ValueError:  # the 29th–31st in a short month
        wanted = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return fmt_date(wanted) if wanted <= until else None


def _investment(c, name: str, class_code: str, symbol: str):
    """The investment with this symbol: reuse it when it was already added (no accounts need it)."""
    from lightning.assets.domain import INVESTMENT_KINDS
    try:
        return c.assets.get_asset_by_code(f"{INVESTMENT_KINDS[class_code].prefix}:{symbol}")
    except NotFoundError:
        return c.assets.create_investment(name, class_code, symbol)


def build_demo(c, as_of: date | None = None) -> dict:
    """Fill an empty Lightning with Mohab's household. Returns a short summary for messages."""
    if c.accounts.list():
        raise ValueError("The demo household can only be added to an empty Lightning.")
    day = as_of or today()
    months = [_month_start(day, back) for back in (2, 1, 0)]
    opened = fmt_date(months[0])
    cat = {code: c.categories.get_by_code(code).id for code in (
        "EXP.WORK.SALARY", "EXP.PERSONAL.HOUSING", "EXP.PERSONAL.FOOD", "EXP.PERSONAL.DINING",
        "EXP.PERSONAL.TRANSPORT", "EXP.PERSONAL.UTILITIES", "EXP.PERSONAL.GIFTS", "EXP.INVEST.INTEREST",
        "EXP.PERSONAL.FEES", "EXP.PERSONAL.HEALTH", "EXP.SYSTEM.CUSTODY", "EXP.PERSONAL.SHOPPING")}
    flows, tx = c.account_flows, c.transactions
    loan_category = c.categories.get_by_code("EXP.SYSTEM.LOANS").id

    with c.db.transaction():
        # ------------------------------------------------------------ ledger: accounts
        cib = flows.open_account("CIB Payroll", "BANK", opened, "138,500", institution="CIB")
        wallet = flows.open_account("Cash wallet", "CASH", opened, "2,000")
        vodafone = flows.open_account("Vodafone Cash", "CASH", opened, "1,200")
        thndr = flows.open_account("THNDR", "BROKERAGE", opened, "0", institution="THNDR")
        cd = flows.open_account("NBE CDs", "DEPOSIT", opened, "0", institution="NBE")
        gold_home = flows.open_account("Gold at home", "PHYSICAL_ASSET", opened, "0")
        purchase_date = months[0]
        c.deposits.purchase(
            cd.id, "NBE 3-year certificate", opened,
            date(purchase_date.year + 1, purchase_date.month, purchase_date.day),
            date(purchase_date.year + 3, purchase_date.month, purchase_date.day),
            "100,000", "22", "SIMPLE", "MONTHLY", "MONTHLY", cib.id, cib.id, term_years="3",
        )

        # ------------------------------------------------------------ ledger: three months of activity
        groceries = [("Carrefour", 2, ["3,180.40", "3,310.20", "3,250.75"]), ("Seoudi", 22, ["1,388.10", "1,452.60", "1,420.40"])]
        eating_out = [("Talabat", 10, ["540.25", "412.00", "468.50"]), ("Koshary El Tahrir", 16, ["180", "210", "165"])]
        for index, start in enumerate(months):
            def post(day_of_month, action, *args, **kwargs):
                when = _on(start, day_of_month, day)
                if when:
                    return action(when, *args, **kwargs)
                return None
            post(1, tx.record_inflow, cib.id, "45,000", cat["EXP.WORK.SALARY"], counterparty="ACME Egypt")
            post(3, tx.record_outflow, cib.id, "12,000", cat["EXP.PERSONAL.HOUSING"], counterparty="Landlord")
            for name, when, amounts in groceries:
                post(when, tx.record_outflow, cib.id, amounts[index], cat["EXP.PERSONAL.FOOD"], counterparty=name)
            for name, when, amounts in eating_out:
                account = wallet.id if name.startswith("Koshary") else cib.id
                post(when, tx.record_outflow, account, amounts[index], cat["EXP.PERSONAL.DINING"], counterparty=name)
            # Untracked on purpose: three months of it make "Looks recurring" offer it from the first day of the demo.
            post(4, tx.record_outflow, cib.id, "900", cat["EXP.PERSONAL.HEALTH"], counterparty="Fitness Time Gym")
            post(5, tx.record_transfer, cib.id, wallet.id, "3,000")
            post(7, tx.record_transfer, cib.id, vodafone.id, "1,000")
            post(9, tx.record_outflow, vodafone.id, "350", cat["EXP.PERSONAL.UTILITIES"], counterparty="Vodafone")
            post(12, tx.record_outflow, wallet.id, ["60", "75", "90"][index], cat["EXP.PERSONAL.TRANSPORT"], counterparty="Microbus")
            if index:  # 22% a year, paid monthly on its payout day (the 1st), first a month after the purchase
                post(1, tx.record_inflow, cib.id, "1,833.33", cat["EXP.INVEST.INTEREST"], counterparty="NBE")
            post(20, tx.record_outflow, cib.id, "650", cat["EXP.PERSONAL.UTILITIES"], counterparty="WE Internet")
            post(24, tx.record_outflow, cib.id, "480", cat["EXP.PERSONAL.UTILITIES"], counterparty="North Cairo Electricity")
            post(25, tx.record_outflow, cib.id, "2,000", cat["EXP.PERSONAL.GIFTS"], counterparty="Mom")
            post(28, tx.record_outflow, cib.id, "15", cat["EXP.PERSONAL.FEES"], counterparty="CIB")
            post(5, tx.record_outflow, cib.id, "2,500", loan_category, counterparty="Toyota Finance")
        post_last = _on(months[1], 18, day)
        if post_last:
            tx.record_outflow(post_last, cib.id, "1,299", cat["EXP.PERSONAL.SHOPPING"], counterparty="Amazon")

        # Held for others: Mom keeps 10,000 in Mohab's CIB account.
        when = _on(months[1], 10, day)
        if when:
            mom = c.counterparties.resolve("Mom")
            txn = tx.record_inflow(when, cib.id, "10,000", cat["EXP.SYSTEM.CUSTODY"], counterparty="Mom",
                                   owner_id=mom["id"] if mom else None)
            c.money_from_others.sync_transaction(txn.id, txn.date, "Mom", cib.id, D("10000"), "Kept for Mom")

        # ------------------------------------------------------------ ledger: investments
        comi = _investment(c, "Commercial International Bank (COMI)", "STOCK", "COMI")
        fawry = _investment(c, "Fawry for Banking Technology", "STOCK", "FWRY")
        fund = _investment(c, "Money market fund", "FUND.MONEY_MARKET", "MMF")
        when = _on(months[1], 11, day)
        if when:
            tx.record_transfer(when, cib.id, thndr.id, "20,000")
            c.investments.buy_total(when, thndr.id, comi.id, "150", "12,150", fees="35")
            c.assets.set_price(comi.id, when, "80.77")
            c.investments.buy_total(when, thndr.id, fawry.id, "500", "4,450", fees="18")
            c.assets.set_price(fawry.id, when, "8.86")
        when = _on(months[2], 1, day)
        if when:
            c.assets.set_price(fund.id, when, "120")
            c.investments.buy_total(when, thndr.id, fund.id, "25", "3,000")

        gold_ref = c.assets.get_asset_by_code("REF:GLD-21K")
        pound = c.physical_items.create(gold_home.id, "Gold pound (from grandma)", "Coin", "8", 21, gold_ref.id)
        ring = c.physical_items.create(gold_home.id, "L'Azurde ring", "Ring", "4.3", 21, gold_ref.id)
        txn = c.investments.add_holding(gold_home.id, pound, "1", "29,000", opened, "Inherited")
        c.physical_items.record_trade_details(txn.id, pound, "OPN", "0", "Inherited")
        when = _on(months[2], 14, day) or _on(months[1], 14, day)
        if when:
            txn = c.investments.buy_total(when, gold_home.id, ring, "1", "18,450", cib.id, "Birthday ring", "0", True)
            c.physical_items.record_trade_details(txn.id, ring, "BUY", "1,950", "Birthday ring")

        # Month-end prices (and today's), as a user would type them.
        price_days = [(months[0] + timedelta(days=40)).replace(day=1) - timedelta(days=1),
                      (months[1] + timedelta(days=40)).replace(day=1) - timedelta(days=1), day]
        prices = [[(comi, "81.00"), (fawry, "8.90"), (fund, "120.40"), (gold_ref, "3,900")],
                  [(comi, "84.20"), (fawry, "9.10"), (fund, "120.90"), (gold_ref, "4,200")],
                  [(comi, "86.50"), (fawry, "9.40"), (fund, "121.30"), (gold_ref, "4,650")]]
        brokerage_ids = {comi.id, fawry.id, fund.id}
        for when, row in zip(price_days, prices):
            if when > day:
                continue
            for asset, price in row:
                if asset.id in brokerage_ids and not c.investments.holding(thndr.id, asset.id, fmt_date(when)):
                    continue
                c.assets.set_price(asset.id, fmt_date(when), price)

        # ------------------------------------------------------------ plan: budget, reserves, bills, a loan
        this_month = fmt_date(months[2])[:7]
        suggested = c.budgets.suggested_plan(this_month)
        if suggested:
            c.budgets.save_month(this_month, suggested)
        c.reserves.set_emergency_fund("20,000", c.budgets.emergency_fund(this_month, None).target or D(0))

        def party(name):
            found = c.counterparties.resolve(name)
            return str(found["id"]) if found else ""

        recurring = [("INCOME", "ACME Egypt", "45,000", 1, cat["EXP.WORK.SALARY"]),
                     ("BILL", "Landlord", "12,000", 3, cat["EXP.PERSONAL.HOUSING"]),
                     ("SUBSCRIPTION", "Vodafone", "350", 9, cat["EXP.PERSONAL.UTILITIES"]),
                     ("BILL", "WE Internet", "650", 20, cat["EXP.PERSONAL.UTILITIES"]),
                     ("BILL", "North Cairo Electricity", "480", 24, cat["EXP.PERSONAL.UTILITIES"])]
        for kind, name, amount, day_of_month, category in recurring:
            account = vodafone.id if name == "Vodafone" else cib.id
            c.planning.create(kind=kind, name=name, amount=amount, frequency="MONTHLY", interval_count="1",
                              start_date=fmt_date(months[0].replace(day=day_of_month)), account_id=str(account),
                              category_id=str(category), counterparty_id=party(name))
        # A car loan three payments in: each payment went out of CIB on the 5th.
        c.planning.create(kind="LOAN", name="Car loan", amount="2,500", frequency="MONTHLY", interval_count="1",
                          start_date=fmt_date(months[0].replace(day=5)), payment_count="24", principal="60,000",
                          account_id=str(cib.id), category_id=str(loan_category),
                          counterparty_id=party("Toyota Finance"), notes="Toyota Finance")

    c.planning.match_payments(day)
    try:
        c.reevaluations.process_due()
    except Exception:  # valuation checkpoints are detail; the demo stands without them
        pass
    return {"accounts": len(c.accounts.list()), "from": opened, "to": fmt_date(day)}
