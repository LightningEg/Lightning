from __future__ import annotations

from datetime import date
from decimal import Decimal
import pytest

from lightning.core.errors import NotFoundError, ValidationError
from lightning.deposits import DepositService


@pytest.fixture
def deposits(c, setup):
    accounts, _ = setup
    return DepositService(c.db, c.accounts), accounts


def _save(service, accounts, **overrides):
    values = {
        "account_id": accounts["cd"].id,
        "start_date": "2028-01-31",
        "maturity_date": "2028-05-31",
        "principal": "5000",
        "annual_rate": "18",
        "interest_method": "SIMPLE",
        "payout_frequency": "MONTHLY",
        "destination_account_id": accounts["cib"].id,
    }
    values.update(overrides)
    return service.save(**values)


def test_simple_actual_days_month_end_and_maturity_return(deposits):
    service, accounts = deposits
    _save(service, accounts, lockup_end_date="2028-04-30")
    events = service.future_events("2028-01-31", "2028-05-31")
    assert [(e.date, e.kind, e.account_id, e.deposit_account_id) for e in events] == [
        ("2028-02-29", "INTEREST", accounts["cib"].id, accounts["cd"].id),
        ("2028-03-31", "INTEREST", accounts["cib"].id, accounts["cd"].id),
        ("2028-04-30", "INTEREST", accounts["cib"].id, accounts["cd"].id),
        ("2028-05-31", "INTEREST", accounts["cib"].id, accounts["cd"].id),
        ("2028-05-31", "PRINCIPAL", accounts["cib"].id, accounts["cd"].id),
    ]
    assert events[0].amount == Decimal("71.506849")  # 29 actual days at 18% p.a.
    assert events[-1].amount == Decimal("5000")


def test_compound_is_one_maturity_event_and_rounds_once(deposits):
    service, accounts = deposits
    _save(service, accounts, maturity_date="2029-01-31", annual_rate="10.123456789",
          interest_method="COMPOUND", payout_frequency="AT_MATURITY",
          compounding_frequency="QUARTERLY")
    events = service.future_events("2028-01-31", "2029-01-31")
    assert len(events) == 1
    assert events[0].kind == "MATURITY"
    assert events[0].amount == Decimal("5527.209228")
    assert events[0].date == "2029-01-31"
    assert service.get(accounts["cd"].id).compounding_frequency.value == "QUARTERLY"


def test_compounding_frequency_changes_capitalization(deposits):
    service, accounts = deposits
    _save(service, accounts, maturity_date="2029-01-31", annual_rate="12",
          interest_method="COMPOUND", payout_frequency="AT_MATURITY",
          compounding_frequency="MONTHLY")
    monthly = service.future_events("2028-01-31", "2029-01-31")[0].amount
    _save(service, accounts, maturity_date="2029-01-31", annual_rate="12",
          interest_method="COMPOUND", payout_frequency="AT_MATURITY",
          compounding_frequency="YEARLY")
    yearly = service.future_events("2028-01-31", "2029-01-31")[0].amount
    assert monthly > yearly


def test_no_events_on_or_before_as_of_and_lockup_is_not_cash_event(deposits):
    service, accounts = deposits
    terms = _save(service, accounts, lockup_end_date="2028-03-15")
    assert terms.lockup_end_date == "2028-03-15"
    events = service.future_events("2028-02-29", "2028-03-31")
    assert [event.date for event in events] == ["2028-03-31"]
    assert service.future_events("2028-05-31", "2028-06-30") == []


def test_projection_suppressed_when_not_owned_and_save_requires_funding(deposits, c):
    service, accounts = deposits
    with pytest.raises(ValidationError, match="You can put in at most"):
        _save(service, accounts, principal="5000.000001")
    _save(service, accounts, principal="4000")
    c.deposits.move_legacy_cash(accounts["cd"].id, "2026-09-25", "1500", accounts["cib"].id)
    assert service.future_events("2026-09-26", "2028-05-31") == []


@pytest.mark.parametrize("changes,field", [
    ({"principal": "0"}, "principal"),
    ({"annual_rate": "100.0001"}, "annual_rate"),
        ({"start_date": "2028-05-31"}, "maturity_date"),
        ({"lockup_end_date": "2028-06-01"}, "lockup_end_date"),
    ({"destination_account_id": "cd"}, "destination_account_id"),
    ({"interest_method": "COMPOUND"}, "payout_frequency"),
])
def test_term_validation(deposits, changes, field):
    service, accounts = deposits
    if changes.get("destination_account_id") == "cd":
        changes["destination_account_id"] = accounts["cd"].id
    with pytest.raises(ValidationError) as error:
        _save(service, accounts, **changes)
    assert error.value.field == field


def test_get_delete_and_interest_at_maturity(deposits):
    service, accounts = deposits
    terms = _save(service, accounts, payout_frequency="AT_MATURITY")
    assert service.get(accounts["cd"].id) == terms
    events = service.future_events(date(2028, 1, 31), date(2028, 5, 31))
    assert [(event.kind, event.date) for event in events] == [
        ("INTEREST", "2028-05-31"), ("PRINCIPAL", "2028-05-31")]
    service.delete(accounts["cd"].id)
    with pytest.raises(NotFoundError, match="CD terms were not found"):
        service.get(accounts["cd"].id)
