"""Paid themes unlocked on this computer: signed store licences, verified offline against the pinned store keys.

A redeemed licence is kept in two places: beside the profiles (Documents/Lightning/cosmetics/licenses.json, the
instant cache on this computer) and in the open profile's own settings under `store_licence.<item>`, which sync to
every device of the profile. So one code unlocks a theme once per profile: the profile's other devices verify the
synced envelope themselves and need no code. Losing the file loses nothing. Nothing here touches money, calculations
or roles.

One purchase unlocks a theme for one profile: the store binds each licence to the profile's own stable id (the same on
every device that profile lives on), so a licence is worn only while that profile is open. The same computer may hold
licences for several profiles; each wears only its own. Another profile needs another seat from the website.
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

STORE = Path(__file__).resolve().parents[1] / "security" / "store_keys.json"
REGISTRY = Path(__file__).parent / "static" / "themes.generated.json"


class UnlockError(ValueError):
    """A message the person can act on."""


@lru_cache(maxsize=1)
def store() -> dict:
    data = json.loads(STORE.read_text())
    keys = {kid: base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)) for kid, raw in data.get("keys", {}).items()}
    return {"keys": keys, "redeem_url": data.get("redeem_url", "")}


@lru_cache(maxsize=1)
def paid_themes() -> dict[str, int]:
    """Each paid store item this app version carries, at the exact version a licence must name. A theme's other mode
    (Dendera's night) names its item and rides on that item's licence: one purchase, both modes."""
    return {t.get("item", t["id"]): t["version"] for t in json.loads(REGISTRY.read_text()) if t.get("paid")}


def store_themes() -> list[dict]:
    """The paid themes for Settings, in registry order: id, name and whether this computer holds its licence."""
    mine = owned()
    return [{"id": t["id"], "name": t["name"], "owned": t["id"] in mine}
            for t in json.loads(REGISTRY.read_text()) if t.get("paid") and "item" not in t]


_FOLDER: Path | None = None
_PROFILE = None  # a callable giving the open profile's id, or None when no profile is open


_SETTINGS = None  # a callable giving the open profile's settings store, or None when no profile is open
LICENCE_KEY = "store_licence."  # one profile setting per item: the signed envelope as compact JSON (well under 4000 chars)


def use_profile(provider, settings=None) -> None:
    """The runtime names how to read the open profile's id and settings (lightning/runtime/session.py)."""
    global _PROFILE, _SETTINGS
    _PROFILE = provider
    _SETTINGS = settings


def _profile_settings():
    try:
        return _SETTINGS() if _SETTINGS else None
    except Exception:  # a profile that cannot give its settings shares nothing
        return None


def profile_id() -> str | None:
    try:
        return _PROFILE() if _PROFILE else None
    except Exception:  # a profile that cannot say who it is simply owns nothing paid
        return None


def use_folder(folder: Path) -> None:
    """The runtime names the folder beside the profiles (Documents/Lightning/cosmetics) when it opens the root."""
    global _FOLDER
    _FOLDER = Path(folder)


def licence_file() -> Path:
    folder = os.environ.get("LIGHTNING_LICENSE_DIR")
    if folder:
        return Path(folder) / "licenses.json"
    if _FOLDER is not None:
        return _FOLDER / "licenses.json"
    from lightning.bootstrap import DEFAULT_DATA_DIR  # the single-database and sample modes
    return DEFAULT_DATA_DIR / "cosmetics" / "licenses.json"


def _verifier():
    """The licence check needs cryptography, which a plain install may lack: then nothing paid unlocks."""
    try:
        from lightning.security.cosmetic_license import InvalidCosmeticLicense, verify_license
    except ImportError:
        return None
    return InvalidCosmeticLicense, verify_license


def _envelopes() -> list[dict]:
    try:
        data = json.loads(licence_file().read_text())
    except (OSError, ValueError):
        return []
    return [e for e in data.get("licenses", []) if isinstance(e, dict)] if isinstance(data, dict) else []


def _synced_envelopes() -> list[dict]:
    """The envelopes the profile's other devices (or this one, earlier) stored in the synced settings."""
    settings, found = _profile_settings(), []
    if settings is None:
        return found
    for item in paid_themes():
        try:
            envelope = json.loads(settings.get(LICENCE_KEY + item) or "null")
        except Exception:  # unreadable or missing setting: ignored like any invalid licence
            continue
        if isinstance(envelope, dict):
            found.append(envelope)
    return found


def owned() -> frozenset[str]:
    """Paid theme ids the open profile has a valid licence for. A licence for another profile, an invalid one or an
    unsupported one unlocks nothing and harms nothing."""
    keys, supported, ids, check, profile = store()["keys"], paid_themes(), set(), _verifier(), profile_id()
    if check is None or profile is None:
        return frozenset()
    InvalidCosmeticLicense, verify_license = check
    for envelope in _envelopes() + _synced_envelopes():
        try:
            ids.update(name for name, _ in verify_license(envelope, keys, supported, expected_profile=profile).items)
        except InvalidCosmeticLicense:
            continue
    return frozenset(ids)


def wearable(theme: str) -> bool:
    # LIGHTNING_THEME_REVIEW=1 is for maintainers reviewing themes before release (tools/theme_shots.py); the app
    # is open source, so this is a convenience, not a lock. Ownership is the store's signed licence.
    item = next((t.get("item", t["id"]) for t in json.loads(REGISTRY.read_text()) if t["id"] == theme), theme)
    return item not in paid_themes() or os.environ.get("LIGHTNING_THEME_REVIEW") == "1" or item in owned()


def _save(envelope: dict) -> None:
    path = licence_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = [e for e in _envelopes() if e.get("payload") != envelope.get("payload")] + [envelope]
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".licenses-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"licenses": kept}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)  # all or nothing: a crash leaves the old file
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _share(item: str, envelope: dict) -> None:
    """Put the envelope in the profile's synced settings so its other devices unlock by themselves."""
    settings = _profile_settings()
    if settings is None:
        return
    try:
        settings.set(LICENCE_KEY + item, json.dumps(envelope, separators=(",", ":")))
    except Exception:  # PendingOnHome (applies once the home confirms) or a read-only refusal: the file still unlocks here
        pass


def redeem(code: str, *, opener=None) -> str:
    """Exchange a one-time website code for the signed licence of the theme it was bought for, verify it, keep it on this
    computer and in the profile's settings. Returns the theme id the licence names."""
    supported, conf, check, profile = paid_themes(), store(), _verifier(), profile_id()
    if check is None:
        raise UnlockError("Unlocking opens with the next Lightning update.")
    if profile is None:
        raise UnlockError("Open the profile you want to unlock this on, then try again.")
    InvalidCosmeticLicense, verify_license = check
    code = "".join(code.split()).upper()
    if not (8 <= len(code) <= 64):
        raise UnlockError("Paste the whole code from your account page.")
    if not conf["keys"] or not conf["redeem_url"].startswith("https://"):
        raise UnlockError("Unlocking opens with the next Lightning update.")
    items = [{"item_id": name, "asset_version": version} for name, version in supported.items()]
    body = json.dumps({"code": code, "items": items, "profile_id": profile}).encode()
    request = Request(conf["redeem_url"], data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        with (opener or urlopen)(request, timeout=15) as response:
            envelope = json.loads(response.read(200_000))
    except HTTPError as exc:
        if exc.code == 409:  # the store says every seat for this theme is taken by other profiles
            raise UnlockError("Every profile seat for this theme is used. Add another profile on your account page: "
                              "it costs a quarter of the price.") from exc
        raise UnlockError("That code is used or expired. Get a fresh one from your account page.") from exc
    except (URLError, OSError, ValueError) as exc:
        raise UnlockError("Could not reach the Lightning store. Check the connection and try again.") from exc
    try:
        names = [name for name, _ in verify_license(envelope, conf["keys"], supported, expected_profile=profile).items]
    except InvalidCosmeticLicense as exc:
        if str(exc).startswith("Update Lightning: unsupported"):  # signed, but names an item this app does not carry
            raise UnlockError("Update Lightning to wear this theme.") from exc
        raise UnlockError("The store's answer did not verify. Update Lightning and try again.") from exc
    names = [n for n in names if n in supported]
    if not names:
        raise UnlockError("Update Lightning to wear this theme.")
    _save(envelope)
    for name in names:
        _share(name, envelope)
    return names[0]
