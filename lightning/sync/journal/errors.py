"""Journal error classes shared by the transports, so no module imports another's inside a function.

`codec.JournalError` stays the root; the old homes (`cloud`, `local`, `finance`) re-export these names.
"""
from __future__ import annotations

from .codec import JournalError


class CloudUnavailable(JournalError):
    """Transient carrier failure. The caller retains every durable source."""


class HomeRefused(CloudUnavailable):
    """The home answered that it cannot take this request now (frozen, full); retry later."""


class MembershipUpdateRequired(JournalError):
    """Fetch the signed individual key wrap using saved device credentials."""


class CatchupPaused(JournalError):
    """This bounded wake-up ended; resume from its already durable cursor."""


class UploadHeld(JournalError):
    """Downloads finished, but the home would not take every pending edit yet; they stay pending."""


class ChunksMissing(JournalError):
    """A chunked commit waits for these chunk hashes; nothing was applied."""
    def __init__(self, missing):
        super().__init__("Effect chunks are still arriving")
        self.missing = missing
