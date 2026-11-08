"""Settings on the phone (IV-3AY16, report: *Settings*): grouped rows, each a control or a way to the page that holds the
rest. Services hold the values; this module only picks what the phone shows."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SettingsScreen:
    locale: str
    has_backup: bool          # a copy to save exists
    zakat_on: bool
    base: str
    fingerprint: str          # "", "on" or "off": the row only exists where the phone can unlock with a fingerprint
    secure_profiles: bool     # Start fresh opens a new profile instead of an empty database


def build(c, fingerprint: str = "", secure_profiles: bool = False) -> SettingsScreen:
    locale = c.settings.get("locale")
    return SettingsScreen(locale=locale if locale in ("en", "ar") else "en", has_backup=bool(c.backup_files()),
                          zakat_on=c.zakat.enabled(), base=c.base_currency, fingerprint=fingerprint,
                          secure_profiles=secure_profiles)
