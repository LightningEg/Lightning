"""Refund links survive journal replication when a refund is recorded on a replica."""
from decimal import Decimal

from test_journal_finance import devices  # noqa: F401
from test_journal_area_more import act, on_home
from test_journal_area_plans import account, category


def test_record_refund_replicates_transaction_and_link(devices):
    home, replica = devices
    bank = account(home, "Bank").id
    food = category(home).id
    on_home(home, lambda s: s.transactions.record_outflow(
        "2026-09-02", bank, Decimal("200"), food, counterparty="Hotel"))
    replica.sync_with(home.home)
    expense = replica.c.db.scalar("SELECT id FROM transactions WHERE counterparty='Hotel'")
    act(home, replica, lambda s: s.refunds.record_refund(expense, "2026-10-02", Decimal("50")))
    for device in (home, replica):
        assert device.c.db.scalar("SELECT count(*) FROM refund_links") == 1
        assert device.c.db.scalar("SELECT amount_e6 FROM refund_links") == 50_000_000


def test_estimate_dates_replicate_and_clear(devices):
    home, replica = devices
    bank, food = account(home, "Bank").id, category(home).id
    on_home(home, lambda s: s.transactions.record_outflow("2026-09-02", bank, Decimal("200"), food, counterparty="Hotel"))
    replica.sync_with(home.home)
    expense = replica.c.db.scalar("SELECT id FROM transactions WHERE counterparty='Hotel'")
    act(home, replica, lambda s: s.budgets.set_estimate_date(expense, "2026-08-21"))
    act(home, replica, lambda s: s.refunds.record_refund(expense, "2026-10-02", Decimal("50")))
    link = replica.c.db.scalar("SELECT id FROM refund_links")
    act(home, replica, lambda s: s.refunds.set_estimate_date(link, "2026-09-04"))
    for device in (home, replica):
        assert device.c.db.scalar("SELECT estimate_date FROM budget_estimate_dates") == "2026-08-21"
        assert device.c.db.scalar("SELECT estimate_date_override FROM refund_links") == "2026-09-04"
    act(home, replica, lambda s: s.budgets.set_estimate_date(expense, None))
    assert home.c.db.scalar("SELECT COUNT(*) FROM budget_estimate_dates") == 0


def test_dated_posting_and_claim_are_one_replica_command(devices):
    home, replica = devices
    bank, food = account(replica, "Bank").id, category(replica).id
    act(home, replica, lambda s: s.dated_entries.capture("2026-08-21", "2026-09-02", bank, Decimal("-200"),
                                                         food, "Trip", "", None, paid_for_work=True, expected="100"))
    for device in (home, replica):
        assert device.c.db.scalar("SELECT estimate_date FROM budget_estimate_dates") == "2026-08-21"
        assert device.c.reimbursements.list_claims()[0]["outstanding"] == 100
    expense = replica.c.db.scalar("SELECT transaction_id FROM budget_estimate_dates")
    act(home, replica, lambda s: s.refunds.record_dated_refund(expense, "2026-09-20", Decimal("50"), "",
                                                               "2026-08-22"))
    for device in (home, replica):
        assert device.c.db.scalar("SELECT estimate_date_override FROM refund_links") == "2026-08-22"
