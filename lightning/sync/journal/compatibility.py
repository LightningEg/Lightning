"""Explicit capabilities; incompatible peers keep queues and confirmed copies."""
from __future__ import annotations

from .codec import JournalError, fields


def _capabilities(value):
    fields(value, ("protocol", "app", "ledger_schema", "effects", "entry_kinds", "catalog"))
    if type(value["protocol"]) is not int or type(value["app"]) is not str or not value["app"]:
        raise JournalError("Invalid peer capabilities")
    if type(value["ledger_schema"]) is not int or value["ledger_schema"] < 1:
        raise JournalError("Invalid peer capabilities")
    if type(value["effects"]) is not list or any(type(item) is not int or item < 1 for item in value["effects"]):
        raise JournalError("Invalid peer capabilities")
    if type(value["entry_kinds"]) is not dict or type(value["entry_kinds"].get("commands")) is not list:
        raise JournalError("Invalid peer capabilities")
    if any(type(kind) is not str or len(kind) != 6 or any(char not in "0123456789abcdef" for char in kind)
           for kind in value["entry_kinds"]["commands"]):
        raise JournalError("Invalid peer capabilities")
    for kind, version in value["entry_kinds"].items():
        if kind == "commands":
            continue
        if type(kind) is not str or type(version) is not int or version < 1:
            raise JournalError("Invalid peer capabilities")
    if type(value["entry_kinds"].get("commands")) is not list or len(set(value["entry_kinds"]["commands"])) != len(value["entry_kinds"]["commands"]):
        raise JournalError("Invalid peer capabilities")
    from .codec import hash_value
    hash_value(value["catalog"])


class UpdateRequired(JournalError):
    def __init__(self, target):
        self.target = target
        super().__init__("Update the home before sending these edits" if target == "home" else
                         "Update this device before applying confirmed changes")


def short(kind):
    """A command kind as six hex digits: the capability list stays small as commands are added."""
    import hashlib
    return hashlib.sha256(kind.encode()).hexdigest()[:6]


def capabilities(store):
    from lightning import __version__
    from .commands import KINDS
    from .snapshots import catalog
    return dict(protocol=2, app=__version__, ledger_schema=store.db.scalar("SELECT MAX(version) FROM schema_migrations"),
                effects=[2], entry_kinds={"transaction.add":1,"transaction.edit":1,"transaction.delete":1,
                                 "commands": sorted(short(kind) for kind in KINDS)},
                catalog=catalog(store.adapter))


def check(local, home, pending):
    _capabilities(local)
    _capabilities(home)
    if local["protocol"] != 2:
        raise UpdateRequired("device")
    if home["protocol"] != 2 or home["ledger_schema"] > local["ledger_schema"] or any(value not in local["effects"] for value in home["effects"]):
        raise UpdateRequired("device")
    if home["ledger_schema"] < local["ledger_schema"]:
        raise UpdateRequired("home")
    if home["catalog"] != local["catalog"]:
        raise JournalError("Verified compatible catalog checkpoint required; edits remain pending")
    from .codec import unpack
    for wire in pending:
        body = unpack(wire)["body"]
        known = home["entry_kinds"]
        if (body["kind_version"] != 1 or short(body["kind"]) not in known.get("commands", ())) if body["kind"].startswith("command.") \
                else known.get(body["kind"]) != body["kind_version"]:
            raise UpdateRequired("home")
