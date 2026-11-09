"""Themes sold through Google Play Billing in the Play build (NF-11B3).

The Play build hands `profile_app(billing=…)` an object with this shape (`AndroidBilling` in the Android app's
lightning_android.py, over `BillingBridge.java`); the GitHub APK and the PC hand None and sell on the website. Play
owns the money and the price; the store's redeem-play function turns a purchase into the same signed licence a website
code gives (`entitlements.redeem_play`), so wearing a theme works exactly as before. Nothing here touches money in
the ledger.
"""
from __future__ import annotations

from typing import Protocol

from .entitlements import UnlockError, owned, paid_themes, redeem_play


class PlayBilling(Protocol):
    def prices(self, ids) -> dict[str, str]: ...          # Play's formatted price per product id (theme id)
    def buy(self, product: str, profile_id: str) -> bool: ...  # opens Play's sheet; False when Play cannot now
    def purchases(self) -> list[dict]: ...                # [{"product", "token", "state": purchased|pending|unknown}]
    def take_result(self) -> str: ...                     # how the last sheet ended: ok, cancelled, error or ""


def settle(billing: PlayBilling) -> tuple[list[str], list[str], list[str]]:
    """Unlock every paid purchase Play reports that this profile does not wear yet (a new purchase, another device, a
    reinstall). Returns (unlocked theme ids, pending theme ids, messages for the person)."""
    supported, mine = paid_themes(), owned()
    unlocked, pending, messages = [], [], []
    try:
        purchases = billing.purchases()
    except Exception:  # noqa: BLE001 - Play not answering: nothing to settle now, Settings still opens
        return unlocked, pending, messages
    for purchase in purchases:
        product = purchase.get("product", "")
        if product not in supported or product in mine or product in unlocked:
            continue
        if purchase.get("state") == "pending":
            pending.append(product)
            continue
        if purchase.get("state") != "purchased":
            continue
        try:
            unlocked.append(redeem_play(product, purchase.get("token", "")))
        except UnlockError as exc:
            messages.append(str(exc))
    return unlocked, pending, messages


def offers(billing: PlayBilling, themes: list[dict]) -> dict[str, str]:
    """Play's price for each paid theme not owned yet; a theme Play has no price for is not offered."""
    wanted = [t["id"] for t in themes if not t["owned"]]
    if not wanted:
        return {}
    try:
        return {k: v for k, v in billing.prices(wanted).items() if k in wanted and v}
    except Exception:  # noqa: BLE001 - no prices: Settings says the store is not answering
        return {}
