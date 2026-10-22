import pytest

from lightning.sync.journal.codec import JournalError
from lightning.sync.journal.compatibility import check


def test_malformed_peer_capabilities_fail_closed():
    local = dict(protocol=2, app="1.0", ledger_schema=1, effects=[2],
                 entry_kinds={"transaction.add": 1, "commands": []}, catalog="0" * 64)
    malformed = dict(local, entry_kinds={"commands": ["not-a-hash"]})
    with pytest.raises(JournalError, match="capabilities"):
        check(local, malformed, [])


def test_peer_capabilities_reject_duplicate_command_fingerprints():
    local = dict(protocol=2, app="1.0", ledger_schema=1, effects=[2],
                 entry_kinds={"transaction.add": 1, "commands": ["abcdef"]}, catalog="0" * 64)
    malformed = dict(local, entry_kinds={"transaction.add": 1, "commands": ["abcdef", "abcdef"]})
    with pytest.raises(JournalError, match="capabilities"):
        check(local, malformed, [])
