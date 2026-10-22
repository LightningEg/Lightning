"""Home-local undo and redo commands."""
from .spec import FLAG, INT, TEXT, Command

# Undo history is local session state and never replicated.
TABLES = ()


COMMANDS = {
    "undo.replay": Command("undo.replay", dict(
        redo=FLAG, expected_id=INT, expected_fingerprint=TEXT,
    )),
}
