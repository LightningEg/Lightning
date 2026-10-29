"""2F: on the phone a download goes to the app's "Save to" screen and the page comes back; on a PC, unchanged."""
import re
from contextlib import contextmanager

from fastapi.testclient import TestClient

from lightning.runtime.app import profile_app
from lightning.runtime.http import Credentials
from lightning.runtime.phone_files import attachment_name

PASSWORD = "a correct long passphrase"
SECRET = {"question": "What was the name of your first school?", "answer": "El Orman"}


class Saver:
    def __init__(self, accept=True):
        self.offers, self.accept = [], accept

    def offer(self, name, media_type, data):
        self.offers.append((name, media_type, data))
        return self.accept


def header(response, name):
    return dict((k.decode().lower(), v.decode()) for k, v in response.headers.raw).get(name, "")


def token(text, name):
    return re.search(r'name="' + name + r'" value="([^"]+)"', text).group(1)


@contextmanager
def opened(tmp_path, *, phone=True, saver=None):
    """A new, unlocked dummy profile."""
    cfg = Credentials("http://127.0.0.1:9872")
    app = profile_app(cfg, tmp_path / "Documents" / "Lightning", phone=phone, files=saver)
    with TestClient(app, base_url=cfg.origin, headers={"Origin": cfg.origin}) as browser:
        browser.get("/__launch", params={"code": cfg.launch_code})
        yield _created(browser)


def _created(browser):
    page = browser.post("/profiles/new", data={"csrf": token(browser.get("/profiles/new").text, "csrf"), "name": "Home",
                                               "currency": "EGP", "password": PASSWORD, "confirm": PASSWORD, **SECRET})
    recovery = re.search(r'aria-label="Recovery key">([0-9-]+)<', page.text).group(1)
    browser.post("/profiles/confirm", data={"csrf": token(page.text, "csrf"), "recovery": recovery})
    return browser


def test_a_phone_download_is_offered_for_saving_and_the_page_comes_back(tmp_path):
    saver = Saver()
    with opened(tmp_path, saver=saver) as browser:
        session = token(browser.get("/settings").text, "__session")
        answer = browser.get("/exports/import/template", headers={"Referer": "http://127.0.0.1:9872/settings?tab=data&msg=old"},
                             follow_redirects=False)
        assert answer.status_code == 303 and header(answer, "location").startswith("/settings?tab=data&msg=Choose")
        name, media, data = saver.offers[-1]
        assert name.endswith(".xlsx") or name.endswith(".csv")
        assert data and media and "attachment" not in header(answer, "content-disposition")
        # A page's own fetch (the AI workbook) gets an empty answer that names the file.
        fetched = browser.post("/settings/ai-analysis", data={"__session": session, "period": "ytd"},
                               headers={"X-Requested-With": "fetch"})
        assert fetched.status_code == 204 and header(fetched, "x-lightning-offered").endswith(".xlsx")
        assert saver.offers[-1][0].endswith(".xlsx") and saver.offers[-1][2][:2] == b"PK"
        # An ordinary page is not touched.
        assert browser.get("/settings").status_code == 200 and len(saver.offers) == 2


def test_when_the_app_cannot_take_it_the_file_still_arrives(tmp_path):
    saver = Saver(accept=False)
    with opened(tmp_path, saver=saver) as browser:
        answer = browser.get("/exports/import/template")
        assert answer.status_code == 200 and "attachment" in header(answer, "content-disposition") and answer.content
        assert len(saver.offers) == 1


def test_a_pc_download_is_unchanged(tmp_path):
    saver = Saver()
    with opened(tmp_path, phone=False, saver=saver) as browser:
        answer = browser.get("/exports/import/template")
        assert answer.status_code == 200 and "attachment" in header(answer, "content-disposition")
        assert saver.offers == []


def test_attachment_names_are_safe():
    assert attachment_name('attachment; filename="lightning-2026.csv"') == "lightning-2026.csv"
    assert attachment_name('attachment; filename="../../x/y.csv"') == "..-..-x-y.csv"
    assert attachment_name("attachment") == "lightning-file"
    assert attachment_name('inline; filename="a.pdf"') is None and attachment_name("") is None


def test_the_android_adapter_hands_over_a_private_file_and_cleans_up(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "android" / "app" / "src" / "main" / "python"))
    sys.modules.pop("lightning_android", None)
    import lightning_android

    class Bridge:
        def __init__(self, answer):
            self.answer, self.calls = answer, []

        def offer(self, path, name, media):
            self.calls.append((path, name, media, Path(path).read_bytes()))
            return self.answer

    folder = tmp_path / "outgoing"
    folder.mkdir()
    (folder / "left-by-a-closed-app").write_bytes(b"old")
    taken = lightning_android.AndroidFiles(Bridge(True), folder)
    assert list(folder.iterdir()) == []  # nothing older is ever offered
    assert taken.offer("a.csv", "text/csv", b"1,2") is True
    path, name, media, data = taken.bridge.calls[0]
    assert Path(path).parent == folder and (name, media, data) == ("a.csv", "text/csv", b"1,2")
    refused = lightning_android.AndroidFiles(Bridge(False), folder)
    assert refused.offer("b.csv", "text/csv", b"3") is False and list(folder.iterdir()) == []
    assert lightning_android.AndroidFiles.create(folder) is None  # off the phone: no bridge
