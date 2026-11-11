"""Safe to spend labels reconcile without changing exact forecasts."""
from decimal import Decimal as D

import pytest


def test_safe_to_spend_display_keeps_free_cash_and_reconciles_signed_parts():
    from lightning.ui.visuals import _safe_display_parts as safe_to_spend_parts
    from lightning.core.money import quantize
    parts = [('Free cash', D('312504.51')), ('Budget until payday', D('-1283.51')),
             ('Emergency fund top-up', D('-11520.51')), ('Rest of savings target', D('-2012.51'))]
    total = sum((value for _, value in parts), D(0))
    shown = safe_to_spend_parts(parts, total)
    assert shown[0] == ('Free cash', D('312505'))
    assert sum(value for _, value in shown) == quantize(total, 0) == D('297688')
    assert sum(quantize(value, 0) for _, value in parts) == D('297687')
    assert all(shown[i][1] <= 0 for i in range(1, len(shown)))
    assert [name for name, _ in shown] == [name for name, _ in parts]
    assert parts[0][1] == D('312504.51') and total == D('297687.98')
    negative = [('Free cash', D('-0.49')), ('Due before payday', D('-0.49')), ('Goals', D('-0.49'))]
    shown_negative = safe_to_spend_parts(negative, D('-1.47'))
    assert shown_negative[0][1] == 0 and sum(value for _, value in shown_negative) == -1
    with pytest.raises(ValueError):
        safe_to_spend_parts(parts, total + 1)


def test_pc_safe_to_spend_waterfall_and_table_use_the_same_display_parts(c, setup, monkeypatch):
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    f = c.forecaster.forecast()
    parts = [('Free cash', D('312504.51')), ('Budget until payday', D('-1283.51')),
             ('Emergency fund top-up', D('-11520.51')), ('Rest of savings target', D('-2012.51'))]
    from dataclasses import replace
    f = replace(f, free_cash=parts[0][1], safe_to_spend_parts=parts,
                safe_to_spend=sum((value for _, value in parts), D(0)))
    monkeypatch.setattr(c.forecaster, 'forecast', lambda *args, **kwargs: f)
    with TestClient(create_app(c)) as client:
        response = client.get('/plan')
    assert response.status_code == 200
    section = response.text.split('id="plan-build"', 1)[1].split('</details>', 1)[0]
    import re
    rows = re.findall(r'<span class="chart-fall-label">([^<]+)</span>.*?'
                      r'<b class="chart-fall-value">([^<]+)</b>', section, re.S)
    values = [int(value.replace(',', '').replace('−', '-')) for _, value in rows]
    assert [name for name, _ in rows] == [name for name, _ in parts] + ['Safe to spend']
    assert values[0] == 312505 and values[-1] == 297688
    assert sum(values[:-1]) == values[-1]
    panel = response.text.split('id="working-safe"', 1)[1].split('</table>', 1)[0]  # NF-12AB3: How it adds up
    for name, value in rows[:-1]:
        assert f'<td>{name}</td><td class="num">{value}</td>' in panel
    assert f.free_cash == D('312504.51') and f.safe_to_spend == D('297687.98')


def test_phone_safe_to_spend_bars_use_the_reconciled_display(c, setup, monkeypatch):
    import re
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from lightning.ui.web import create_app
    original = c.forecaster.forecast()
    parts = [('Free cash', D('312504.51')), ('Budget until payday', D('-1283.51')),
             ('Emergency fund top-up', D('-11520.51')), ('Rest of savings target', D('-2012.51'))]
    f = replace(original, free_cash=parts[0][1], safe_to_spend_parts=parts,
                safe_to_spend=sum((value for _, value in parts), D(0)))
    monkeypatch.setattr(c.forecaster, 'forecast', lambda *args, **kwargs: f)
    inner = create_app(c)

    async def phone(scope, receive, send):
        if scope['type'] == 'http':
            scope.setdefault('state', {})['phone'] = True
        await inner(scope, receive, send)

    with TestClient(phone) as client:
        response = client.get('/plan')
    assert response.status_code == 200
    section = response.text.split('id="plan-build"', 1)[1].split('</article>', 1)[0]
    rows = re.findall(r'<span class="phone-bar-name">([^<]+)</span>'
                      r'<b class="phone-bar-value">([^<]+)</b>', section)
    values = [int(value.replace(',', '').replace('−', '-')) for _, value in rows]
    assert [name for name, _ in rows] == [name for name, _ in parts] + ['Safe to spend']
    assert values[0] == 312505 and values[-1] == 297688 and sum(values[:-1]) == values[-1]
    assert f.free_cash == D('312504.51') and f.safe_to_spend == D('297687.98')
