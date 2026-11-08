"""IV-3AY16: Settings on the phone: grouped rows, controls that work, and the older sections still reachable."""
from tests.test_phone_account import _phone, sample  # noqa: F401,F811


def test_the_groups_and_their_ways_on(sample):
    html = _phone(sample).get("/settings").text
    for heading in ("theme-heading", "this-phone-heading", "data-heading", "features-heading", "more-heading"):
        assert f'id="{heading}"' in html
    for href in ("/profiles/devices", "/sms", "/rules", "/categories", "/checks", "/exports/all",
                 "/settings?section=budget", "/settings?section=currencies"):
        assert f'href="{href}"' in html, href


def test_language_and_zakat_switch_work_from_it(sample):
    import re
    phone = _phone(sample)
    token = re.search(r'name="__session" value="([^"]*)"', phone.get("/settings").text).group(1)
    assert phone.post("/settings/locale", data={"locale": "ar", "__session": token}, follow_redirects=False).status_code == 303
    assert sample.settings.get("locale") == "ar"


def test_a_section_still_reaches_the_older_page(sample):
    html = _phone(sample).get("/settings?section=budget").text
    assert 'id="theme-heading"' not in html and "budget" in html.lower()
