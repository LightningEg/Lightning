"""Household records: saved register views, reimbursement claims and their receipts, and the zakat settings."""
from .spec import AMOUNT, DATE, FLAG, TEXT, Command, filtered, optional, ref

TABLES = ("saved_views", "reimbursement_claims", "reimbursement_receipts", "zakat_settings")
# The one zakat row exists on every device from the start, so its identity is fixed rather than random.
NATURAL = {"zakat_settings": ("id",)}

CLAIM = ("reimbursement_claims", "claim_id")
# The register's own filters; the form posts more fields than a view keeps.
VIEW = filtered(preset=TEXT, date_from=TEXT, date_to=TEXT, q=TEXT, tag=TEXT, category_id=optional(ref("categories")))
COMMANDS = {
    "saved_views.save": Command("saved_views.save", dict(name=TEXT, filters=VIEW, account_id=optional(ref("accounts"))),
                                creates="saved_views"),
    "saved_views.delete": Command("saved_views.delete", dict(view_id=ref("saved_views"), account_id=optional(ref("accounts"))),
                                  target=("saved_views", "view_id")),
    "reimbursements.create_claim": Command("reimbursements.create_claim", dict(
        transaction_id=ref("transactions"), expected=AMOUNT, payer_id=optional(ref("counterparties")),
        due_date=optional(DATE)), creates="reimbursement_claims"),
    "reimbursements.link_receipt": Command("reimbursements.link_receipt", dict(
        claim_id=ref("reimbursement_claims"), transaction_id=ref("transactions"), amount=AMOUNT), target=CLAIM,
        creates="reimbursement_receipts"),
    "reimbursements.unlink_receipt": Command("reimbursements.unlink_receipt", dict(
        claim_id=ref("reimbursement_claims"), link_id=ref("reimbursement_receipts")), target=CLAIM),
    "reimbursements.delete_claim": Command("reimbursements.delete_claim", dict(claim_id=ref("reimbursement_claims")),
                                           target=CLAIM),
    # The settings are one row that always exists; the last save wins.
    "zakat.save_settings": Command("zakat.save_settings", dict(
        zakat_day=optional(TEXT), typed_nisab=optional(AMOUNT), count_worn_gold=FLAG, deduct_debts_due=FLAG)),
    "zakat.save_nisab_basis": Command("zakat.save_nisab_basis", dict(nisab_basis=TEXT, typed_silver=optional(AMOUNT))),
}
