"""IT-1S: a form delivered twice saves once. SubmissionStore directly, not through a route."""
import pytest

from lightning.core.errors import ValidationError
from lightning.transactions.submissions import SubmissionStore, fingerprint, revision

TOKEN = "0123456789abcdef0123456789abcdef"
PAYLOAD = {"date": "2026-10-01", "amount": "100", "note": "Lunch"}


@pytest.fixture
def store(c):
    return SubmissionStore(c.db, c.transactions.repo, c.audit)


@pytest.fixture
def txn_id(c, setup):
    accounts, cats = setup
    return c.transactions.record_outflow("2026-10-01", accounts["cib"].id, "100", cats["EXP.PERSONAL.FOOD"].id).id


def test_fingerprint_needs_a_well_formed_token_and_ignores_key_order():
    assert fingerprint(None, PAYLOAD) is None
    assert fingerprint("", PAYLOAD) is None
    assert fingerprint("short", PAYLOAD) is None
    assert fingerprint("G" * 32, PAYLOAD) is None  # not hexadecimal
    assert fingerprint(TOKEN, PAYLOAD) == fingerprint(TOKEN, dict(reversed(list(PAYLOAD.items()))))
    assert fingerprint(TOKEN, PAYLOAD) != fingerprint(TOKEN, {**PAYLOAD, "amount": "101"})


def test_the_same_token_and_payload_returns_the_first_transaction(store, txn_id):
    assert store.submitted(TOKEN, PAYLOAD) is None
    store.remember_submission(TOKEN, PAYLOAD, txn_id)
    assert store.submitted(TOKEN, PAYLOAD).id == txn_id


def test_the_same_token_with_other_values_is_refused(store, txn_id):
    store.remember_submission(TOKEN, PAYLOAD, txn_id)
    with pytest.raises(ValidationError, match="This form was already saved"):
        store.submitted(TOKEN, {**PAYLOAD, "amount": "999"})


def test_a_voided_transaction_is_refused_not_returned(c, store, txn_id):
    store.remember_submission(TOKEN, PAYLOAD, txn_id)
    c.transactions.void(txn_id)
    with pytest.raises(ValidationError, match="This form was already saved"):
        store.submitted(TOKEN, PAYLOAD)


def test_a_form_that_saved_something_else_is_remembered_the_same_way(store):
    assert store.form_seen(TOKEN, PAYLOAD) is False
    store.remember_form(TOKEN, PAYLOAD)
    assert store.form_seen(TOKEN, PAYLOAD) is True
    with pytest.raises(ValidationError, match="This form was already saved"):
        store.form_seen(TOKEN, {**PAYLOAD, "note": "Dinner"})


def test_no_token_means_nothing_is_remembered(c, store, txn_id):
    before = c.db.scalar("SELECT COUNT(*) FROM audit_log WHERE entity='form'")
    store.remember_submission(None, PAYLOAD, txn_id)
    store.remember_form("", PAYLOAD)
    assert c.db.scalar("SELECT COUNT(*) FROM audit_log WHERE entity='form'") == before
    assert store.submitted(None, PAYLOAD) is None and store.form_seen(None, PAYLOAD) is False


def test_revision_is_stable_and_changes_with_the_snapshot():
    assert revision({"a": 1, "b": 2}) == revision({"b": 2, "a": 1})
    assert revision({"a": 1}) != revision({"a": 2})
