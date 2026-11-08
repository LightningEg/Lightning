"""IT-7AF: larger bounded register pages preserve filters and can select more than fifty entries."""
import html
import re
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def _payments(c, setup, count):
    account, category = setup[0]["cib"], setup[1]["EXP.PERSONAL.FOOD"]
    return [c.transactions.record_outflow("2026-09-10", account.id, "1", category.id,
                                          counterparty="Example page merchant") for _ in range(count)]


def _ids(text):
    return re.findall(r'class="transaction-select" value="(\d+)"', text)


def test_page_sizes_apply_to_sql_and_filtered_pages_and_reject_unbounded_values(c, setup):
    _payments(c, setup, 510)
    url = f"/accounts/{setup[0]['cib'].id}"
    with TestClient(create_app(c)) as client:
        for size in (50, 100, 250, 500):
            first = client.get(url, params={"page_size": size})
            assert first.status_code == 200
            assert len(_ids(first.text)) == size
            filtered = client.get(url, params={"page_size": size, "q": "Example page merchant"})
            assert len(_ids(filtered.text)) == size
        for invalid in ("-1", "0", "999999", "no-size", "99"):
            assert len(_ids(client.get(url, params={"page_size": invalid}).text)) == 50
        first = client.get(url, params={"page_size": 100}).text
        second = client.get(url, params={"page_size": 100, "page": 2}).text
        assert "Showing 101–200 of 511" in second
        assert not set(_ids(first)) & set(_ids(second))


def test_page_size_control_resets_page_and_preserves_search_and_selection(c, setup):
    _payments(c, setup, 115)
    with TestClient(create_app(c)) as client:
        page = client.get("/transactions", params={"q": "Example page merchant", "page_size": 100,
                                                   "page": 2, "select": 1, "kind": "out"}).text
    control = re.search(r'<form[^>]*class="actions register-page-size".*?</form>', page, re.S).group()
    hidden = dict(re.findall(r'type="hidden" name="([^"]+)" value="([^"]*)"', control))
    assert hidden["q"] == "Example page merchant" and hidden["select"] == "1"
    assert hidden["kind"] == "out" and "page" not in hidden
    assert 'value="100" selected' in control
    hrefs = [html.unescape(link) for link in re.findall(r'href="([^"]+)"', page)]
    previous = next(link for link in hrefs if "page=1" in link)
    assert parse_qs(urlparse(previous).query)["page_size"] == ["100"]


def test_phone_larger_pages_keep_size_when_changing_filters(c, setup):
    _payments(c, setup, 115)
    app = create_app(c)

    @app.middleware("http")
    async def phone(request, call_next):
        request.state.phone = True
        return await call_next(request)

    with TestClient(app) as client:
        page = client.get("/transactions", params={"q": "Example page merchant", "page_size": 100,
                                                   "select": 1, "preset": "all_time"}).text
    assert 'id="register-page-size"' in page
    assert len(re.findall(r'name="txn_ids" value="\d+"', page)) == 100
    assert 'name="page_size" value="100"' in page
    older = re.search(r'href="([^"]+)"[^>]*>Show older</a>', page).group(1)
    assert parse_qs(urlparse(html.unescape(older)).query)["page_size"] == ["100"]
    done = re.search(r'href="([^"]+)"[^>]*>Done</a>', page).group(1)
    done_query = parse_qs(urlparse(html.unescape(done)).query)
    assert done_query["page_size"] == ["100"] and "select" not in done_query
