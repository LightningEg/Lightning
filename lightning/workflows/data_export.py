"""Complete local financial records, for inspection and portability rather than profile restore."""
import csv
from io import BytesIO, StringIO
from zipfile import ZIP_DEFLATED, ZipFile

from lightning.core.money import from_e6
from lightning.reporting.xlsx import MAX_ROWS, tabular_workbook_bytes

# Explicit financial-data boundary: passwords, pairing material, licences and runtime configuration
# are not exported. These are user records, including archived/voided items and unfinished reviews.
TABLES = ("profile_identity", "accounts", "asset_classes", "financial_assets", "categories", "counterparties",
          "counterparty_aliases", "institutions", "transactions", "ledger_entries", "registered_currencies", "currency_suggestions",
          "fx_rates", "price_history", "budgets", "budget_carryover", "budget_carryover_resets", "cash_reserves",
          "reserve_allocation_history", "reserve_transaction_links", "planned_items", "planned_payments",
          "loan_extra_payments", "installment_purchases", "cd_terms", "cd_certificates", "cd_redemptions",
          "gameya_terms", "money_from_others", "investment_custody_events", "investment_dividend_assets",
          "investment_liquidation_factors", "investment_targets", "physical_items", "physical_item_valuations",
          "physical_item_trade_details", "other_asset_valuations", "rules", "rule_conditions", "rule_actions",
          "bank_import_batches", "bank_import_rows", "bank_import_column_maps", "reevaluation_periods",
          "reevaluation_entries", "reevaluation_account_posts", "reevaluation_suppressed_accounts", "zakat_settings",
          "reconciled_through", "saved_views", "reimbursement_claims", "reimbursement_receipts",
          "cd_interest_receipt_events", "cd_interest_receipt_links", "cash_funding", "audit_log")


def _safe_text(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def _raw_tables(c):
    tables = []
    # One consistent read snapshot, with no plaintext files on disk.
    with c.db.read_snapshot():
        present = {row["name"] for row in c.db.all("SELECT name FROM sqlite_master WHERE type='table'")}
        for name in (*TABLES, "settings"):
            if name not in present:
                continue
            columns = [row["name"] for row in c.db.all(f'PRAGMA table_info("{name}")')]
            rows = c.db.all(f'SELECT * FROM "{name}" ORDER BY rowid')
            if name == "settings":
                rows = [row for row in rows if row["key"] in ("base_currency", "locale", "privacy_mode")
                        or row["key"].startswith(("budget_", "investment_", "emergency_", "health_", "financial_health_"))]
            headings = [column.removesuffix("_e6") for column in columns]
            values = [tuple(from_e6(row[col]) if col.endswith("_e6") and row[col] is not None else row[col]
                            for col in columns) for row in rows]
            tables.append((name, headings, values, [22] * len(columns)))
    return tables



RELATIONS = {"account_id": ("accounts", "name"), "asset_id": ("financial_assets", "name"),
             "category_id": ("categories", "name"), "transaction_id": ("transactions", "ref"),
             "owner_id": ("counterparties", "name"), "counterparty_id": ("counterparties", "name"),
             "asset_class_id": ("asset_classes", "name"), "cash_class_id": ("asset_classes", "name"),
             "funding_account_id": ("accounts", "name"), "payout_account_id": ("accounts", "name")}



def readable_relations(c, name):
    relations = {}
    for fk in c.db.all(f'PRAGMA foreign_key_list("{name}")'):
        target, column = fk["table"], fk["from"]
        if target not in TABLES:
            continue
        fields = {row["name"] for row in c.db.all(f'PRAGMA table_info("{target}")')}
        label = next((key for key in ("name", "ref", "code") if key in fields), None)
        if label and column.endswith("_id"):
            relations[column] = (target, label)
    return relations

def export_tables(c):
    """Readable context first, unchanged schema columns at the tail for exact mapping."""
    with c.db.read_snapshot():
        raw = _raw_tables(c)
        records = {name: [dict(zip(headings, row)) for row in rows]
                   for name, headings, rows, _ in raw}
        lookup = {name: {row.get("id"): row for row in rows} for name, rows in records.items()}
        categories = lookup.get("categories", {})

        def levels(category_id):
            path, seen = [], set()
            while category_id in categories and category_id not in seen:
                seen.add(category_id)
                cat = categories[category_id]
                if cat.get("parent_id") is not None:
                    path.insert(0, cat["name"])
                category_id = cat.get("parent_id")
            return (path + ["", "", ""])[:3]

        tables = []
        for name, headings, rows, widths in raw:
            relations = readable_relations(c, name)
            display = []
            if name == "ledger_entries":
                display = ["Transaction ID", "Transaction reference", "Account", "Date", "Counterparty", "Currency",
                           "Total in currency", "FX rate", "Total in default currency", "Category L1", "Category L2", "Asset", "Owner"]
            else:
                display = [key.removesuffix("_id").replace("_", " ").title()
                           for key in headings if key in relations]
                if name == "categories":
                    display += ["Category L1", "Category L2", "Category L3"]
            # Raw identifiers and audit metadata come after the fields people read.
            order = [h for h in headings if h != "id" and not h.endswith("_id") and h not in ("created_at", "updated_at")]
            order += [h for h in headings if h not in order]
            values = []
            for record in records[name]:
                if name == "ledger_entries":
                    txn = lookup.get("transactions", {}).get(record["transaction_id"], {})
                    account = lookup.get("accounts", {}).get(record["account_id"], {})
                    asset = lookup.get("financial_assets", {}).get(record["asset_id"], {})
                    prefix = [record["transaction_id"], txn.get("ref", ""), account.get("name", ""), record["date"],
                              txn.get("counterparty", ""), asset.get("currency", account.get("currency", "")),
                              record["amount"], record["fx_rate"], record["amount_base"], *levels(record.get("category_id"))[:2],
                              asset.get("name", ""), lookup.get("counterparties", {}).get(record.get("owner_id"), {}).get("name", "")]
                else:
                    prefix = [lookup.get(relations[h][0], {}).get(record[h], {}).get(relations[h][1], "")
                              for h in headings if h in relations]
                    if name == "categories":
                        prefix += levels(record["id"])
                values.append(tuple(prefix + [record[h] for h in order]))
            tables.append((name, display + order, values, [22] * (len(display) + len(order))))
        priority = ["ledger_entries", "transactions", "accounts", "categories", "counterparties", "financial_assets"]
        tables.sort(key=lambda table: (priority.index(table[0]) if table[0] in priority else len(priority), not bool(table[2])))
        index = [(name, len(rows), "Financial records" if rows else "Empty table retained for portability")
                 for name, _, rows, _ in tables]
        notes = [("Start here", "Read ledger_entries for activity; names come first and mapping columns are at the tail."),
                 ("Amounts", "Money, quantities and FX are decimal values, not stored millionths. Dates are ISO yyyy-mm-dd."),
                 ("Import", "Import this complete workbook into an empty profile through Settings → Your data → Import your data."),
                 ("Mapping", "Lower-case schema columns at the tail are authoritative for import. Readable columns are context; keep both consistent."),
                 ("Privacy", "This workbook is unencrypted. Passwords, pairing material and runtime configuration are excluded.")]
        return [("Read me", ["Sheet", "Records", "Purpose"], [(a, "", b) for a, b in notes] + index, [40, 14, 85])] + tables

def export_all(c, format):
    tables = export_tables(c)
    if format == "xlsx":
        sheets = []
        for name, headings, rows, widths in tables:
            parts = max(1, (len(rows) + MAX_ROWS - 2) // (MAX_ROWS - 1))
            for part in range(parts):
                suffix = f"_{part + 1}" if parts > 1 else ""
                sheet_name = name[:31 - len(suffix)] + suffix
                sheets.append((sheet_name, headings, rows[part * (MAX_ROWS - 1):(part + 1) * (MAX_ROWS - 1)], widths))
        return tabular_workbook_bytes(sheets), "lightning-all-data.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if format != "csv":
        raise ValueError("Choose Excel or CSV.")
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, headings, rows, _ in tables:
            buffer = StringIO(newline="")
            writer = csv.writer(buffer)
            writer.writerow(headings)
            writer.writerows(tuple(_safe_text(value) for value in row) for row in rows)
            archive.writestr(name + ".csv", "\ufeff" + buffer.getvalue())
        archive.writestr("README.txt", "Lightning financial data\nAll dates and IDs are preserved. Money and quantities are decoded from millionths to decimal values.\nIncludes archived and voided records and unfinished statement reviews. CSV text that could be a spreadsheet formula is prefixed with an apostrophe.\nSecurity credentials are excluded. These unencrypted inspection files are not profile backups; use Back up now to restore a profile.\n")
    return output.getvalue(), "lightning-all-data.zip", "application/zip"
