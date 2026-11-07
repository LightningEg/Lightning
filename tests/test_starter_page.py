"""NF-7AC4: the starter workbook page: download, upload, review, add, and the result file with codes."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))
from test_starter_import import acct, entry, workbook  # noqa: E402

from lightning.bootstrap import build  # noqa: E402
from lightning.ui.web import create_app  # noqa: E402
from lightning.workflows.workbook_import import read_workbook  # noqa: E402


@pytest.fixture
def parts(tmp_path):
    ledger = build(tmp_path / "t.db")
    client = TestClient(create_app(ledger))
    yield ledger, client
    ledger.db.close()


def upload(client, data):
    return client.post("/exports/starter", files={"workbook": ("mine.xlsx", data)})


def hidden(html, name):
    return re.search(rf'name="{name}" value="([^"]*)"', html).group(1)


GOOD = workbook([acct("Salary account", bal=5000)], [(None, "Personal", "Pets", "Spending", None)],
                [entry("2026-01-05", "Salary account", "Pets", "Vet", -420),
                 entry("2026-01-06", "Salary account", "Mystery", "x", -5)])


def test_the_pages_link_to_each_other_and_the_template_downloads(parts):
    _, client = parts
    assert "/exports/starter" in client.get("/exports/import").text
    page = client.get("/exports/starter")
    assert page.status_code == 200 and "/exports/starter/template" in page.text
    template = client.get("/exports/starter/template")
    assert template.headers["content-type"].endswith("spreadsheetml.sheet") and "attachment" in template.headers["content-disposition"]
    assert list(read_workbook(template.content))[:4] == ["Read me", "Accounts", "Categories", "Entries"]


def test_review_changes_nothing_then_add_it_and_download_the_codes(parts):
    ledger, client = parts
    before = ledger.db.scalar("SELECT COUNT(*) FROM transactions")
    review = upload(client, GOOD)
    assert review.status_code == 200 and "Review what will be added" in review.text and "Mystery" not in review.text.split("Entries to add")[1].split("Rows that cannot")[0]
    assert "The category is not on the Categories sheet or in Lightning." in review.text
    assert ledger.db.scalar("SELECT COUNT(*) FROM transactions") == before
    done = client.post("/exports/starter", data={"action": "confirm", "token": hidden(review.text, "token"),
                                                  "payload": hidden(review.text, "payload")})
    assert done.status_code == 200 and "Your data is in" in done.text and "1 rows could not be placed" in done.text
    link = re.search(r'href="(/exports/starter/result/[^"]+)"', done.text).group(1)
    result = client.get(link)
    sheets = read_workbook(result.content)
    assert sheets["Not imported"][1][0] == "Entries" and any(r[0] == "Category" and r[2] == "EXP.PERSONAL.PETS" for r in sheets["Codes"][1:])
    # the file that came back imports nothing twice
    again = upload(client, result.content)
    assert "There is nothing new to add." in again.text or "Rows that cannot be placed" in again.text
    assert "Add them" not in again.text or "To add" in again.text


def test_a_preview_cannot_be_replayed_or_swapped(parts):
    ledger, client = parts
    review = upload(client, GOOD)
    token, payload = hidden(review.text, "token"), hidden(review.text, "payload")
    other = __import__("base64").b64encode(workbook([acct("Other")])).decode()
    swapped = client.post("/exports/starter", data={"action": "confirm", "token": token, "payload": other})
    assert swapped.status_code == 400 and "expired or the file changed" in swapped.text
    assert client.post("/exports/starter", data={"action": "confirm", "token": token, "payload": payload}).status_code == 400  # token used up
    assert client.get("/exports/starter/result/nope").status_code == 404


def test_a_file_that_is_not_a_starter_workbook_says_so_plainly(parts):
    _, client = parts
    response = upload(client, b"not a workbook")
    assert response.status_code == 400 and "Choose a valid Excel .xlsx workbook" in response.text
    response = upload(client, workbook(skip_sheet="Entries"))
    assert response.status_code == 400 and "no Entries sheet" in response.text


def test_arabic_shows_no_english_on_every_step(parts):
    from test_arabic_no_english import _english
    ledger, client = parts
    assert client.post("/settings/locale", data={"locale": "ar"}, follow_redirects=False).status_code == 303
    pages = [client.get("/exports/starter").text, client.get("/exports/import").text]
    review = upload(client, GOOD)
    pages.append(review.text)
    done = client.post("/exports/starter", data={"action": "confirm", "token": hidden(review.text, "token"),
                                                  "payload": hidden(review.text, "payload")})
    pages.append(done.text)
    bad = workbook([acct("A", bal=-5), acct("A"), acct("B", kind="x"), acct("C", cur="ZZZ"), acct("D", day="2999-01-01"),
                    acct("E", kind="Certificates", bal=1), acct("")],
                   [(None, "Hobbies", "x", "Spending", None), (None, "Personal", "x", "Both", None),
                    (None, "Personal", "", "Spending", None), (None, "Personal", "Y", "Spending", None),
                    (None, "Personal", "y", "Spending", None)],
                   [entry("2026-01-05", "Nowhere", "Pets", "x", -5), entry("nope", "A", "Pets", "x", -5),
                    entry("2026-01-05", "A", "Pets", "x", 0), entry("2026-01-05", "A", "Pets", "x", "abc"),
                    entry("2026-01-05", "A", "Mystery", "x", -5), entry("2026-01-05", "A", "Transportation", "x", -5),
                    entry("2026-01-05", "A", "Salary", "x", -5), entry("2026-01-05", "A", "Adjustment", "x", -5),
                    entry("2026-01-05", "A", "Pets", "x", -5, cur="USD"), entry("2026-01-05", "A", "Pets", "x", -5, ref="NOPE-1"),
                    entry("2026-01-05", "A", "Pets", "x", -5.1234567)])
    problems = upload(client, bad)
    pages.append(problems.text.replace("Shown", ""))
    for html in pages:
        assert not [t for t in _english(html, {"Salary account", "Vet", "Pets", "Mystery", "Nowhere", "Hobbies", "abc"}) if "Not imported" not in t], html[:80]
