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
PROFILE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER_PROFILE = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


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

    monkeypatch.setattr(entitlements, "_PROFILE", lambda: PROFILE)  # the open profile; the runtime supplies it

    def sign(items, signer=key, profile=PROFILE):
        payload = json.dumps({"issuer": "lightning-store", "schema_version": 1, "account_id": ACCOUNT, "profile_id": profile,
                              "items": [{"item_id": i, "asset_version": v, "deliveries": []} for i, v in items]})
        return {"algorithm": "Ed25519", "key_id": "test-1", "payload": payload, "signature": b64(signer.sign(payload.encode()))}
    return sign


def answer(envelope=None, status=200):
    def opener(request, timeout):
        assert request.full_url == "https://store.example/redeem" and request.get_method() == "POST" and timeout <= 15
        assert not request.has_header("Origin"), "the store refuses browser origins"
        sent = json.loads(request.data)
        assert set(sent) == {"code", "items", "profile_id"}
        assert sent["items"] == [{"item_id": n, "asset_version": v} for n, v in entitlements.paid_themes().items()]
        assert sent["profile_id"] == PROFILE, "the code claims a seat for the open profile"
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
    assert entitlements.redeem(" abcd1234-ABCD1234-abcd1234-abcd1234 ", opener=answer(envelope)) == "papyrus"
    assert entitlements.owned() == frozenset({"papyrus"})
    from lightning.ui.themes import theme_id
    assert theme_id("papyrus") == "papyrus"
    # a second unlock keeps the first; the same licence twice is kept once
    entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", opener=answer(store([("cotton", 1)])))
    entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", opener=answer(store([("cotton", 1)])))
    assert entitlements.owned() == frozenset({"papyrus", "cotton"})
    kept = json.loads(entitlements.licence_file().read_text())["licenses"]
    assert len(kept) == 2
    assert not list(entitlements.licence_file().parent.glob(".licenses-*")), "no temporary file left behind"


def test_a_themes_night_mode_is_worn_with_its_items_licence(store):
    assert not entitlements.wearable("dendera-night") and not entitlements.wearable("dendera")
    entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", opener=answer(store([("dendera", 1)])))
    assert entitlements.wearable("dendera") and entitlements.wearable("dendera-night")
    from lightning.ui.themes import theme_id
    assert theme_id("dendera-night") == "dendera-night"


def test_forged_tampered_or_wrong_version_licences_unlock_nothing(store):
    forged = store([("papyrus", 1)], signer=Ed25519PrivateKey.generate())
    with pytest.raises(entitlements.UnlockError, match="did not verify"):
        entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", opener=answer(forged))
    old = store([("papyrus", 7)])
    with pytest.raises(entitlements.UnlockError, match="Update Lightning"):
        entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", opener=answer(old))
    other = store([("nile", 1)])
    entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", opener=answer(other))  # a valid licence for another theme
    assert entitlements.owned() == frozenset({"nile"})
    entitlements.licence_file().unlink()
    assert entitlements.owned() == frozenset()
    # a licence file edited by hand is ignored, not trusted
    good = store([("nile", 1)])
    good["payload"] = good["payload"].replace("nile", "papyrus")
    entitlements.licence_file().write_text(json.dumps({"licenses": [good, {"junk": True}, 5]}))
    assert entitlements.owned() == frozenset()


def test_a_licence_for_another_profile_unlocks_nothing_here(store, monkeypatch):
    """One purchase, one profile: the store binds the licence to the profile id; other profiles on this computer ignore it."""
    entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", opener=answer(store([("papyrus", 1)])))
    assert entitlements.owned() == frozenset({"papyrus"})
    monkeypatch.setattr(entitlements, "_PROFILE", lambda: OTHER_PROFILE)
    assert entitlements.owned() == frozenset() and not entitlements.wearable("papyrus")
    monkeypatch.setattr(entitlements, "_PROFILE", lambda: PROFILE)  # back on the first profile, on any device of it
    assert entitlements.owned() == frozenset({"papyrus"})
    # the store answering for a different profile than the one that asked is refused, not saved
    entitlements.licence_file().unlink()
    with pytest.raises(entitlements.UnlockError, match="did not verify"):
        entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", opener=answer(store([("papyrus", 1)], profile=OTHER_PROFILE)))
    assert not entitlements.licence_file().exists()
    # two profiles on one computer each keep their own licence in the one file
    monkeypatch.setattr(entitlements, "_PROFILE", lambda: OTHER_PROFILE)
    monkeypatch.setattr(entitlements, "_PROFILE", lambda: PROFILE)
    entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", opener=answer(store([("nile", 1)])))
    monkeypatch.setattr(entitlements, "_PROFILE", lambda: OTHER_PROFILE)
    assert entitlements.owned() == frozenset()


def test_no_open_profile_owns_nothing_and_cannot_unlock(store, monkeypatch):
    entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", opener=answer(store([("papyrus", 1)])))
    monkeypatch.setattr(entitlements, "_PROFILE", None)
    assert entitlements.owned() == frozenset() and entitlements.profile_id() is None
    with pytest.raises(entitlements.UnlockError, match="Open the profile"):
        entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", opener=answer(store([("papyrus", 1)])))
    monkeypatch.setattr(entitlements, "_PROFILE", lambda: 1 / 0)  # a profile that cannot say who it is owns nothing
    assert entitlements.owned() == frozenset()


def test_every_seat_taken_says_what_to_do(store):
    with pytest.raises(entitlements.UnlockError, match="Every profile seat.*quarter of the price"):
        entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", opener=answer(status=409))
    assert not entitlements.licence_file().exists()


def test_store_refusals_and_missing_keys_say_what_to_do(store, monkeypatch):
    with pytest.raises(entitlements.UnlockError, match="used or expired.*fresh one"):
        entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", opener=answer(status=400))
    with pytest.raises(entitlements.UnlockError, match="whole code"):
        entitlements.redeem("abc", opener=answer())
    monkeypatch.setattr(entitlements, "store", lambda: {"keys": {}, "redeem_url": "https://store.example/redeem"})
    with pytest.raises(entitlements.UnlockError, match="next Lightning update"):
        entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", opener=answer())


def test_settings_tries_saves_only_owned_and_unlocks(c, store, monkeypatch):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    client = TestClient(create_app(c))
    assert client.post('/settings/theme', data={'theme': 'papyrus'}).status_code == 402, "try it, but not keep it"
    assert c.settings.get('appearance_theme') != 'papyrus'
    page = client.get('/settings').text
    assert 'Unlock a theme you bought' in page and 'action="/settings/theme/unlock"' in page
    assert '<meta name="lightning-owned" content="">' in page
    assert 'unlock-theme' not in page and 'data-theme-prices' in page
    monkeypatch.setattr(entitlements, "urlopen", answer(store([("papyrus", 1)])))
    done = client.post('/settings/theme/unlock', data={'code': 'abcd1234abcd1234abcd1234abcd1234'}, follow_redirects=False)
    assert done.status_code in (302, 303)
    assert c.settings.get('appearance_theme') == 'papyrus'
    page = client.get('/settings').text
    assert '<meta name="lightning-theme" content="papyrus">' in page
    assert '<meta name="lightning-owned" content="papyrus">' in page
    assert client.post('/settings/theme', data={'theme': 'papyrus'}).status_code == 204


class FakeSettings:
    """The open profile's synced settings: what ProfileSession hands entitlements."""
    def __init__(self, error=None):
        self.data, self.error = {}, error

    def get(self, key):  # the same signature as lightning.database.settings.SettingsStore.get
        return self.data.get(key, "")

    def set(self, key, value):
        if self.error:
            raise self.error
        assert len(key) <= 200 and len(value) <= 4000
        self.data[key] = value


def test_redeem_shares_the_licence_in_the_profile_settings(c, store, monkeypatch):
    monkeypatch.setattr(entitlements, "_SETTINGS", lambda: c.settings)  # the real store, as ProfileSession hands it
    envelope = store([("papyrus", 1)])
    entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", opener=answer(envelope))
    assert json.loads(c.settings.get("store_licence.papyrus")) == envelope


def test_another_device_of_the_profile_unlocks_from_the_synced_setting(c, store, monkeypatch, tmp_path):
    c.settings.set("store_licence.nile", json.dumps(store([("nile", 1)])))  # arrived from the profile's other device
    monkeypatch.setenv("LIGHTNING_LICENSE_DIR", str(tmp_path / "fresh-device"))  # no licence file here
    monkeypatch.setattr(entitlements, "_SETTINGS", lambda: c.settings)
    assert entitlements.owned() == frozenset({"nile"}) and entitlements.wearable("nile")


def test_a_synced_licence_for_another_profile_or_tampered_unlocks_nothing(store, monkeypatch):
    settings = FakeSettings()
    monkeypatch.setattr(entitlements, "_SETTINGS", lambda: settings)
    settings.data["store_licence.nile"] = json.dumps(store([("nile", 1)], profile=OTHER_PROFILE))
    assert entitlements.owned() == frozenset()
    tampered = store([("nile", 1)])
    tampered["payload"] = tampered["payload"].replace("nile", "papyrus")
    settings.data["store_licence.papyrus"] = json.dumps(tampered)
    settings.data["store_licence.cotton"] = "not json"
    assert entitlements.owned() == frozenset()


def test_sharing_that_waits_for_the_home_does_not_fail_the_unlock(store, monkeypatch):
    from lightning.sync.journal.proxy import PendingOnHome
    monkeypatch.setattr(entitlements, "_SETTINGS", lambda: FakeSettings(PendingOnHome("later")))
    assert entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", opener=answer(store([("papyrus", 1)]))) == "papyrus"
    assert entitlements.owned() == frozenset({"papyrus"})


def test_a_licence_for_an_item_this_app_does_not_carry_says_update(store):
    with pytest.raises(entitlements.UnlockError, match="Update Lightning"):
        entitlements.redeem("abcd1234abcd1234abcd1234abcd1234", opener=answer(store([("future-theme", 1)])))
    assert not entitlements.licence_file().exists()


def test_store_keygen_makes_a_key_the_app_pins_and_never_overwrites(tmp_path, capsys):
    import base64
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from tools.store_keygen import main, make_key
    jwk, public = make_key("k1")
    pad = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    key = Ed25519PrivateKey.from_private_bytes(pad(jwk["d"]))
    key.public_key().verify(key.sign(b"x"), b"x")
    assert pad(public) == pad(jwk["x"]) and len(pad(public)) == 32
    out = tmp_path / "private.json"
    assert main([str(out), "--id", "k1"]) == 0 and json.loads(out.read_text())["d"]
    assert json.loads(out.read_text())["d"] not in capsys.readouterr().out
    assert main([str(out)]) == 1
