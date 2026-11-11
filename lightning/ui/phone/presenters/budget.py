"""The PC Budget's address on a phone is the flexible Budget (3AY9): the older phone Budget is gone. The phone router
answers /budget itself; this covers a request that reaches the shared route first (an app built without the router)."""
from __future__ import annotations


def present(request, c, context: dict) -> dict:
    from lightning.core.dates import today
    from lightning.ui.phone.screens import budget
    return {"screen": budget.build(c, today(), request.query_params.get("month", "")),
            "__template__": "phone/budget_flexible.html"}
