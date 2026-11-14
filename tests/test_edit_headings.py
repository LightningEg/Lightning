"""IV-3BH7: edit headings identify the name or transaction, never an internal code."""
import html
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lightning.ui.date_text import day_text
from lightning.ui.web import create_app


def _text(markup):
    return html.unescape(re.sub(r'<[^>]*>', '', markup)).strip()


@pytest.mark.parametrize('phone', [False, True])
@pytest.mark.parametrize('locale', ['en', 'ar'])
def test_investment_edit_headings_show_names_and_transaction_context(c, setup, phone, locale):
    accounts, _ = setup
    c.settings.set('locale', locale)
    asset = c.assets.create_investment('Growth <safe> & income', 'FUND.MONEY_MARKET', 'AZMM')
    c.transactions.record_transfer('2026-09-02', accounts['cib'].id, accounts['thndr'].id, '1000')
    txn = c.investments.buy('2026-09-10', accounts['thndr'].id, asset.id, '10', '5')
    app = create_app(c)

    @app.middleware('http')
    async def frame(request, call_next):
        request.state.phone = phone
        return await call_next(request)

    client = TestClient(app)
    asset_page = client.get(f'/investments/assets/{asset.id}/edit')
    assert asset_page.status_code == 200
    heading = re.search(r'<h1[^>]*>(.*?)</h1>', asset_page.text, re.S).group(1)
    assert _text(heading) == ('تعديل ' if locale == 'ar' else 'Edit ') + asset.name
    assert asset.code not in heading
    assert '<safe>' not in heading and '&lt;safe&gt;' in heading

    transaction_page = client.get(f'/investments/{txn.id}/edit')
    assert transaction_page.status_code == 200
    heading = re.search(r'<h1[^>]*>(.*?)</h1>', transaction_page.text, re.S).group(1)
    assert _text(heading) == ('تعديل المعاملة' if locale == 'ar' else 'Edit transaction')
    subtitle = re.search(r'<p class="(?:page-line|phone-note)">(.*?)</p>', transaction_page.text, re.S).group(1)
    assert day_text(txn.date, locale=locale) in _text(subtitle)
    if txn.counterparty:
        assert txn.counterparty in _text(subtitle)
    assert txn.ref not in heading + subtitle
    assert '<safe>' not in subtitle


def test_edit_headings_use_complete_translation_keys():
    templates = Path(__file__).parents[1] / 'lightning/ui/templates'
    assert not [str(path.relative_to(templates)) for path in templates.rglob('*.html')
                if "'Edit ' ~" in path.read_text(encoding='utf-8')]
