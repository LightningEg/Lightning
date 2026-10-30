"""Running reports compare the same calendar days, including refunds and short months."""
from datetime import date
from decimal import Decimal as D

from fastapi.testclient import TestClient

from lightning.reporting.spending import comparison_windows, spending_profile
from lightning.ui.web import create_app


def test_calendar_windows_preserve_completed_months_and_clamp_february():
    assert comparison_windows(date(2026, 10, 1), date(2026, 10, 14), '2026-09') == [
        (date(2026, 9, 1), date(2026, 9, 14))]
    assert comparison_windows(date(2026, 3, 1), date(2026, 3, 30), '2026-02')[0][1] == date(2026, 2, 28)
    assert comparison_windows(date(2026, 2, 1), date(2026, 2, 28), '2026-01')[0][1] == date(2026, 1, 31)


def test_running_month_excludes_late_prior_payments_and_includes_refunds(c, setup, monkeypatch):
    monkeypatch.setenv('LIGHTNING_TODAY', '2026-10-14')
    accounts, cats = setup
    bank, food = accounts['cib'].id, cats['EXP.PERSONAL.FOOD'].id
    c.transactions.record_outflow('2026-09-05', bank, '1000', food)
    c.transactions.record_refund('2026-09-10', bank, '200', food)
    c.transactions.record_outflow('2026-09-25', bank, '9000', food)
    c.transactions.record_outflow('2026-10-05', bank, '400', food)
    profile = spending_profile(c.reporting, date(2026, 10, 1), date(2026, 10, 14))
    assert profile['partial']
    assert profile['usual_out'] == D('800')
    assert profile['rows'][0]['usual'] == D('800')
    row = c.reporting.spending_vs_usual('2026-10-01', '2026-10-14')[0]
    assert row['usual'] == D('800')
    client = TestClient(create_app(c))
    page = client.get('/birdview/expenses?month=2026-10').text
    assert 'Money out so far' in page
    assert '2026-09 days 1–14' in page
    assert 'the same days in earlier months' in page
    assert 'is-down' not in page.split('cluster-change')[1].split('>')[0]
    client.post('/settings/locale', data={'locale': 'ar'})
    arabic = client.get('/birdview/expenses?month=2026-10').text
    from test_arabic_no_english import _english
    assert _english(arabic, {'CIB Current', 'CIB', 'Wallet', 'CIB CD', 'THNDR'}) == []


def test_multi_month_benchmark_weights_complete_and_partial_months(c, setup):
    accounts, cats = setup
    bank, food = accounts['cib'].id, cats['EXP.PERSONAL.FOOD'].id
    c.transactions.record_outflow('2026-09-05', bank, '100', food)
    c.transactions.record_outflow('2026-09-25', bank, '300', food)
    c.transactions.record_outflow('2026-10-05', bank, '50', food)
    profile = spending_profile(c.reporting, date(2026, 10, 1), date(2026, 11, 14))
    # Equivalent to a completed month (400) plus days 1–14 (100), per month.
    assert profile['usual_out'] == D('250')
    assert profile['rows'][0]['usual'] == D('250')
