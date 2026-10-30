"""Account totals and register rows follow A06.1's total, row and field roles."""

from fastapi.testclient import TestClient

from lightning.ui.web import _amount_role, create_app


def test_amount_role_formats_totals_and_rows_but_preserves_fields():
    from decimal import Decimal

    assert _amount_role(Decimal("71624.86"), "total") == "71,625"
    assert _amount_role(Decimal("-468.5"), "row", True) == "−468.50"
    assert _amount_role("-468.500", "field") == "-468.500"
    assert _amount_role(Decimal("12.5"), "field") == "12.50"
    assert _amount_role("1,250.0", "field") == "1,250.0"
    assert _amount_role("", "field") == ""


def test_transfer_row_has_direction_sign_and_same_amount_on_pc_and_phone(c, setup):
    accounts, _ = setup
    source, destination = accounts["cib"], accounts["wallet"]
    c.transactions.record_transfer("2026-09-10", source.id, destination.id, "468.50")

    pc = TestClient(create_app(c)).get(f"/accounts/{source.id}").text
    phone_app = create_app(c)

    @phone_app.middleware("http")
    async def use_phone_register(request, call_next):
        request.state.phone = True
        return await call_next(request)

    phone = TestClient(phone_app).get(f"/accounts/{source.id}").text

    for html in (pc, phone):
        assert "−468.50" in html
        assert html.count("To Wallet") == 1
        assert "49,532" in html  # the running balance is whole EGP (audit 12, T4); the row's amount keeps its cents
    assert "−468.50" in pc and "−468.50" in phone
    assert "To Wallet</small>" not in pc

    incoming_pc = TestClient(create_app(c)).get(f"/accounts/{destination.id}").text
    incoming_phone_app = create_app(c)

    @incoming_phone_app.middleware("http")
    async def use_phone_register(request, call_next):
        request.state.phone = True
        return await call_next(request)

    incoming_phone = TestClient(incoming_phone_app).get(f"/accounts/{destination.id}").text
    for html in (incoming_pc, incoming_phone):
        assert "+468.50" in html
        assert "From CIB Current" in html
