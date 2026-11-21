"""The phone inbox shows the questions that can be answered directly on each SMS."""
from lightning.categories.domain import Movement


def present(request, c, context):
    extra = {"sms_counts": c.sms_imports.review_counts()}
    if not context["batches"]:
        return extra
    items = []
    similar = {}
    for batch in context["batches"]:
        for row in c.bank_imports.preview(batch["batch_id"])[1]:
            if row["_status"] == "REVIEW":
                items.append((batch, row))
                if row["_quick_purchase"]:
                    similar.setdefault(row["_sms_category_key"], []).append(row)
    return dict(extra, sms_items=items, similar=similar, payees=c.counterparties.list_active(),
                spending=[(cat.id, c.categories.display_name(cat.id)) for cat in c.categories.pickable(Movement.OUTFLOW)])
