"""Home-only scheduled financial work, carried as ordinary signed commands.

The command result is the exact row effect captured by the journal adapter, so
replicas replay it without running rules, matching, or price automation locally.
"""
from datetime import date

from .spec import DATE, TEXT, Command

TABLES = (
    "planned_payments", "price_history", "reevaluation_periods",
    "reevaluation_entries", "reevaluation_account_posts",
    "reevaluation_suppressed_accounts",
)


def _fill_prices(container, *, as_of):
    from lightning.workflows.market_prices import fill_if_due
    return fill_if_due(container, date.fromisoformat(as_of))


def _fill_prices_now(container, *, as_of):
    from lightning.workflows.market_prices import fill_followed
    return fill_followed(container, date.fromisoformat(as_of))


def _process_due(container):
    return container.reevaluations.process_due()


def _match_bills(container, *, as_of):
    return container.planning.match_payments(date.fromisoformat(as_of))


def _mark_live_fetch(container, *, as_of):
    from lightning.workflows.live_prices import TRIED_SETTING
    container.settings.set(TRIED_SETTING, as_of)


def _apply_live_prices(container, *, job_key):
    from lightning.sync.journal.automation import apply_live_prices
    return apply_live_prices(container, job_key)


COMMANDS = {
    "automation.fill_prices": Command(_fill_prices, dict(as_of=DATE)),
    "automation.fill_prices_now": Command(_fill_prices_now, dict(as_of=DATE)),
    "automation.process_due": Command(_process_due, {}),
    "automation.match_bills": Command(_match_bills, dict(as_of=DATE)),
    "automation.mark_live_fetch": Command(_mark_live_fetch, dict(as_of=DATE)),
    "automation.apply_live_prices": Command(_apply_live_prices, dict(job_key=TEXT)),
}
