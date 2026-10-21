from fastapi.testclient import TestClient

from lightning.ui.web import create_app


def test_needs_you_rows_name_each_decision_and_the_count(c, setup, monkeypatch):
    monkeypatch.setenv("LIGHTNING_TODAY", "2026-09-30")
    c.planning.create(kind="BILL", name="Electricity", amount="480", frequency="MONTHLY", start_date="2026-09-25")
    c.planning.create(kind="LOAN", name="Car loan", amount="2500", frequency="MONTHLY", start_date="2026-09-05",
                      payment_count="3")

    page = TestClient(create_app(c)).get("/").text
    section = page[page.index('<section class="needs"'):page.index("</section>", page.index('<section class="needs"'))]

    assert "<span>· 2</span>" in section  # Needs you · 2 (guideline 3.33, A09)
    assert "Bills and payments · 2" in section and "Loan payment due: Car loan, Bill due: Electricity" in section
    assert section.count('class="needs-row"') == 1 and "needs-mark" in section  # one row per kind, the mark as bullet


def test_the_overview_has_no_investments_row(c, setup):
    """Feedback 100: the one-line Investments row is gone; the Investments tab holds those figures."""
    page = TestClient(create_app(c)).get("/").text
    assert 'aria-label="Investments in this period"' not in page and "investments-heading" not in page