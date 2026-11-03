"""Atomic local transaction-entry writes and their automatic payment links."""
from contextlib import contextmanager

from lightning.core.dates import today


@contextmanager
def settled_write(c):
    """Commit a save, retry marker and payment links together; journal commands own their settlement."""
    with c.db.transaction():
        yield
        if not getattr(c, "is_journal", False):
            c.planning.match_payments(today())
