"""SMS capture actions. Captured messages are staged as ordinary bank-import batches."""
from datetime import datetime

from .spec import INT, JSON, TEXT, Command, optional, ref

TABLES = ()  # Settings and bank-import rows are owned by their respective areas.


def _encode_read(adapter, values):
    messages = []
    for item in values["messages"]:
        sender, text, received, *extra = item
        messages.append([sender, text, received.isoformat() if isinstance(received, datetime) else str(received), *extra])
    return values | {"messages": messages}


def _decode_read(adapter, values):
    messages = []
    for sender, text, received, *extra in values["messages"]:
        messages.append((sender, text, datetime.fromisoformat(received), *extra))
    return values | {"messages": messages}


COMMANDS = {
    # Assignment updates the portable account-ending map and stages all waiting rows atomically.
    "sms_imports.assign": Command("sms_imports.assign", dict(ending=TEXT, account_id=ref("accounts"))),
    # Pasted/shared messages arrive as tuples with a local timestamp; the wire carries an ISO timestamp.
    "sms_imports.read": Command("sms_imports.read", dict(messages=JSON, cursor_ms=optional(INT)),
                                 encode=_encode_read, decode=_decode_read),
}
