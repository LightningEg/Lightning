"""Lossless schema-87 journal representation for previously paired replicas."""
from .codec import JournalError, canonical

# Columns added to existing journal rows between ledger schemas 87 and 95.
# Their migration defaults have no financial effect on an existing row.
ADDED_COLUMNS = {
    "reimbursement_claims": {"paid_for_work": 0, "work_closed_on": None},
    "refund_links": {"estimate_date_override": None},
    "reimbursement_receipts": {"estimate_date_override": None},
    "planned_items": {"interest_rate_e6": None, "rate_kind": None},
}

NEW_TABLES = {"cd_rate_changes", "holding_cash_shares", "investment_cash_defaults", "budget_estimate_dates"}


def fingerprint(rows):
    """Only represent data whose full financial contents fit the old ledger."""
    if any(rows.db.scalar(f"SELECT 1 FROM {table} LIMIT 1") for table in NEW_TABLES):
        raise NeedsNewSchema("This ledger contains records that require a newer peer")
    # Most rows have identical wire encodings. Replace only the schema-dependent
    # hashes in the existing accumulator; avoid rereading every ledger entry.
    overrides = {}
    for name, defaults in ADDED_COLUMNS.items():
        table = rows.tables[name]
        for row in rows.db.all(f"SELECT * FROM {name}"):
            key = rows.identity(table, row)
            values = rows.encode(table, row)
            for column, default in defaults.items():
                if values.pop(column) != default:
                    raise NeedsNewSchema("This ledger contains values that require a newer peer")
            overrides[name + ":" + canonical(key).decode()] = rows.row_hash(name, key, values)
    return rows.combine(overrides.get(slot, value) for slot, value in rows.db.all("SELECT uuid,hash FROM journal_fp"))


def expand(domain):
    rows = []
    for item in domain["rows"]:
        name = item["table"]
        if name in NEW_TABLES:
            raise JournalError("Unexpected table in schema 87 effects")
        defaults = ADDED_COLUMNS.get(name, {})
        values = item["values"]
        if values is not None and defaults:
            if defaults.keys() & values.keys():
                raise JournalError("Unexpected column in schema 87 effects")
            item = dict(item, values=values | defaults)
        rows.append(item)
    return dict(domain, rows=rows)


def project(domain):
    """Encode a confirmed effect exactly as a schema-87 replica can apply it."""
    items = []
    for item in domain["rows"]:
        name = item["table"]
        if name in NEW_TABLES:
            raise NeedsNewSchema("This edit needs a newer ledger schema")
        if item["values"] is not None and name in ADDED_COLUMNS:
            values = dict(item["values"])
            for column, default in ADDED_COLUMNS[name].items():
                if values.pop(column) != default:
                    raise NeedsNewSchema("This edit needs a newer ledger schema")
            item = dict(item, values=values)
        items.append(item)
    return items


class NeedsNewSchema(JournalError):
    """The confirmed rows carry information the old version cannot store."""


def through(db):
    """Last revision using schema 87. Minus one keeps the old format active."""
    if not db.has_table("journal_wire_history"):
        return None
    return db.scalar("SELECT last_87 FROM journal_wire_history WHERE id=1")


def old_devices(store):
    return store.db.scalar("""SELECT 1 FROM journal_origins o WHERE revoked=0 AND device!=?
        AND NOT EXISTS (SELECT 1 FROM journal_local l WHERE l.name='peer95:' || o.device || '/' || o.incarnation)
        LIMIT 1""", (store.config["device"],)) is not None
