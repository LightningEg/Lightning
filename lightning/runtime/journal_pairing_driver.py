"""The one joining-side pairing driver, shared by nearby pairing and first-replica enrollment.

A subclass supplies only where the joining state is kept (`_load_join`, `_save`,
`_clear_join`), its identity and exchange, and whether an encrypted copy is already
being installed (`_installing`). The behaviour is decided here, once (owner,
2026-11-02): resume asks the home for status while proving or waiting; compare
checks the offer's life before the failed flag; cancel and finish need a
started pairing.
"""
from __future__ import annotations

import hmac

from lightning.sync.journal.codec import JournalError
from lightning.sync.journal.pairing import require_live_offer
from lightning.sync.journal import pairing_client

NOT_STARTED = "Choose a nearby device and enter its number first"


class JoiningDriver:
    identity = None
    client_factory = None

    def _load_join(self):
        raise NotImplementedError

    def _save_join(self, state):
        raise NotImplementedError

    def _clear_join(self):
        raise NotImplementedError

    def _installing(self):
        return False

    def _started(self):
        state = self._load_join()
        if not state:
            raise JournalError(NOT_STARTED)
        return state

    def _exchange(self, state):
        candidate = state["candidate"]
        return self.client_factory(candidate["endpoint"], candidate["certificate"], timeout=5)

    async def resume(self):
        state = self._started()
        if state["stage"] == "handshake":
            await pairing_client.handshake(state, self.identity, self._exchange(state), self._save_join)
        elif state["stage"] in ("proving", "waiting"):
            await pairing_client.status(state, self.identity, self._exchange(state), self._save_join)
        elif state["stage"] == "cancelling":
            await self.cancel()

    def compare(self, digits):
        """The joining user's confirmation that the home shows the same digits. Nothing leaves the device here."""
        state = self._started()
        require_live_offer(state["candidate"])
        if state.get("failed"):
            raise JournalError("Compare the numbers again: cancel and start a new pairing")
        if state["stage"] != "compare":
            raise JournalError("This step is already done")
        if type(digits) is not str or not hmac.compare_digest(digits, state["digits"]):
            self._save_join(dict(state, failed=True))
            raise JournalError("Check that both devices show the same six digits")
        self._save_join(dict(state, stage="password"))

    async def prove(self, password):
        state = self._started()
        await pairing_client.prove(state, self.identity, password, self._exchange(state), self._save_join)

    async def cancel(self):
        state = self._started()
        if self._installing():
            raise JournalError("Resume the encrypted copy installation before cancelling")
        await pairing_client.cancel(state, self.identity, self._exchange(state), self._save_join)
        self._clear_join()
