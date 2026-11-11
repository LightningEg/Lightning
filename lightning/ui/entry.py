"""What the Add button may enter into, shared by the PC route and the phone router (3AY18), so the phone layer never
imports the PC routes."""
from __future__ import annotations


def entry_accounts(c) -> list:
    """The accounts a hand-entered transaction can go to: every active one that holds money, not a thing you own."""
    return [a for a in c.accounts.list(active_only=True) if a.account_type.value not in ("PHYSICAL_ASSET", "OTHER_ASSET")]
