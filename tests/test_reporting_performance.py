"""Guard the reporting hot paths against per-row metadata queries."""

from decimal import Decimal
from time import perf_counter


def _add_synthetic_transfers(c, accounts, count=319, sequence_start=0):
    """Add a compact, internally balanced 319-transfer read-load fixture."""
    cash_id = c.assets.cash_asset("EGP").id
    with c.db.transaction():
        for sequence in range(sequence_start, sequence_start + count):
            day = (sequence % 29) + 2  # after the opening position, within September
            date = f"2026-09-{day:02}"
            ref = f"PERF-{sequence:04}"
            cursor = c.db.execute(
                "INSERT INTO transactions(ref,type,date,description,status,source,created_at,updated_at) "
                "VALUES (?,'TRF',?,'Synthetic performance transfer','POSTED','MANUAL',?,?)",
                (ref, date, date + "T12:00:00", date + "T12:00:00"),
            )
            transaction_id = cursor.lastrowid
            for line_no, account_id, signed in (
                (1, accounts["cib"].id, -10_000_000),
                (2, accounts["thndr"].id, 10_000_000),
            ):
                c.db.execute(
                    "INSERT INTO ledger_entries(transaction_id,line_no,date,account_id,asset_id,quantity_e6,"
                    "unit_price_e6,amount_e6,fx_rate_e6,amount_base_e6,effect) "
                    "VALUES (?,?,?,?,?,?,1000000,?,?,?,'INTERNAL')",
                    (transaction_id, line_no, date, account_id, cash_id, signed, signed, 1_000_000, signed),
                )


def test_holdings_loads_metadata_in_batches_and_reflects_new_transactions(c, setup, monkeypatch):
    accounts, cats = setup
    counts = {"account_get": 0, "asset_get": 0, "class_get": 0}
    original_account_get = c.accounts.get
    original_asset_get = c.assets.get_asset
    original_class_get = c.assets.get_class

    def account_get(*args, **kwargs):
        counts["account_get"] += 1
        return original_account_get(*args, **kwargs)

    def asset_get(*args, **kwargs):
        counts["asset_get"] += 1
        return original_asset_get(*args, **kwargs)

    def class_get(*args, **kwargs):
        counts["class_get"] += 1
        return original_class_get(*args, **kwargs)

    monkeypatch.setattr(c.accounts, "get", account_get)
    monkeypatch.setattr(c.assets, "get_asset", asset_get)
    monkeypatch.setattr(c.assets, "get_class", class_get)

    earlier, _ = c.reporting.holdings("2026-09-30")
    assert counts == {"account_get": 0, "asset_get": 0, "class_get": 0}
    assert sum((row.value or Decimal(0) for row in earlier), Decimal(0)) == Decimal("56200")

    c.transactions.record_inflow("2026-10-01", accounts["cib"].id, "1200", cats["EXP.WORK.SALARY"].id)
    counts.update(account_get=0, asset_get=0, class_get=0)
    later, _ = c.reporting.holdings("2026-10-01")
    assert sum((row.value or Decimal(0) for row in later), Decimal(0)) == Decimal("57400")
    assert counts == {"account_get": 0, "asset_get": 0, "class_get": 0}


def test_investment_report_does_not_fetch_asset_metadata_per_ledger_row(c, setup, monkeypatch):
    accounts, _ = setup
    count = 0
    original_get = c.assets.get_asset

    def get_asset(*args, **kwargs):
        nonlocal count
        count += 1
        return original_get(*args, **kwargs)

    monkeypatch.setattr(c.assets, "get_asset", get_asset)
    from lightning.investments.report import build_investment_report

    def measure(end):
        statements = []
        c.db.conn.set_trace_callback(statements.append)
        start = perf_counter()
        result = build_investment_report(c.db, c.accounts, c.assets, c.reporting,
                                         "2026-09-01", end)
        elapsed = (perf_counter() - start) * 1000
        c.db.conn.set_trace_callback(None)
        selects = [sql for sql in statements if sql.lstrip().upper().startswith("SELECT")]
        return result, len(selects), elapsed

    before, _, _ = measure("2026-09-01")
    assert before["investment_cash"] == Decimal(0)
    _add_synthetic_transfers(c, accounts, 12)
    small, small_queries, small_ms = measure("2026-09-15")
    assert small["investment_cash"] == Decimal("120")
    count_before_load = count
    _add_synthetic_transfers(c, accounts, 307, sequence_start=12)
    after, after_queries, after_ms = measure("2026-09-30")
    assert after["investment_cash"] == Decimal("3190")
    assert count - count_before_load <= 3  # bounded by distinct holdings resolved for the final report
    assert after_queries == small_queries  # not proportional to ledger row count

    rows = c.db.all(
        "SELECT le.asset_id FROM ledger_entries le JOIN transactions t ON t.id=le.transaction_id "
        "WHERE t.status='POSTED' AND t.type<>'VAL' AND le.owner_id IS NULL AND le.date<='2026-09-30'")
    lookup_sql = []
    c.db.conn.set_trace_callback(lookup_sql.append)
    lookup_start = perf_counter()
    for row in rows:  # reproduce the removed one-get_asset-per-ledger-row behavior
        c.assets.get_asset(row["asset_id"])
    lookup_ms = (perf_counter() - lookup_start) * 1000
    c.db.conn.set_trace_callback(None)
    legacy_lookup_queries = sum(sql.lstrip().upper().startswith("SELECT") for sql in lookup_sql)
    assert legacy_lookup_queries == len(rows)
    print(f"investment_report SQL={small_queries}/{after_queries} "
          f"service_ms={small_ms:.1f}/{after_ms:.1f} (12/319 transfers); "
          f"former row lookup loop={legacy_lookup_queries} SQL, {lookup_ms:.1f}ms; "
          f"optimized total queries={after_queries}, former estimated total={after_queries - 1 + legacy_lookup_queries}")


# -- the request cache (lightning/core/memo.py) ---------------------------------------------------

def _select_count(c, action):
    statements = []
    c.db.conn.set_trace_callback(statements.append)
    try:
        result = action()
    finally:
        c.db.conn.set_trace_callback(None)
    return result, sum(sql.lstrip().upper().startswith("SELECT") for sql in statements)


def test_a_request_reads_a_figure_once_and_forgets_it_after_a_write(c, setup):
    from lightning.core.memo import request_cache
    accounts, cats = setup
    with request_cache(c.db):
        first, first_reads = _select_count(c, lambda: c.reporting.net_worth("2026-10-01").total)
        again, again_reads = _select_count(c, lambda: c.reporting.net_worth("2026-10-01").total)
        assert first_reads > 0 and again_reads == 0 and again == first
        c.transactions.record_inflow("2026-10-01", accounts["cib"].id, "1200", cats["EXP.WORK.SALARY"].id)
        assert c.reporting.net_worth("2026-10-01").total == first + Decimal("1200")


def test_nothing_is_cached_inside_a_transaction_so_a_rollback_leaves_nothing_behind(c, setup):
    from lightning.core.memo import request_cache
    accounts, cats = setup
    with request_cache(c.db):
        before = c.reporting.net_worth("2026-10-01").total
        try:
            with c.db.transaction():
                c.transactions.record_inflow("2026-10-01", accounts["cib"].id, "500", cats["EXP.WORK.SALARY"].id)
                assert c.reporting.net_worth("2026-10-01").total == before + Decimal("500")
                raise RuntimeError("roll back")
        except RuntimeError:
            pass
        assert c.reporting.net_worth("2026-10-01").total == before


def test_a_caller_that_edits_a_cached_result_does_not_change_the_next_one(c, setup):
    from lightning.core.memo import request_cache
    with request_cache(c.db):
        rows, unvalued = c.reporting.holdings("2026-10-01")
        count = len(rows)
        rows.clear()
        unvalued.append("edited by a caller")
        again_rows, again_unvalued = c.reporting.holdings("2026-10-01")
        assert len(again_rows) == count and "edited by a caller" not in again_unvalued


def _years_of_history(c, years):
    """Ordinary activity before Mohab's 2026: salary, a cash withdrawal, 20 card and 10 cash payments a month."""
    import random
    rnd = random.Random(7)
    names = {account.name: account.id for account in c.accounts.list()}
    bank, wallet = names["CIB Payroll"], names["Cash wallet"]
    cats = {cat.code: cat.id for cat in c.categories.tree()}
    spend = [cats[code] for code in ("EXP.PERSONAL.FOOD", "EXP.PERSONAL.DINING", "EXP.PERSONAL.TRANSPORT",
                                     "EXP.PERSONAL.UTILITIES", "EXP.PERSONAL.SHOPPING")]
    with c.db.transaction():
        for year in range(2026 - years, 2026):
            for month in range(1, 13):
                day = lambda d: f"{year}-{month:02d}-{d:02d}"
                c.transactions.record_inflow(day(1), bank, "30000", cats["EXP.WORK.SALARY"], "Salary", "Employer")
                c.transactions.record_transfer(day(2), bank, wallet, "5000", "Cash")
                for _ in range(20):
                    c.transactions.record_outflow(day(rnd.randint(3, 28)), bank, str(rnd.randint(50, 900)),
                                                  rnd.choice(spend), "Card", rnd.choice(["Carrefour", "Uber"]))
                for _ in range(10):
                    c.transactions.record_outflow(day(rnd.randint(3, 28)), wallet, str(rnd.randint(20, 300)),
                                                  rnd.choice(spend[:3]), "Cash", "Kiosk")


# Pages, and the most SELECT statements each may run on Mohab's 2026 plus two earlier years
# (about 1,100 transactions). Before the request cache they ran 1,700 to 10,000; repeated
# figures (positions, ledger scans, month spending, category look-ups) must stay computed once.
# Tightened 2026-10-04 (bill payments, prices and gold items read once per request; register owners
# in one read; reserve suggestions check the amount first): the pages then ran 80 to 550, and each
# budget is about 1.3 times that.
PAGE_READ_BUDGET = {
    "/": 640,  # 640: the sample plan gained a yearly course and bonus (2026-10-07; was 605 after the SMS check)
    "/accounts/1": 120, "/transactions": 110, "/budget?period=month": 175,
    "/budget?period=all": 710, "/plan": 340, "/investments": 235, "/birdview/expenses?period=all": 230,
}


def test_main_tabs_read_each_figure_once_and_show_the_same_pages_as_without_the_cache(c, monkeypatch):
    import contextlib
    import re
    from fastapi.testclient import TestClient
    import lightning.ui.web as web
    from lightning.samples import load_mohab_2026

    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-02")
    load_mohab_2026(c)
    _years_of_history(c, 2)
    app = web.create_app(c)
    nonce = re.compile(r'nonce="[^"]*"')
    with TestClient(app) as browser:
        for path in PAGE_READ_BUDGET:
            browser.get(path)  # settle anything a first visit records (matched bill payments)
        cached = {}
        for path, budget in PAGE_READ_BUDGET.items():
            statements = []
            original_conn = type(c.db).conn.fget

            def traced(db, _statements=statements):
                conn = original_conn(db)
                conn.set_trace_callback(_statements.append)
                return conn

            monkeypatch.setattr(type(c.db), "conn", property(traced))
            response = browser.get(path)
            monkeypatch.setattr(type(c.db), "conn", property(original_conn))
            c.db.conn.set_trace_callback(None)
            reads = sum(sql.lstrip().upper().startswith("SELECT") for sql in statements)
            assert response.status_code == 200, path
            assert reads <= budget, f"{path} ran {reads} SELECT statements (budget {budget})"
            cached[path] = nonce.sub("", response.text)
        monkeypatch.setattr(web, "request_cache", lambda _db: contextlib.nullcontext())
        for path in PAGE_READ_BUDGET:
            assert nonce.sub("", browser.get(path).text) == cached[path], f"{path} differs without the cache"


def test_a_register_page_reads_only_its_rows_and_matches_the_full_register(c, monkeypatch):
    from lightning.samples import load_mohab_2026

    monkeypatch.setenv("LIGHTNING_TODAY", "2026-10-02")
    load_mohab_2026(c)
    _years_of_history(c, 1)
    for account_id in [account.id for account in c.accounts.list()] + [None]:
        for start, end in (("1900-01-01", "9999-12-31"), ("2026-03-01", "2026-08-31"), ("2030-01-01", "2030-12-31")):
            full = c.reporting.register(account_id, start, end)
            pages = max(1, -(-len(full) // 50))
            for asked in range(0, pages + 2):  # out-of-range pages are clamped
                rows, total, page = c.reporting.register_page(account_id, start, end, asked)
                expected_page = min(max(asked, 1), pages)
                assert (total, page) == (len(full), expected_page)
                assert rows == full[(expected_page - 1) * 50:expected_page * 50]  # running balances included
    lines = []
    original = c.reporting.q.statement_lines
    monkeypatch.setattr(c.reporting.q, "statement_lines",
                        lambda *args, **kwargs: lines.append(original(*args, **kwargs)) or lines[-1])
    c.reporting.register_page(1, "1900-01-01", "9999-12-31", 3)
    assert len(lines) == 1 and len(lines[0]) == 50  # read one page, not the whole history
