"""Atomic local writes and their automatic payment links."""
from contextlib import contextmanager

from lightning.core.dates import today


@contextmanager
def settled_write(c, **transaction_options):
    """Commit a save, retry marker and payment links together; journal commands own their settlement."""
    base = getattr(getattr(c, "transactions", None), "base_currency", None)
    try:
        with c.db.transaction(**transaction_options):
            yield
            if not getattr(c, "is_journal", False):
                c.planning.match_payments(today())
    except BaseException:
        if (base is not None and c.transactions.base_currency != base
                and hasattr(c, "refresh_profile_currency")):
            c.refresh_profile_currency(base=base)
        raise
