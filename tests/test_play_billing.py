"""Themes sold through Google Play Billing in the Play build (NF-11B3).

The Play build's Settings shows Play's price and Buy, and no website price or link; a purchase Play reports becomes the
store's signed licence through redeem-play, kept exactly like a website code's. The GitHub APK and the PC are
unchanged. A real Ed25519 key stands in for the store's; Play and the store are fakes. No network, no real keys."""
import base64
import json
import re
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Credentials
from lightning.ui import entitlements, play_store

from test_profile_app import create, token

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


class FakePlay:
    def __init__(self, purchases=(), prices=None):
        self.bought, self.list, self.result = [], list(purchases), ""
        self.price = {"papyrus": "EGP 99.99", "dendera": "EGP 149.99", "nile": "EGP 79.99", "cotton": "EGP 79.99"} \
            if prices is None else prices

    def prices(self, ids):
        return {i: self.price[i] for i in ids if i in self.price}

    def buy(self, product, profile_id):
        self.bought.append((product, profile_id))
        return True

    def purchases(self):
        return self.list

    def take_result(self):
        result, self.result = self.result, ""
        return result


@pytest.fixture
def store(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    monkeypatch.setenv("LIGHTNING_LICENSE_DIR", str(tmp_path))
    monkeypatch.delenv("LIGHTNING_THEME_REVIEW", raising=False)
    monkeypatch.setattr(entitlements, "store", lambda: {"keys": {"test-1": public}, "redeem_url": "https://store.example/redeem",
                                                        "play_redeem_url": "https://store.example/redeem-play"})
    monkeypatch.setattr(entitlements, "_PROFILE", lambda: PROFILE)

    def sign(item, profile=PROFILE):
        payload = json.dumps({"issuer": "lightning-store", "schema_version": 1, "account_id": "11111111-1111-4111-8111-111111111111",
                              "profile_id": profile, "items": [{"item_id": item, "asset_version": 1, "deliveries": []}]})
        return {"algorithm": "Ed25519", "key_id": "test-1", "payload": payload,
                "signature": base64.urlsafe_b64encode(key.sign(payload.encode())).rstrip(b"=").decode()}
    return sign


def play_answer(envelope=None, status=200, seen=None):
    def opener(request, timeout):
        assert request.full_url == "https://store.example/redeem-play" and request.get_method() == "POST"
        sent = json.loads(request.data)
        assert set(sent) == {"package_name", "product_id", "purchase_token", "items", "profile_id"}
        assert sent["package_name"] == "org.lightning.app" and sent["profile_id"] == PROFILE
        if seen is not None:
            seen.append(sent)
        if status != 200:
            raise HTTPError(request.full_url, status, "no", {}, BytesIO(b"{}"))
        return BytesIO(json.dumps(envelope).encode())
    return opener


def test_the_shipped_store_names_the_play_function():
    shipped = json.loads(entitlements.STORE.read_text())
    assert shipped["play_redeem_url"].startswith("https://") and shipped["play_redeem_url"].endswith("/functions/v1/redeem-play")


def test_a_play_purchase_becomes_the_same_signed_licence(store):
    seen = []
    assert entitlements.redeem_play("papyrus", "token-abcdefghijkl", opener=play_answer(store("papyrus"), seen=seen)) == "papyrus"
    assert entitlements.owned() == frozenset({"papyrus"}) and seen[0]["purchase_token"] == "token-abcdefghijkl"


@pytest.mark.parametrize("status,words", [(410, "refunded"), (409, "another profile"), (402, "not finished"),
                                          (400, "does not know")])
def test_the_store_refusals_are_said_plainly(store, status, words):
    with pytest.raises(entitlements.UnlockError, match=words):
        entitlements.redeem_play("papyrus", "token-abcdefghijkl", opener=play_answer(status=status))
    assert entitlements.owned() == frozenset()


def test_a_licence_for_another_profile_is_refused(store):
    with pytest.raises(entitlements.UnlockError, match="did not verify"):
        entitlements.redeem_play("papyrus", "token-abcdefghijkl",
                                 opener=play_answer(store("papyrus", profile="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")))


def test_settle_unlocks_paid_purchases_once_and_waits_for_pending(store, monkeypatch):
    calls = []
    monkeypatch.setattr(play_store, "redeem_play", lambda product, token: calls.append(product) or entitlements.redeem_play(
        product, token, opener=play_answer(store(product))))
    play = FakePlay([{"product": "papyrus", "token": "t-papyrus-123", "state": "purchased"},
                     {"product": "nile", "token": "t-nile-12345", "state": "pending"},
                     {"product": "not-a-theme", "token": "t-other-1234", "state": "purchased"}])
    unlocked, pending, messages = play_store.settle(play)
    assert unlocked == ["papyrus"] and pending == ["nile"] and messages == [] and calls == ["papyrus"]
    assert play_store.settle(play)[0] == [] and calls == ["papyrus"], "an owned theme is not redeemed again"


def _phone(tmp_path, billing):
    cfg = Credentials("http://127.0.0.1:9866")
    app = profile_app(cfg, tmp_path / "docs", devices=Devices(tmp_path / "app", port=0), phone=True, billing=billing)
    browser = TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin})
    browser.__enter__()
    browser.get("/__launch", params={"code": cfg.launch_code})
    create(browser)
    return browser


def test_the_play_build_shows_plays_price_and_buy_and_no_website(tmp_path, monkeypatch):
    play = FakePlay()
    browser = _phone(tmp_path, play)
    try:
        page = browser.get("/settings").text
        assert "EGP 99.99" in page and 'action="/settings/theme/buy"' in page
        assert "marketplace" not in page and "See prices" not in page and "account page" not in page
        outside = {link for link in re.findall(r'href="(https://[^"#?]+)', page)}
        assert outside <= {"https://lightningeg.com/privacy.html"}, f"no website link but the privacy notice: {outside}"
        assert "Unlock a theme you bought" in page, "codes still unlock"
        browser.post("/settings/theme/buy", data={"theme": "papyrus", "__session": token(page, "__session")})
        assert len(play.bought) == 1 and play.bought[0][0] == "papyrus"
        assert re.fullmatch(r"[0-9a-f-]{36}", play.bought[0][1]), "the purchase carries this profile's id"
    finally:
        browser.__exit__(None, None, None)


def test_the_github_apk_and_the_pc_keep_the_website(tmp_path):
    browser = _phone(tmp_path, None)
    try:
        page = browser.get("/settings").text
        assert "See prices" in page and "lightningeg.com/marketplace" in page and "/settings/theme/buy" not in page
    finally:
        browser.__exit__(None, None, None)


def test_only_the_play_flavour_carries_billing():
    gradle = (ROOT / "android/app/build.gradle.kts").read_text()
    assert '"playImplementation"("com.android.billingclient:billing:' in gradle
    assert 'create("github") { dimension = "store"; isDefault = true }' in gradle
    assert (ROOT / "android/app/src/play/java/org/lightning/app/BillingBridge.java").exists()
    assert not (ROOT / "android/app/src/main/java/org/lightning/app/BillingBridge.java").exists()
    assert "com.android.vending.BILLING" not in (ROOT / "packaging/android-permissions.txt").read_text().split("#")[0]
    bridge = (ROOT / "android/app/src/play/java/org/lightning/app/BillingBridge.java").read_text()
    assert ".setObfuscatedProfileId(profileId)" in bridge
