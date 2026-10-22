"""Profile settings: every key is profile-wide and synchronized."""
from .spec import FLAG, LONG, MONTH, TEXT, Command, choice, optional

TABLES = ("settings",)
COMMANDS = {
    "settings.set": Command("settings.set", dict(key=TEXT, value=LONG), target=("settings", ("key",))),
    "set_profile_currency": Command("set_profile_currency", dict(code=TEXT)),
    # Services whose whole write is a few settings keys: the financial-health limits, the raise offer, zakat's switch
    # and dismissing an unread bank message.
    "health.set_limit": Command("health.set_limit", dict(key=TEXT, raw=TEXT, no_limit=FLAG, alert_raw=optional(TEXT))),
    "health.restore_limit": Command("health.restore_limit", dict(key=TEXT)),
    "health.take_raise": Command("health.take_raise", dict(choice=choice("plan", "save", "keep"), month=optional(MONTH))),
    "zakat.set_enabled": Command("zakat.set_enabled", dict(on=FLAG)),
    "sms_imports.dismiss": Command("sms_imports.dismiss", dict(message_id=TEXT)),
}


def refresh(c):
    """A replica applied settings rows: services that cache the profile currency follow."""
    base = c.settings.base_currency
    for service in (c.assets, c.accounts, c.transactions, c.reporting):
        service.base_currency = base
    c.reporting.valuer.base = base
    c.fx.profile_currency = base
