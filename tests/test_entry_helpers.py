"""The command bar's search (lightning/ui/routes/search.py) and privacy mode, on the server side.

What runs in the window (Ctrl-K, arrows and Enter, blurring amounts) is in lightning/ui/static/app.js;
it was checked in Chromium. Here: what the search finds and in what order, that every page and action
it offers opens, and how privacy mode is remembered.
"""

from fastapi.testclient import TestClient

from lightning.ui.routes.search import ACTIONS, GROUPS, PAGES, matches
from lightning.ui.web import create_app


def _house(c):
    cib = c.account_flows.open_account("CIB Current", "BANK", "2026-09-01", "50,000", institution="CIB")
    food = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    txn = c.transactions.record_outflow("2026-09-10", cib.id, "1,500", food.id, counterparty="Carrefour & Co",
                                        notes="Kahk #Eid")
    return cib, txn


def _kinds(rows):
    return [(row["kind"], row["label"]) for row in rows]


def test_results_are_ranked_and_grouped_by_type(c):
    cib, txn = _house(c)
    loan = _kinds(matches(c, "loan"))
    assert loan[:3] == [("Page", "Loans"), ("Action", "Add loan"), ("Category", "Loan payments")]
    assert loan[-1] == ("Search", "Find transactions with “loan”")
    kinds = [kind for kind, _ in loan]
    assert kinds == sorted(kinds, key=GROUPS.index)  # an own account is never mixed in with counterparties

    assert ("Account", "CIB Current") in _kinds(matches(c, "cib"))
    assert ("Action", "Import CSV · CIB Current") in _kinds(matches(c, "import"))
    assert _kinds(matches(c, "carref"))[0] == ("Counterparty", "Carrefour & Co")
    assert _kinds(matches(c, txn.ref.lower()))[0] == ("Transaction", txn.ref)
    assert _kinds(matches(c, "#e"))[0] == ("Tag", "#eid")
    assert _kinds(matches(c, "1,500")) == [("Search", "Find transactions with “1,500”")]  # never a near spelling of an amount
    assert _kinds(matches(c, "lons"))[0] == ("Page", "Loans")  # a near spelling of a name is fine


def test_links_are_encoded_and_the_empty_bar_is_a_launcher(c):
    _house(c)
    party = next(row for row in matches(c, "carref") if row["kind"] == "Counterparty")
    assert party["href"] == "/transactions?q=Carrefour+%26+Co"
    launcher = matches(c, "")
    assert launcher[0] == {"label": "Overview", "href": "/", "kind": "Page", "context": ""}
    assert launcher[-1]["label"] == "Hide amounts" and launcher[-1]["action"] == "privacy"
    assert matches(c, "", privacy=True)[-1]["label"] == "Show amounts"


def test_every_page_and_action_offered_opens(c):
    _house(c)
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    for label, href, _ in PAGES + ACTIONS:
        assert client.get(href).status_code == 200, f"{label} ({href})"


def test_search_page_and_command_bar_ask_the_same_matcher(c):
    _house(c)
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    answer = client.get("/search", params={"q": "loan", "format": "json"}).json()
    assert answer["query"] == "loan" and _kinds(answer["results"]) == _kinds(matches(c, "loan"))
    page = client.get("/search", params={"q": "loan"}).text
    assert '<h2 class="search-group">Pages</h2><a class="recent-row" href="/plan/loans"><b>Loans</b>' in page
    shell = client.get("/").text
    assert 'id="command-bar"' in shell and 'href="/search" data-command-open aria-keyshortcuts="Control+K"' in shell


def test_category_result_shows_parent_separately_without_breadcrumb(c):
    category = c.categories.get_by_code("EXP.PERSONAL.FOOD")
    parent = c.categories.get(category.parent_id)
    result = next(row for row in matches(c, category.name) if row["kind"] == "Category" and row["label"] == category.name)
    assert result["context"] == parent.name
    page = TestClient(create_app(c)).get("/search", params={"q": category.name}).text
    assert f'{parent.name} › {category.name}' not in page


def test_privacy_mode_is_the_windows_cookie_else_what_the_profile_remembers(c):
    _house(c)
    client = TestClient(create_app(c), base_url="http://127.0.0.1")
    assert '<html lang="en" dir="ltr" data-week-start="6">' in client.get("/").text and 'aria-pressed="false"' in client.get("/").text
    assert client.post("/settings/privacy", data={"on": "1"}).status_code == 204
    assert c.settings.get("privacy_mode") == "1"
    shell = client.get("/").text
    assert '<html lang="en" dir="ltr" data-week-start="6" class="privacy">' in shell and 'aria-label="Show amounts"' in shell
    client.cookies.set("lightning_privacy", "0")  # switched off in this window, for this sitting
    assert '<html lang="en" dir="ltr" data-week-start="6">' in client.get("/").text
    client.post("/settings/privacy", data={"on": "0"})
    client.cookies.set("lightning_privacy", "1")  # a reader session cannot save, so its cookie decides
    assert '<html lang="en" dir="ltr" data-week-start="6" class="privacy">' in client.get("/").text and c.settings.get("privacy_mode") == "0"


def test_privacy_toggle_preserves_previous_undo_and_does_not_settle(c, setup, monkeypatch):
    accounts, categories = setup
    bank = accounts['cib'].id
    client = TestClient(create_app(c))
    from lightning.undo import user_action
    with user_action('Record expense'):
        c.transactions.record_outflow('2026-09-10', bank, '40', categories['EXP.PERSONAL.FOOD'].id)
    before = c.undo.available()['undo']
    assert before is not None
    monkeypatch.setattr(c.planning, 'match_payments', lambda day: (_ for _ in ()).throw(AssertionError('unexpected settlement')))
    assert client.post('/settings/privacy', data={'on': '1'}).status_code == 204
    assert c.settings.get('privacy_mode') == '1'
    assert c.undo.available()['undo'] == before
    monkeypatch.undo()
    c.undo.replay(expected_id=before['id'])
    assert c.reporting.account_balance(bank) == 50000
    assert c.settings.get('privacy_mode') == '1'
