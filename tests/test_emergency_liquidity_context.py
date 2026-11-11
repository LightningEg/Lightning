"""Emergency liquidity context labels accessible, locked and unknown holdings separately."""
from decimal import Decimal
from types import SimpleNamespace
from tests.screens import said


def _holding(asset, class_code, value, locked_until=None):
    return SimpleNamespace(asset=asset, class_code=class_code, value=value, locked_until=locked_until)


def test_context_keeps_free_cash_money_market_locked_and_unknown_separate():
    from lightning.planning.emergency_context import emergency_liquidity_context

    position = SimpleNamespace(
        free_cash=Decimal("55560"),
        classes=(
            SimpleNamespace(name="Money Market Fund", items=[
                _holding("MMF", "FUND.MONEY_MARKET", Decimal("3033"))]),
            SimpleNamespace(name="CDs / Time Deposits", items=[
                _holding("CIB Certificate", "DEPOSIT.CD", Decimal("100000"), "2027-08-01")]),
            SimpleNamespace(name="Stocks", items=[
                _holding("CIB shares", "STOCK", Decimal("14000")),
                _holding("Unpriced share", "STOCK", None)]),
        ),
    )

    context = emergency_liquidity_context(position)
    assert context["free_cash"] == Decimal("55560")
    assert context["within_days"] == [{"label": "Money Market Fund", "value": Decimal("3033"), "unvalued": 0}]
    assert context["locked"] == [{"label": "CIB Certificate", "value": Decimal("100000"), "until": "2027-08-01"}]
    assert context["unknown"] == [{"label": "Stocks", "value": Decimal("14000"), "unvalued": 1}]
    assert "total" not in context


def test_unclassified_unvalued_holding_has_no_invented_value_or_timing():
    from lightning.planning.emergency_context import emergency_liquidity_context

    position = SimpleNamespace(free_cash=None, classes=(SimpleNamespace(name="Other", items=[
        _holding("Unpriced item", "OTHER", None)]),))
    context = emergency_liquidity_context(position)

    assert context["free_cash"] is None
    assert context["unknown"] == [{"label": "Other", "value": None, "unvalued": 1}]
    assert context["within_days"] == [] and context["locked"] == []


def test_reserves_and_health_show_the_display_only_context(c, setup):
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from types import SimpleNamespace

    from lightning.core.dates import today
    from lightning.core.money import fmt
    from lightning.ui.web import create_app

    c.reserves.set_emergency_fund("5000")
    position = c.position.at(today())
    classes = (
        SimpleNamespace(name="Money Market Fund", items=[
            _holding("Money Market Fund", "FUND.MONEY_MARKET", Decimal("3033"))]),
        SimpleNamespace(name="CDs / Time Deposits", items=[
            _holding("CIB Certificate", "DEPOSIT.CD", Decimal("100000"), "2027-08-01")]),
        SimpleNamespace(name="Stocks", items=[
            _holding("CIB shares", "STOCK", Decimal("14000"))]),
    )
    c.position.at = lambda as_of=None, *, match_payments=True: replace(position, classes=classes)
    browser = TestClient(create_app(c))

    reserves = browser.get("/plan/reserves").text
    health = browser.get("/financial-health").text
    assert "Could also use" in reserves and "Could also use" in health
    for page in (reserves, health):
        assert f"{fmt(position.free_cash, 0)}" in page
        assert "Money Market Fund" in page and "3,033" in page and "Accessible in days" in page
        assert "CIB Certificate" in page and "100,000" in page and said("Locked until 2027-08-01") in page
        assert "Stocks" in page and "14,000" in page and "Access timing unknown" in page


def test_phone_liquidity_other_preserves_sources_and_timing(c, setup):
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from lightning.core.dates import today
    from lightning.ui.web import create_app

    c.reserves.set_emergency_fund('5000')
    position = c.position.at(today())
    classes = (
        SimpleNamespace(name='Money Market Fund', items=[_holding('Fund', 'FUND.MONEY_MARKET', Decimal('100'))]),
        SimpleNamespace(name='Certificates', items=[
            _holding('Certificate A', 'DEPOSIT.CD', Decimal('200'), '2027-08-01'),
            _holding('Certificate B', 'DEPOSIT.CD', Decimal('300'), '2028-08-01')]),
        SimpleNamespace(name='Stocks', items=[_holding('Stock', 'STOCK', Decimal('400'))]),
        SimpleNamespace(name='Gold', items=[_holding('Unpriced gold', 'GOLD', None)]),
    )
    c.position.at = lambda as_of=None, *, match_payments=True: replace(position, classes=classes)
    app = create_app(c)
    async def phone_app(scope, receive, send):
        scope.setdefault('state', {})['phone'] = True
        await app(scope, receive, send)
    phone, desktop = TestClient(phone_app), TestClient(app)
    path = '/plan/reserves'
    def context(html):
        return html.split('class="muted small emergency-liquidity-context"', 1)[1].split('</details>', 1)[0]
    short = context(phone.get(path).text)
    assert all(name in short for name in ('Free cash', 'Money Market Fund', 'Certificate A', 'Certificate B'))
    assert 'Other' in short and '2 more sources' in short
    assert 'Stocks' not in short and 'Unpriced gold' not in short
    full = context(phone.get(path + '?liquidity_view=all').text)
    assert 'Stocks' in full and 'Gold' in full and 'Value unavailable' in full
    assert 'Accessible in days' in full and said('Locked until 2027-08-01') in full and 'Access timing unknown' in full
    assert 'Show fewer' in full
    desktop_context = context(desktop.get(path).text)
    assert 'Stocks' in desktop_context and 'Gold' in desktop_context and 'liquidity_view' not in desktop_context
    health = context(phone.get('/financial-health?as_of=2026-12-31').text)
    assert 'as_of=2026-12-31' in health and 'liquidity_view=all' in health
    expanded_health = context(phone.get('/financial-health?as_of=2026-12-31&liquidity_view=all').text)
    assert 'Stocks' in expanded_health and 'Gold' in expanded_health
