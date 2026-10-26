"""Paid themes unlocked on this computer: signed store licences, verified offline against the pinned store keys.

A licence lives beside the profiles (Documents/Lightning/cosmetics/licenses.json), never inside a profile or its
backups: it belongs to the person's store account, not to a ledger. Losing the file loses nothing; the owner of the
purchase gets a fresh one-time code on the website. Nothing here touches money, calculations or roles.
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


def owned() -> frozenset[str]:
    """Paid theme ids with a valid licence here. An invalid or unsupported licence unlocks nothing and harms nothing."""
    keys, supported, ids, check = store()["keys"], paid_themes(), set(), _verifier()
    if check is None:
        return frozenset()
    InvalidCosmeticLicense, verify_license = check
    for envelope in _envelopes():
        try:
            ids.update(name for name, _ in verify_license(envelope, keys, supported).items)
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


def redeem(code: str, theme: str, *, opener=None) -> str:
    """Exchange a one-time website code for a signed licence, verify it, keep it. Returns the theme unlocked."""
    supported, conf, check = paid_themes(), store(), _verifier()
    if check is None:
        raise UnlockError("Unlocking opens with the next Lightning update.")
    InvalidCosmeticLicense, verify_license = check
    if theme not in supported:
        raise UnlockError("Choose the theme you bought.")
    code = "".join(code.split()).upper()
    if not (8 <= len(code) <= 64):
        raise UnlockError("Paste the whole code from your account page.")
    if not conf["keys"] or not conf["redeem_url"].startswith("https://"):
        raise UnlockError("Unlocking opens with the next Lightning update.")
    body = json.dumps({"code": code, "item_id": theme, "asset_version": supported[theme]}).encode()
    request = Request(conf["redeem_url"], data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        with (opener or urlopen)(request, timeout=15) as response:
            envelope = json.loads(response.read(200_000))
    except HTTPError as exc:
        raise UnlockError("That code is used, expired or for another theme. Get a fresh one from your account page.") from exc
    except (URLError, OSError, ValueError) as exc:
        raise UnlockError("Could not reach the Lightning store. Check the connection and try again.") from exc
    try:
        names = {name for name, _ in verify_license(envelope, conf["keys"], supported).items}
    except InvalidCosmeticLicense as exc:
        raise UnlockError("The store's answer did not verify. Update Lightning and try again.") from exc
    if theme not in names:
        raise UnlockError("That code is for another theme.")
    _save(envelope)
    return theme
