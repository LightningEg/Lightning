import pytest

from lightning.core.errors import ValidationError
from lightning.transactions.submissions import SubmissionStore, fingerprint


@pytest.fixture
def submission_store(c):
    """Direct SubmissionStore fixture with real Database, Repository, and AuditLog."""
    return SubmissionStore(c.db, c.transactions.repo, c.transactions.audit)


@pytest.fixture
def sample_txn(c, setup):
    """Create a sample real transaction in the repository."""
    accounts, cats = setup
    return c.transactions.record_inflow(
        "2026-09-05", accounts["wallet"].id, "500", cats["EXP.WORK.SALARY"].id
    )


def test_fingerprint_validation_and_deterministic_hash():
    """fingerprint requires a 32-character lowercase hex token and sorts payload keys."""
    valid_token = "a" * 32
    payload = {"b": "2", "a": "1"}

    res = fingerprint(valid_token, payload)
    assert res is not None
    token, payload_hash = res
    assert token == valid_token
    # Same payload with different dictionary key insertion order produces identical hash
    assert fingerprint(valid_token, {"a": "1", "b": "2"})[1] == payload_hash

    # Invalid token formats return None (caller keeps old contract)
    assert fingerprint(None, payload) is None
    assert fingerprint("", payload) is None
    assert fingerprint("short", payload) is None
    assert fingerprint("a" * 31, payload) is None
    assert fingerprint("a" * 33, payload) is None
    assert fingerprint("z" * 32, payload) is None  # 'z' is not a hex character
    assert fingerprint("A" * 32, payload) is None  # uppercase is refused


def test_same_token_and_payload_returns_first_transaction(submission_store, sample_txn):
    """The same token and payload returns the first transaction."""
    token = "0" * 32
    payload = {"amount": "500", "account": "wallet"}

    # Initially, nothing has been submitted for this token
    assert submission_store.submitted(token, payload) is None

    # Remember the submission associated with sample_txn
    submission_store.remember_submission(token, payload, sample_txn.id)

    # Submitting again with the identical token and payload returns the first transaction
    retrieved = submission_store.submitted(token, payload)
    assert retrieved is not None
    assert retrieved.id == sample_txn.id
    assert retrieved.ref == sample_txn.ref


def test_same_token_with_other_values_raises_validation_error(
    submission_store, sample_txn
):
    """The same token with other values raises 'This form was already saved'."""
    token = "1" * 32
    original_payload = {"amount": "500", "account": "wallet"}
    tampered_payload = {"amount": "999", "account": "wallet"}

    submission_store.remember_submission(token, original_payload, sample_txn.id)

    # Tampered or different payload values with the same token must raise ValidationError
    with pytest.raises(ValidationError, match="This form was already saved"):
        submission_store.submitted(token, tampered_payload)


def test_voided_transaction_raises_validation_error(c, submission_store, sample_txn):
    """A voided transaction raises 'This form was already saved'."""
    token = "2" * 32
    payload = {"amount": "500", "account": "wallet"}

    submission_store.remember_submission(token, payload, sample_txn.id)

    # Void the transaction
    c.transactions.void(sample_txn.id, reason="Mistake")
    assert c.transactions.get(sample_txn.id).is_void

    # Checking submitted form for a voided transaction must raise ValidationError
    with pytest.raises(ValidationError, match="This form was already saved"):
        submission_store.submitted(token, payload)


def test_nonexistent_transaction_row_raises_validation_error(c, submission_store):
    """If the recorded txn_id no longer exists in repository, submitted raises ValidationError."""
    token = "3" * 32
    payload = {"plan": "retirement"}
    non_existent_id = 999999

    submission_store.remember_submission(token, payload, non_existent_id)

    with pytest.raises(ValidationError, match="This form was already saved"):
        submission_store.submitted(token, payload)


def test_form_seen_and_remember_form_behave_for_non_transaction_forms(
    submission_store,
):
    """form_seen and remember_form behave the same for a form that saved something other than one transaction."""
    token = "4" * 32
    payload = {"goal": "emergency_fund", "target": "100000"}
    different_payload = {"goal": "emergency_fund", "target": "200000"}

    # Initially unseen
    assert submission_store.form_seen(token, payload) is False

    # Remember form without an entity transaction id (records entity_id=0)
    submission_store.remember_form(token, payload)

    # Identical token and payload reports seen
    assert submission_store.form_seen(token, payload) is True

    # Same token with different values is refused
    with pytest.raises(ValidationError, match="This form was already saved"):
        submission_store.form_seen(token, different_payload)


def test_no_token_means_nothing_is_remembered(submission_store, sample_txn):
    """No token means nothing is remembered."""
    payload = {"amount": "100"}

    for invalid_token in (None, "", "not-a-token", "123"):
        # submitted returns None
        assert submission_store.submitted(invalid_token, payload) is None
        # form_seen returns False
        assert submission_store.form_seen(invalid_token, payload) is False

        # Calling remember functions with no valid token does not write to audit log
        count_before = submission_store.db.one(
            "SELECT COUNT(*) as c FROM audit_log WHERE entity='form'"
        )["c"]
        submission_store.remember_form(invalid_token, payload)
        submission_store.remember_submission(invalid_token, payload, sample_txn.id)
        count_after = submission_store.db.one(
            "SELECT COUNT(*) as c FROM audit_log WHERE entity='form'"
        )["c"]
        assert count_before == count_after
