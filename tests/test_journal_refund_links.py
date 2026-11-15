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
