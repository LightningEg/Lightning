"""Paid themes (8L): worn only with a verified licence, tried by anyone, unlocked with the website's one-time code.

A real Ed25519 key stands in for the store's; the store endpoint is a fake opener. No network, no real keys.
"""
import base64
import json
from io import BytesIO
from urllib.error import HTTPError

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from lightning.ui import entitlements

ACCOUNT = "11111111-1111-4111-8111-111111111111"


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A pinned test key, an empty licence folder, and a signer playing the store (supabase/functions)."""
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    monkeypatch.setenv("LIGHTNING_LICENSE_DIR", str(tmp_path))
    monkeypatch.delenv("LIGHTNING_THEME_REVIEW", raising=False)
    entitlements.store.cache_clear()
    monkeypatch.setattr(entitlements, "store", lambda: {"keys": {"test-1": public}, "redeem_url": "https://store.example/redeem"})

    def sign(items, signer=key):
        payload = json.dumps({"issuer": "lightning-store", "schema_version": 1, "account_id": ACCOUNT,
                              "items": [{"item_id": i, "asset_version": v, "deliveries": []} for i, v in items]})
        return {"algorithm": "Ed25519", "key_id": "test-1", "payload": payload, "signature": b64(signer.sign(payload.encode()))}
    return sign


def answer(envelope=None, status=200):
    def opener(request, timeout):
        assert request.full_url == "https://store.example/redeem" and request.get_method() == "POST" and timeout <= 15
        assert not request.has_header("Origin"), "the store refuses browser origins"
        sent = json.loads(request.data)
        assert set(sent) == {"code", "item_id", "asset_version"}
        if status != 200:
            raise HTTPError(request.full_url, status, "no", {}, BytesIO(b"{}"))
        return BytesIO(json.dumps(envelope).encode())
    return opener


def test_the_bundled_paid_themes_share_the_store_ids():
    assert entitlements.paid_themes() == {"cotton": 1, "dendera": 1, "nile": 1, "papyrus": 1}
    # Dendera's night is the same purchase: it is not a store item of its own and rides on Dendera's licence
    assert [t["id"] for t in entitlements.store_themes()].count("dendera-night") == 0
    shipped = json.loads(entitlements.STORE.read_text())
    assert shipped["redeem_url"].startswith("https://") and shipped["redeem_url"].endswith("/functions/v1/redeem-purchase")


def test_without_a_licence_a_paid_theme_is_not_worn(store, monkeypatch):
    monkeypatch.delenv("LIGHTNING_THEME_REVIEW", raising=False)
    assert entitlements.owned() == frozenset()
    assert not entitlements.wearable("papyrus")
    assert entitlements.wearable("royal-obsidian-gold") and entitlements.wearable("lightning-default")
    from lightning.ui.themes import theme_id
    assert theme_id("papyrus") == "lightning-default"


def test_redeem_verifies_keeps_and_unlocks(store):
    envelope = store([("papyrus", 1)])
    assert entitlements.redeem(" abcd1234-ABCD1234-abcd1234-abcd1234 ", "papyrus", opener=answer(envelope)) == "papyrus"
    assert entitlements.owned() == frozenset({"papyrus"})
    from lightning.ui.themes import theme_id
    assert theme_id("papyrus") == "papyrus"
    # a second unlock keeps the first; the same licence twice is kept once
    entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", "cotton", opener=answer(store([("cotton", 1)])))
    entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", "cotton", opener=answer(store([("cotton", 1)])))
    assert entitlements.owned() == frozenset({"papyrus", "cotton"})
    kept = json.loads(entitlements.licence_file().read_text())["licenses"]
    assert len(kept) == 2
    assert not list(entitlements.licence_file().parent.glob(".licenses-*")), "no temporary file left behind"


def test_a_themes_night_mode_is_worn_with_its_items_licence(store):
    assert not entitlements.wearable("dendera-night") and not entitlements.wearable("dendera")
    entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", "dendera", opener=answer(store([("dendera", 1)])))
    assert entitlements.wearable("dendera") and entitlements.wearable("dendera-night")
    from lightning.ui.themes import theme_id
    assert theme_id("dendera-night") == "dendera-night"


def test_forged_tampered_or_wrong_version_licences_unlock_nothing(store):
    forged = store([("papyrus", 1)], signer=Ed25519PrivateKey.generate())
    with pytest.raises(entitlements.UnlockError, match="did not verify"):
        entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", "papyrus", opener=answer(forged))
    old = store([("papyrus", 7)])
    with pytest.raises(entitlements.UnlockError, match="did not verify"):
        entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", "papyrus", opener=answer(old))
    other = store([("nile", 1)])
    with pytest.raises(entitlements.UnlockError, match="another theme"):
        entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", "papyrus", opener=answer(other))
    assert entitlements.owned() == frozenset()
    # a licence file edited by hand is ignored, not trusted
    good = store([("nile", 1)])
    good["payload"] = good["payload"].replace("nile", "papyrus")
    entitlements.licence_file().write_text(json.dumps({"licenses": [good, {"junk": True}, 5]}))
    assert entitlements.owned() == frozenset()


def test_store_refusals_and_missing_keys_say_what_to_do(store, monkeypatch):
    with pytest.raises(entitlements.UnlockError, match="fresh one"):
        entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", "papyrus", opener=answer(status=400))
    with pytest.raises(entitlements.UnlockError, match="Choose the theme"):
        entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", "royal-obsidian-gold", opener=answer())
    with pytest.raises(entitlements.UnlockError, match="whole code"):
        entitlements.redeem("abc", "papyrus", opener=answer())
    monkeypatch.setattr(entitlements, "store", lambda: {"keys": {}, "redeem_url": "https://store.example/redeem"})
    with pytest.raises(entitlements.UnlockError, match="next Lightning update"):
        entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", "papyrus", opener=answer())


def test_settings_tries_saves_only_owned_and_unlocks(c, store, monkeypatch):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    client = TestClient(create_app(c))
    assert client.post('/settings/theme', data={'theme': 'papyrus'}).status_code == 402, "try it, but not keep it"
    assert c.settings.get('appearance_theme') != 'papyrus'
    page = client.get('/settings').text
    assert 'Unlock a theme you bought' in page and 'action="/settings/theme/unlock"' in page
    assert '<meta name="lightning-owned" content="">' in page
    monkeypatch.setattr(entitlements, "urlopen", answer(store([("papyrus", 1)])))
    done = client.post('/settings/theme/unlock', data={'theme': 'papyrus', 'code': 'abcd1234abcd1234abcd1234abcd1234'}, follow_redirects=False)
    assert done.status_code in (302, 303)
    assert c.settings.get('appearance_theme') == 'papyrus'
    page = client.get('/settings').text
    assert '<meta name="lightning-theme" content="papyrus">' in page
    assert '<meta name="lightning-owned" content="papyrus">' in page
    assert client.post('/settings/theme', data={'theme': 'papyrus'}).status_code == 204
