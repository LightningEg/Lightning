"""IV-3AM O2: Strong rose means a problem (guideline A03). A Needs you row whose items put no money at risk (a
payment to match, cleanup) is a to-do: its action reads in the action colour, not rose."""
from __future__ import annotations

from lightning.workflows.review import grouped


def _item(label, href, priority, consequence):
    return {"label": label, "detail": "", "href": href, "priority": priority, "consequence": consequence}


def test_only_groups_with_money_at_risk_are_marked_risk():
    groups = grouped([_item("A data check does not add up", "/checks", 0, "risk"),
                      _item("Match an SMS", "/sms", 2, "unreconciled"),
                      _item("Name a counterparty", "/settings", 2, "cleanup")])
    assert sorted(g["risk"] for g in groups) == [False, False, True]
    assert groups[0]["risk"]  # the most urgent group, the data check, sorts first


def test_the_action_word_is_rose_only_on_risk_rows(c, monkeypatch):
    from fastapi.testclient import TestClient
    from lightning.samples import SAMPLE_TODAY, load_mohab_2026
    from lightning.ui.web import create_app
    monkeypatch.setenv("LIGHTNING_PRICES_OFFLINE", "1")
    monkeypatch.setenv("LIGHTNING_TODAY", SAMPLE_TODAY.isoformat())
    load_mohab_2026(c)
    with TestClient(create_app(c)) as client:
        page = client.get("/").text
    section = page.split('<section class="needs"', 1)[1].split("</section>", 1)[0]
    acts = section.count('class="needs-act')
    risky = section.count('class="needs-act is-risk"')
    assert acts and risky < acts  # the sample has to-dos that are not risks
