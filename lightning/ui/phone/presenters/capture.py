"""The phone's Add sheet (templates/phone/transactions/form_popup.html): the accounts its From chip can change to, the
bills due and the usual categories as chips. Only a new entry has them; editing shows the fields alone (3AY11)."""
from __future__ import annotations

from lightning.core.dates import today


def _entry_accounts(c) -> list:
    """The accounts a hand-entered transaction can go to: every active one that holds money, not a thing you own."""
    return [a for a in c.accounts.list(active_only=True) if a.account_type.value not in ("PHYSICAL_ASSET", "OTHER_ASSET")]


def _capture_context(c, account) -> dict:
    """What the phone's Add sheet shows besides the fields (3AN3): the accounts its From chip can change to, and the
    usual categories for money out and money in as chips, most used first (computed from this person's history in
    TransactionService.usual_capture_categories; never in the template)."""
    def named(group):
        names = [c.categories.get(category_id).name for category_id in group]
        return [{"id": category_id, "label": c.categories.get(category_id).name if names.count(name) == 1
                 else c.categories.display_name(category_id)} for category_id, name in zip(group, names)]
    from lightning.core.dates import _local_now
    from lightning.planning import bill_state
    hour = _local_now().hour
    # From lists accounts money is paid from (cash and bank), plus the one this sheet is already for.
    spend = [a for a in _entry_accounts(c) if a.account_type.value in ("CASH", "BANK") or a.id == account.id]
    spend_ids = {a.id for a in spend}
    return {"entry_accounts": [{"id": a.id, "name": a.name} for a in spend],
            "usual_payees": [p for p in c.transactions.usual_payees() if p["account_id"] in spend_ids][:3],
            "usual_accounts": {name: a_id for name, a_id in c.transactions.usual_accounts().items() if a_id in spend_ids},
            "bills_due": len(bill_state.unpaid_bills(c.planning, today(), bill_state.SOON_DAYS)),
            "chips_out": named(c.transactions.usual_capture_categories("out", hour=hour)),
            "chips_in": named(c.transactions.usual_capture_categories("in", hour=hour))}


def present(request, c, context: dict) -> dict:
    return _capture_context(c, context["account"]) if context.get("txn_id") is None else {}
