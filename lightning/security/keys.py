"""The keys of an encrypted profile: one random data key, two locks on it, and two checks.

Owner decision 2026-10-05 (Architecture › Desktop app and encrypted profiles):

- The database and its backups use only the data key: 32 random bytes nobody types.
- Lock 1 wraps the data key with the password. Lock 2 wraps it with the 12-digit recovery key and the
  security answer together, so a found key alone opens nothing. Both are slow Argon2id checks.
- The answer and recovery checks are HMACs under the data key: they confirm a second proof once the
  profile is open, and give nothing to someone guessing from copied files.

The key file (`keys.json`) holds both locks, the question and the checks. Rules about which proofs a
change needs live in `lightning.runtime.session`; this module only makes and opens the locks.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

_KEY_ID_DOMAIN = b"lightning/key-id/v1"
_ANSWER_CHECK_DOMAIN = b"lightning/answer-check/v1"
_RECOVERY_CHECK_DOMAIN = b"lightning/recovery-check/v1"

# Lock 1 (password) runs at every unlock; lock 2 (recovery) only when recovering, so it can afford to be
# slower. The parser accepts only bounded costs, so a malformed file cannot ask for unbounded memory or
# CPU before it is authenticated.
ARGON2_MEMORY_KIB = 131072
ARGON2_ITERATIONS = 4
RECOVERY_MEMORY_KIB = 262144
RECOVERY_ITERATIONS = 8
ARGON2_LANES = 4
_ARGON2_MEMORY_MIN_KIB = 32768
_ARGON2_MEMORY_MAX_KIB = 262144
_ARGON2_ITERATIONS_MIN = 2
_ARGON2_ITERATIONS_MAX = 10
_ARGON2_LANES_MIN = 1
_ARGON2_LANES_MAX = 4
_PASSWORD_MAX_BYTES = 4096
_MAX_DOCUMENT_BYTES = 16384
_SLOT_METADATA_KEYS = {"version", "type", "key_id", "kdf", "cipher", "salt", "nonce",
                       "memory_kib", "iterations", "lanes"}
_SLOT_KEYS = _SLOT_METADATA_KEYS | {"ciphertext"}
_FILE_KEYS = {"version", "key_id", "password", "recovery", "question", "answer_check", "recovery_check"}
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")

RECOVERY_DIGITS = 12
QUESTION_MAX_CHARS = 200
_ANSWER_MAX_CHARS = 200
# Arabic-Indic and Eastern Arabic-Indic digits type the same as Western ones.
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "0123456789" * 2)
# Arabic spelling variants that people write either way: alef forms, taa marbuta, alef maqsura.
_ARABIC_VARIANTS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي"})
_ARABIC_MARKS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")  # tashkeel and tatweel

SUGGESTED_QUESTIONS = (
    "What was the name of your first school?",
    "In which city did your parents meet?",
    "What was the name of your first pet?",
    "What is the name of the street you grew up on?",
)


# ------------------------------------------------------------------ the data key and its identity
def new_data_key() -> bytes:
    return os.urandom(32)


def key_id(key: bytes) -> str:
    """Return a non-secret 64-bit identifier for matching encrypted data and its key file."""
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError("The data key must be exactly 32 bytes.")
    return hmac.new(key, _KEY_ID_DOMAIN, hashlib.sha256).hexdigest()[:16]


# ------------------------------------------------------------------ what people type
def new_recovery_key() -> str:
    """Twelve random digits, shown in groups of four: 1234-5678-9012."""
    digits = f"{secrets.randbelow(10 ** RECOVERY_DIGITS):0{RECOVERY_DIGITS}d}"
    return "-".join(digits[index:index + 4] for index in range(0, RECOVERY_DIGITS, 4))


def normalize_recovery_key(text: str) -> str:
    """The twelve digits, whatever spacing, dashes or digit script they were typed with."""
    if not isinstance(text, str) or len(text) > 64:
        raise ValueError("A recovery key is 12 digits.")
    digits = "".join(char for char in text.translate(_DIGITS) if char not in " -\t\r\n._")
    if len(digits) != RECOVERY_DIGITS or not all("0" <= char <= "9" for char in digits):
        raise ValueError("A recovery key is 12 digits.")
    return digits


def normalize_answer(text: str) -> str:
    """Case, spaces, punctuation, Arabic letter variants and marks, and digit script are ignored."""
    if not isinstance(text, str) or len(text) > _ANSWER_MAX_CHARS:
        raise ValueError(f"Keep the answer under {_ANSWER_MAX_CHARS} characters.")
    value = unicodedata.normalize("NFKC", text).translate(_DIGITS).casefold()
    value = _ARABIC_MARKS.sub("", value).translate(_ARABIC_VARIANTS)
    value = "".join(char for char in value if not unicodedata.category(char).startswith("P"))
    value = " ".join(value.split())
    if not value:
        raise ValueError("Type an answer to your security question.")
    return value


def clean_question(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("Type a security question.")
    value = " ".join(text.split())
    if not value or len(value) > QUESTION_MAX_CHARS:
        raise ValueError(f"Type a security question of 1–{QUESTION_MAX_CHARS} characters.")
    return value


@lru_cache(maxsize=1)
def _words() -> tuple[str, ...]:
    words = tuple(Path(__file__).with_name("wordlist_en.txt").read_text("utf-8").split())
    if len(words) != 2048 or len(set(words)) != 2048:
        raise RuntimeError("The password word list is damaged.")
    return words


def suggest_password() -> str:
    """Four random words from a 2048-word list (44 bits), easy to type and remember."""
    return " ".join(secrets.choice(_words()) for _ in range(4))


def _password_bytes(password: str) -> bytes:
    if not isinstance(password, str):
        raise ValueError("Password must be text.")
    try:
        encoded = password.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("Password is not valid UTF-8 text.") from exc
    if not 1 <= len(encoded) <= _PASSWORD_MAX_BYTES:
        raise ValueError("Type a password.")
    return encoded


# ------------------------------------------------------------------ one lock
def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _decode_b64(value: Any, expected_length: int, label: str) -> bytes:
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError(f"Invalid {label} encoding.")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid {label} encoding.") from exc
    if len(decoded) != expected_length:
        raise ValueError(f"Invalid {label} length.")
    return decoded


def _metadata(document: dict[str, Any]) -> dict[str, Any]:
    return {name: document[name] for name in _SLOT_METADATA_KEYS}


def _validate_slot(document: dict[str, Any], kind: str) -> tuple[bytes, bytes, bytes]:
    if not isinstance(document, dict) or set(document) != _SLOT_KEYS:
        raise ValueError("Invalid key slot fields.")
    if document["version"] != 1 or type(document["version"]) is not int:
        raise ValueError("Unsupported key slot version.")
    if document["type"] != kind or document["cipher"] != "aes-256-gcm" or document["kdf"] != "argon2id":
        raise ValueError("Unsupported key slot type or algorithm.")
    kid = document["key_id"]
    if not isinstance(kid, str) or not re.fullmatch(r"[0-9a-f]{16}", kid):
        raise ValueError("Invalid key identifier.")
    memory, iterations, lanes = document["memory_kib"], document["iterations"], document["lanes"]
    if type(memory) is not int or not _ARGON2_MEMORY_MIN_KIB <= memory <= _ARGON2_MEMORY_MAX_KIB:
        raise ValueError("Argon2 memory cost is outside the supported bounds.")
    if type(iterations) is not int or not _ARGON2_ITERATIONS_MIN <= iterations <= _ARGON2_ITERATIONS_MAX:
        raise ValueError("Argon2 iteration count is outside the supported bounds.")
    if type(lanes) is not int or not _ARGON2_LANES_MIN <= lanes <= _ARGON2_LANES_MAX:
        raise ValueError("Argon2 lane count is outside the supported bounds.")
    salt = _decode_b64(document["salt"], 16, "salt")
    nonce = _decode_b64(document["nonce"], 12, "nonce")
    ciphertext = _decode_b64(document["ciphertext"], 48, "ciphertext")
    return salt, nonce, ciphertext


def _lock(key: bytes, secret: bytes, kind: str, memory_kib: int, iterations: int,
          context: bytes = b"") -> dict[str, Any]:
    """Wrap the data key under a slow key from `secret`. `context` is authenticated with the lock."""
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError("The data key must be exactly 32 bytes.")
    salt, nonce = os.urandom(16), os.urandom(12)
    document: dict[str, Any] = {
        "version": 1, "type": kind, "key_id": key_id(key), "kdf": "argon2id", "cipher": "aes-256-gcm",
        "salt": base64.b64encode(salt).decode("ascii"), "nonce": base64.b64encode(nonce).decode("ascii"),
        "memory_kib": memory_kib, "iterations": iterations, "lanes": ARGON2_LANES,
    }
    kek = Argon2id(salt=salt, length=32, iterations=iterations, lanes=ARGON2_LANES,
                   memory_cost=memory_kib).derive(secret)
    document["ciphertext"] = base64.b64encode(
        AESGCM(kek).encrypt(nonce, key, _canonical(document) + context)).decode("ascii")
    return document


def _unlock(document: dict[str, Any], secret: bytes, kind: str, context: bytes = b"") -> bytes:
    salt, nonce, ciphertext = _validate_slot(document, kind)
    kek = Argon2id(salt=salt, length=32, iterations=document["iterations"],
                   lanes=document["lanes"], memory_cost=document["memory_kib"]).derive(secret)
    try:
        key = AESGCM(kek).decrypt(nonce, ciphertext, _canonical(_metadata(document)) + context)
    except InvalidTag as exc:
        raise ValueError("Key slot authentication failed.") from exc
    if len(key) != 32 or not hmac.compare_digest(key_id(key), document["key_id"]):
        raise ValueError("Key slot identifier does not match.")
    return key


def wrap_key(key: bytes, password: str) -> dict[str, Any]:
    """Lock 1 alone: the data key wrapped by a password."""
    return _lock(key, _password_bytes(password), "password", ARGON2_MEMORY_KIB, ARGON2_ITERATIONS)


def _recovery_secret(recovery_key: str, answer: str) -> bytes:
    return normalize_recovery_key(recovery_key).encode("ascii") + b"\x00" + normalize_answer(answer).encode("utf-8")


def _check(key: bytes, domain: bytes, value: str) -> str:
    return hmac.new(key, domain + value.encode("utf-8"), hashlib.sha256).hexdigest()


# ------------------------------------------------------------------ the key file
def create_key_file(key: bytes, password: str, recovery_key: str, question: str, answer: str) -> dict[str, Any]:
    """Both locks, the question and the checks for a data key."""
    question = clean_question(question)
    return {
        "version": 2,
        "key_id": key_id(key),
        "password": wrap_key(key, password),
        "recovery": _lock(key, _recovery_secret(recovery_key, answer), "recovery",
                          RECOVERY_MEMORY_KIB, RECOVERY_ITERATIONS, question.encode("utf-8")),
        "question": question,
        "answer_check": _check(key, _ANSWER_CHECK_DOMAIN, normalize_answer(answer)),
        "recovery_check": _check(key, _RECOVERY_CHECK_DOMAIN, normalize_recovery_key(recovery_key)),
    }


def validate_key_file(document: dict[str, Any]) -> None:
    if not isinstance(document, dict) or set(document) != _FILE_KEYS:
        raise ValueError("Invalid key file fields.")
    try:
        encoded_size = len(_canonical(document))
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ValueError("Invalid key file.") from exc
    if encoded_size > _MAX_DOCUMENT_BYTES:
        raise ValueError("Key file is too large.")
    if document["version"] != 2 or type(document["version"]) is not int:
        raise ValueError("Unsupported key file version.")
    if clean_question(document["question"]) != document["question"]:
        raise ValueError("Invalid security question.")
    for name in ("answer_check", "recovery_check"):
        if not isinstance(document[name], str) or _HEX64.fullmatch(document[name]) is None:
            raise ValueError("Invalid key file check.")
    _validate_slot(document["password"], "password")
    _validate_slot(document["recovery"], "recovery")
    if not document["password"]["key_id"] == document["recovery"]["key_id"] == document["key_id"]:
        raise ValueError("The key file's locks belong to different keys.")


def unwrap_key(document: dict[str, Any], password: str) -> bytes:
    """Open lock 1: a key file (or a lone password lock) and its password give the data key."""
    passphrase = _password_bytes(password)
    if isinstance(document, dict) and document.get("version") == 2:
        validate_key_file(document)
        document = document["password"]
    return _unlock(document, passphrase, "password")


def open_with_recovery(document: dict[str, Any], recovery_key: str, answer: str) -> bytes:
    """Open lock 2: the recovery key and the answer together give the data key."""
    validate_key_file(document)
    return _unlock(document["recovery"], _recovery_secret(recovery_key, answer), "recovery",
                   document["question"].encode("utf-8"))


def proof_kind(document: dict[str, Any], key: bytes, proof: str) -> str | None:
    """With the profile open, say whether `proof` is its security answer or recovery key (None if neither)."""
    validate_key_file(document)
    if not hmac.compare_digest(key_id(key), document["key_id"]):
        raise ValueError("The key file belongs to a different key.")
    try:
        if hmac.compare_digest(_check(key, _RECOVERY_CHECK_DOMAIN, normalize_recovery_key(proof)),
                               document["recovery_check"]):
            return "recovery"
    except ValueError:
        pass
    try:
        if hmac.compare_digest(_check(key, _ANSWER_CHECK_DOMAIN, normalize_answer(proof)), document["answer_check"]):
            return "answer"
    except ValueError:
        pass
    return None


def with_password(document: dict[str, Any], key: bytes, password: str) -> dict[str, Any]:
    validate_key_file(document)
    return {**document, "password": wrap_key(key, password)}


def with_question(document: dict[str, Any], key: bytes, recovery_key: str, question: str,
                  answer: str) -> dict[str, Any]:
    """A new question and answer. Lock 2 needs the recovery key to be rebuilt, so it must be the right one."""
    if proof_kind(document, key, recovery_key) != "recovery":
        raise ValueError("That is not this profile's recovery key.")
    question = clean_question(question)
    return {**document, "question": question,
            "recovery": _lock(key, _recovery_secret(recovery_key, answer), "recovery",
                              RECOVERY_MEMORY_KIB, RECOVERY_ITERATIONS, question.encode("utf-8")),
            "answer_check": _check(key, _ANSWER_CHECK_DOMAIN, normalize_answer(answer))}


def with_recovery_key(document: dict[str, Any], key: bytes, answer: str, recovery_key: str) -> dict[str, Any]:
    """A new recovery key. Lock 2 needs the answer to be rebuilt, so it must be the right one."""
    if proof_kind(document, key, answer) != "answer":
        raise ValueError("That is not the answer to this profile's security question.")
    return {**document,
            "recovery": _lock(key, _recovery_secret(recovery_key, answer), "recovery",
                              RECOVERY_MEMORY_KIB, RECOVERY_ITERATIONS, document["question"].encode("utf-8")),
            "recovery_check": _check(key, _RECOVERY_CHECK_DOMAIN, normalize_recovery_key(recovery_key))}
