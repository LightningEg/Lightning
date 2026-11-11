"""The PC Overview's address on a phone is Home (3AY10): the older phone Overview is gone. The phone router answers /
itself; this covers a request that reaches the shared route first (an app built without the phone router)."""
from __future__ import annotations


def present(request, c, context: dict) -> dict:
    from lightning.core.dates import today
    from lightning.ui.phone.screens import home
    return {"screen": home.build(c, today()), "__template__": "phone/home.html"}
