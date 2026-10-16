"""Explicit capabilities; incompatible peers keep queues and confirmed copies."""
from __future__ import annotations

from .codec import JournalError, fields


class UpdateRequired(JournalError):
    def __init__(self, target):
        self.target = target
        super().__init__("Update the home before sending these edits" if target == "home" else
                         "Update this device before applying confirmed changes")


def capabilities(store):
    from lightning import __version__
    from .snapshots import catalog
    full = getattr(store.adapter, 'full_domain', False)
    kinds = {"transaction.add":1,"transaction.edit":1,"transaction.delete":1}
    if full:
        kinds['action.add'] = 2  # Highest supported version; original v1 queues remain valid.
    if store.db.has_table('journal_acks'):
        kinds['control.ack'] = 1
        kinds['control.receipts'] = 1
    return dict(protocol=2, app=__version__, ledger_schema=store.db.scalar("SELECT MAX(version) FROM schema_migrations"),
                effects=[2] if full else [1], entry_kinds=kinds,
                catalog=catalog(store.adapter))


def check(local, home, pending):
    fields(home, ("protocol", "app", "ledger_schema", "effects", "entry_kinds", "catalog"))
    if home["protocol"] != 2 or home["ledger_schema"] > local["ledger_schema"] or any(value not in local["effects"] for value in home["effects"]):
        raise UpdateRequired("device")
    if home["ledger_schema"] < local["ledger_schema"]:
        raise UpdateRequired("home")
    if home["catalog"] != local["catalog"]:
        raise JournalError("Verified compatible catalog checkpoint required; edits remain pending")
    from .codec import unpack
    for wire in pending:
        body = unpack(wire)["body"]
        supported = home["entry_kinds"].get(body["kind"])
        if type(supported) is not int or supported < body['kind_version']:
            raise UpdateRequired("home")
