"""Arabic coverage for recently added workflow screens."""
from __future__ import annotations

import pytest

from lightning.accounts.domain import AccountType
from lightning.bootstrap import build
from lightning.samples import load_mohab_2026
from lightning.ui.web import create_app
from lightning.workflows.activity import ActivityReview

from test_arabic_no_english import _client, _english, _typed_names


@pytest.fixture(scope="module")
def workflow_sample(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("LIGHTNING_TODAY", "2026-10-02")
        patch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
        c = build(tmp_path_factory.mktemp("workflow-ar") / "t.db")
        load_mohab_2026(c)
        yield c, _typed_names(c)
        c.db.close()


@pytest.mark.parametrize("phone", [False, True], ids=["pc", "phone"])
def test_new_workflow_pages_have_no_english_system_text(workflow_sample, phone):
    c, names = workflow_sample
    client = _client(c, phone)
    posted = c.db.all("SELECT id FROM transactions WHERE status='POSTED' ORDER BY id")
    assert posted
    first_id = ActivityReview(c).recent()[0]["txn"].id
    second_id = posted[-2]["id"] if len(posted) > 1 else posted[-1]["id"]

    view_name = "مراجعة عربية للهاتف" if phone else "مراجعة عربية للكمبيوتر"
    view_id = c.saved_views.save(view_name, {"preset": "all_time"})
    routes = [
        "/review",
        "/activity",
        f"/activity/{first_id}",
        "/payday",
        # IV-12Q: the pages of Budget and Cash planning that got the page pattern
        "/plan/scenarios?what=purchase&purchase=1000&purchase_date=2026-10-10&account_id=1",
        "/plan/inputs",
        "/budget/carryover-bridge?month=2026-10",
        "/budget/fill?month=2026-10&source=average",
        f"/budget/category/{c.categories.find_by_text('Food & groceries').id}/edit?month=2026-10",
        "/reimbursements",
        f"/transactions/merge?keep={first_id}&drop={second_id}",
        f"/transactions/views/{view_id}/report",
    ]
    deposits = [a for a in c.accounts.list() if a.account_type == AccountType.DEPOSIT]
    assert deposits, "The Mohab sample should include a certificate account."
    deposit_route = f"/deposits/{deposits[0].id}"
    routes.append(deposit_route)

    problems = {}
    for path in routes:
        response = client.get(path)
        assert response.status_code == 200, path
        assert 'dir="rtl"' in response.text, path
        if path == deposit_route:
            assert 'id="interest-receipts"' in response.text
        bad = _english(response.text, names)
        if bad:
            problems[path] = sorted(set(bad))[:8]
    assert not problems, problems
