"""Bank-statement import: staged statements, their rows and the remembered column matches.

Large but bounded statement and decision payloads use chunked command forms. References are converted to UUIDs
before confirmations are compressed, and are restored before the unchanged import service validates each row.
"""
import base64
import json
import zlib

from lightning.core.errors import ValidationError

from .spec import BYTES, FLAG, JSON, TEXT, Command, optional, ref

TABLES = ("bank_import_batches", "bank_import_rows", "bank_import_column_maps")
BATCH = ("bank_import_batches", "batch_id")
IDS = {"category_id": "categories", "transfer_account_id": "accounts", "counterparty_id": "counterparties"}
CHOICES = {"counterparty_choice": ("existing:", "counterparties"), "owner_choice": ("existing:", "counterparties"),
           "match": ("link:", "transactions")}  # name -> (prefix of "<prefix><id>", table)
FILE_LIMIT = 40 * 1024
CONFIRM_COMPRESSED_LIMIT = 40 * 1024
CONFIRM_EXPANDED_LIMIT = 4 * 1024 * 1024
CHUNK_BYTES = 2800  # Base64 fits the command LONG text field and the 64 KiB wire envelope.


def _convert(decisions, row, one):
    """Every id-bearing field of every decision, and the row keys, through `row` and `one` (key and id converters)."""
    out = {}
    for key, decision in decisions.items():
        item = dict(decision)
        for name, table in IDS.items():
            if item.get(name) not in (None, ""):
                item[name] = one(table, item[name], True)
        for name, (prefix, table) in CHOICES.items():
            if isinstance(item.get(name), str) and item[name].startswith(prefix):
                item[name] = prefix + str(one(table, item[name][len(prefix):], False))
        out[row(key)] = item
    return out


def _encode(adapter, values):
    wire = _convert(values["decisions"], lambda key: adapter.uid("bank_import_rows", int(key)),
                    lambda table, value, whole: adapter.uid(table, int(value)))
    return values | dict(decisions=wire)


def _decode(adapter, values):
    # A whole-field id comes back as the type the form gave: counterparty_id an int, the others text.
    local = _convert(values["decisions"], lambda key: adapter.local("bank_import_rows", key),
                     lambda table, value, whole: adapter.local(table, value) if table == "counterparties" and whole
                     else str(adapter.local(table, value)))
    return values | dict(decisions=local)


def _encode_packed_decisions(adapter, values):
    """Portable UUID decisions in a bounded compressed envelope."""
    converted = _convert(values["decisions"], lambda key: adapter.uid("bank_import_rows", int(key)),
                         lambda table, value, whole: adapter.uid(table, int(value)))
    raw = json.dumps(converted, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) > CONFIRM_EXPANDED_LIMIT:
        raise ValidationError("This statement has too many details to synchronize. Split it into smaller files.")
    compressed = zlib.compress(raw, level=6)
    if len(compressed) > CONFIRM_COMPRESSED_LIMIT:
        raise ValidationError("This statement has too many details to synchronize. Split it into smaller files.")
    chunks = [base64.b64encode(compressed[offset:offset + CHUNK_BYTES]).decode("ascii")
              for offset in range(0, len(compressed), CHUNK_BYTES)] or [""]
    return values | {"decisions": chunks}


def _unpack_decisions(adapter, values):
    try:
        chunks = values["decisions"]
        if type(chunks) is not list or len(chunks) > 16 or any(type(part) is not str or len(part) > 4000 for part in chunks):
            raise ValueError
        compressed = b"".join(base64.b64decode(part, validate=True) for part in chunks)
        if len(compressed) > CONFIRM_COMPRESSED_LIMIT:
            raise ValueError
        inflater = zlib.decompressobj()
        raw = inflater.decompress(compressed, CONFIRM_EXPANDED_LIMIT + 1)
        if len(raw) > CONFIRM_EXPANDED_LIMIT or inflater.unconsumed_tail:
            raise ValueError
        raw += inflater.flush(CONFIRM_EXPANDED_LIMIT + 1 - len(raw))
        if len(raw) > CONFIRM_EXPANDED_LIMIT or not inflater.eof or inflater.unused_data:
            raise ValueError
        decisions = json.loads(raw)
        if type(decisions) is not dict or len(decisions) > 3000:
            raise ValueError
        from ..codec import canonical, uuid
        for row, decision in decisions.items():
            uuid(row)
            if type(decision) is not dict:
                raise ValueError
            canonical(decision)
    except (ValueError, TypeError, zlib.error, json.JSONDecodeError) as error:
        raise ValidationError("The statement decisions are too large or damaged. Review them again.") from error
    return values | _decode(adapter, dict(decisions=decisions))


def _encode_file(_adapter, values):
    data = values["data"]
    if type(data) is not bytes or len(data) > FILE_LIMIT:
        raise ValidationError("This statement file is too large to synchronize.")
    chunks = [base64.b64encode(data[offset:offset + CHUNK_BYTES]).decode("ascii")
              for offset in range(0, len(data), CHUNK_BYTES)]
    return values | {"data": chunks}


def _decode_file(_adapter, values):
    chunks = values["data"]
    try:
        if type(chunks) is not list or len(chunks) > 16 or any(type(part) is not str or len(part) > 4000 for part in chunks):
            raise ValueError
        data = b"".join(base64.b64decode(part, validate=True) for part in chunks)
        if len(data) > FILE_LIMIT:
            raise ValueError
    except (ValueError, TypeError) as error:
        raise ValidationError("This statement file is too large or damaged.") from error
    return values | {"data": data}


def _legacy_stage(c, **values):
    return c.bank_imports.stage(**values)


def _legacy_confirm(c, **values):
    return c.bank_imports.confirm(**values)


COMMANDS = {
    "bank_imports.stage": Command(_legacy_stage, dict(
        account_id=ref("accounts"), filename=TEXT, data=BYTES, mapping=optional(JSON), invert_amount=FLAG),
        creates="bank_import_batches"),
    "bank_imports.confirm": Command(_legacy_confirm, dict(batch_id=ref("bank_import_batches"), decisions=JSON),
                                    target=BATCH, encode=_encode, decode=_decode),
    # Callable aliases preserve the prior wire forms while current app service calls select these bounded forms.
    "bank_imports.stage_chunked": Command("bank_imports.stage", dict(
        account_id=ref("accounts"), filename=TEXT, data=JSON, mapping=optional(JSON), invert_amount=FLAG),
        creates="bank_import_batches", encode=_encode_file, decode=_decode_file),
    "bank_imports.confirm_packed": Command("bank_imports.confirm", dict(
        batch_id=ref("bank_import_batches"), decisions=JSON), target=BATCH,
        encode=_encode_packed_decisions, decode=_unpack_decisions),
    "bank_imports.discard": Command("bank_imports.discard", dict(batch_id=ref("bank_import_batches")), target=BATCH),
}
