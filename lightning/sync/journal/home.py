"""Single-home confirmation and a separate idempotent review lane for dummy data."""
from __future__ import annotations

from functools import wraps

from .codec import (JournalError, authenticate, canonical, digest, origin_id,
                    proposal, seal, unpack, uuid)
from .store import JournalStore, _commit

MAX_GAP = 256
MAX_STAGED = 1024


def _confirmation(method):
    @wraps(method)
    def protected(self, *args, **kwargs):
        with self.store.confirming():
            return method(self, *args, **kwargs)
    return protected


class JournalHome:
    def __init__(self, store: JournalStore, signer, *, fault=lambda phase: None):
        if store.config["role"] != "home":
            raise JournalError("Only the home confirms proposals")
        self.store, self.db, self.signer, self.fault = store, store.db, signer, fault
        self._inherit()

    def _require_upgrade_complete(self):
        if self.db.has_table("journal_local"):
            pending = self.db.scalar(
                "SELECT name FROM journal_local WHERE name IN ('upgrade_barrier','cutover_normalization') LIMIT 1",
            )
            if pending is not None:
                raise JournalError("Journal cutover or schema upgrade is incomplete; confirmation stays locked")

    def _inherit(self):
        """Signed commits are receipts too: a home that took over from a lost or
        moved predecessor answers a resent prefix proposal with its original
        decision, and each origin resumes after its last decided sequence."""
        decided = {}
        with self.db.transaction():
            for row in self.db.all("SELECT proposal_id,wire FROM journal_commits"):
                device, incarnation, seq = row["proposal_id"].split("/")
                decided.setdefault((device, incarnation), set()).add(int(seq))
                stale = self.db.one("SELECT status FROM journal_inbox WHERE proposal_id=? AND status IN ('staged','review')", (row["proposal_id"],))
                if stale:
                    body = unpack(bytes(row["wire"]))["body"]
                    self.db.execute("UPDATE journal_inbox SET status=?,reason=?,review_token=NULL WHERE proposal_id=?",
                                    (body["outcome"], body["reason"], row["proposal_id"]))
            for member in self.db.all("SELECT device,incarnation,progress FROM journal_origins"):
                progress, seqs = member["progress"], decided.get((member["device"], member["incarnation"]), set())
                while progress + 1 in seqs:
                    progress += 1
                if progress != member["progress"]:
                    self.db.execute("UPDATE journal_origins SET progress=? WHERE device=? AND incarnation=?",
                                    (progress, member["device"], member["incarnation"]))

    def approve_origin(self, device, incarnation, public_key):
        """Laboratory enrollment only; production pairing must authenticate this."""
        from cryptography.hazmat.primitives.asymmetric import ec
        uuid(device)
        uuid(incarnation)
        try:
            ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(public_key))
        except (ValueError, TypeError) as error:
            raise JournalError("Invalid origin public key") from error
        with self.db.transaction():
            existing = self.db.one("SELECT public_key,revoked FROM journal_origins WHERE device=? AND incarnation=?",
                                   (device, incarnation))
            if existing:
                if existing["public_key"] != public_key or existing["revoked"]:
                    raise JournalError("Origin identity cannot be replaced or revived")
                return
            self.db.execute("INSERT INTO journal_origins(device,incarnation,public_key) VALUES(?,?,?)",
                            (device, incarnation, public_key))
        self._inherit()

    def revoke_origin(self, device, incarnation):
        """Local admission gate only, not production transport-key revocation."""
        with self.db.transaction():
            self.db.execute("UPDATE journal_origins SET revoked=1 WHERE device=? AND incarnation=?", (device, incarnation))

    @_confirmation
    def receive(self, wire):
        self._require_upgrade_complete()
        self.store.require_confirmation_authority()
        envelope = unpack(wire)
        body = envelope["body"]
        # Only inspect bounded routing identity before authenticating financial contents.
        if type(body) is not dict or type(body.get("origin")) is not dict:
            raise JournalError("Missing origin")
        identity = body["origin"]
        identifier = origin_id(identity)
        with self.db.transaction():
            member = self.db.one("SELECT * FROM journal_origins WHERE device=? AND incarnation=?",
                                 (identity["device"], identity["incarnation"]))
            if member is None or member["revoked"]:
                raise JournalError("Origin is not currently trusted")
            authenticate(envelope, member["public_key"])
            proposal(body)
            if not body["kind"].startswith("dummy.") and self.store.adapter is None:
                raise JournalError("Unsupported financial adapter")
            if self.store.adapter is not None and not self.store.adapter.supports(body["kind"]):
                raise JournalError("Unsupported financial entry kind")
            if self.store.adapter is not None and not body["kind"].endswith(".delete"):
                self.store.adapter.check(body["kind"], body["groups"], complete=body["kind"].endswith(".add"))
            retired = (body["generation"] != self.store.config["generation"] and self.store.authority is not None
                       and self.store.authority.admits_original(body))
            if not retired:
                self.store._scope(body)
                self.store._check_cursor(body["cursor"])
            payload_hash = digest(body)
            known = self.db.one("SELECT hash,status FROM journal_inbox WHERE proposal_id=?", (identifier,))
            if known is None:
                inherited = self.db.scalar("SELECT wire FROM journal_commits WHERE proposal_id=?", (identifier,))
                if inherited is not None:
                    receipt = unpack(bytes(inherited))["body"]
                    known = dict(hash=receipt["proposal_hash"], status=receipt["outcome"])
            if known:
                if known["hash"] != payload_hash:
                    raise JournalError("Proposal identity reused with different content")
                return known["status"]
            if identity["seq"] <= member["progress"]:
                raise JournalError("Missing receipt below origin progress; repair required")
            if identity["seq"] > member["progress"] + MAX_GAP:
                raise JournalError("Sequence gap exceeds staging window")
            if self.db.scalar("SELECT COUNT(*) FROM journal_inbox WHERE status IN ('staged','review')") >= MAX_STAGED:
                raise JournalError("Staging capacity reached; retain the edit on its origin")
            self.db.execute("INSERT INTO journal_inbox VALUES(?,?,?,?,?,?,'staged','queued',NULL)",
                            (identifier, identity["device"], identity["incarnation"], identity["seq"], payload_hash, wire))
            self.fault("inbox_inserted")
        self.fault("inbox_committed")
        return "staged"

    @_confirmation
    def process(self, *, limit=None):
        """Drain eligible work; a review blocks its origin, never other origins."""
        self._require_upgrade_complete()
        self.store.require_confirmation_authority()
        if limit is not None and (type(limit) is not int or not 1 <= limit <= MAX_STAGED):
            raise JournalError("Invalid confirmation work budget")
        committed = []
        while True:
            progressed = False
            members = self.db.all("SELECT * FROM journal_origins WHERE revoked=0 ORDER BY device,incarnation")
            for member in members:
                with self.db.transaction():
                    row = self.db.one("SELECT * FROM journal_inbox WHERE device=? AND incarnation=? AND seq=?",
                                      (member["device"], member["incarnation"], member["progress"] + 1))
                    if row is None or row["status"] != "staged":
                        continue
                    body = unpack(bytes(row["wire"]))["body"]
                    try:
                        with self.db.transaction():
                            result = self._consider(body)
                            if result[0] in ("wait", "review"):
                                wire = None
                            else:
                                wire = self._finish(row, *result)
                    except Exception as error:
                        if ((isinstance(error, self.db.driver.DatabaseError)
                             and not isinstance(error, self.db.driver.IntegrityError))
                                or not self.db.conn.in_transaction):
                            raise  # Storage failure: stop, keep everything for retry.
                        result = ("review", "home-error")
                    if result[0] == "wait":
                        continue
                    if result[0] == "review":
                        # Only this origin waits; others keep confirming, even when the comparison itself fails.
                        try:
                            token = self._review_token(row)
                        except Exception as error:
                            if (isinstance(error, self.db.driver.DatabaseError)
                                    and not isinstance(error, self.db.driver.IntegrityError)):
                                raise
                            token = None
                        self.db.execute("UPDATE journal_inbox SET status='review',reason=?,review_token=? WHERE proposal_id=?",
                                        (result[1], token, row["proposal_id"]))
                        continue
                # Nothing escapes the transaction before it is durably committed.
                self.fault("decision_committed")
                committed.append(wire)
                if limit is not None and len(committed) >= limit:
                    return committed
                progressed = True
            if not progressed:
                return committed

    def _consider(self, body, *, force=False):
        if body["kind"].startswith("command."):
            return self._consider_command(body, force=force)
        dependencies = []
        for dependency in body["dependencies"]:
            row = self.status(origin_id(dependency))
            if row is not None and row["status"] == "rejected":
                return "rejected", "dependency-rejected", []
            if row is None or row["status"] not in {"accepted", "accepted-as-existing"}:
                return "wait", "dependency", []
            commit = self._decision(origin_id(dependency))
            for effect in unpack(commit)["body"]["effects"]:
                dependencies.append(effect | {"record": effect["alias"]} if "alias" in effect else effect)
        current = self.store.record(body["record"])
        if current and current["deleted"]:
            return "rejected", "deleted", []
        if body["kind"].endswith(".add"):
            if current:
                return "rejected", "record-exists", []
            if any(value is not None for value in body["bases"].values()):
                raise JournalError("An addition cannot have existing base tokens")
            groups, tokens = {}, {}
        else:
            if current is None:
                return "rejected", "missing-record", []
            groups, tokens = dict(current["groups"]), dict(current["tokens"])
            bases = dict(body["bases"])
            for group, base in bases.items():
                if base is None:
                    inherited = {effect["tokens"][group] for effect in dependencies
                                 if self.store.resolve(effect["record"]) == self.store.resolve(body["record"]) and group in effect["tokens"]}
                    if len(inherited) > 1:
                        return "review", "conflict", []
                    if inherited:
                        bases[group] = inherited.pop()
            if not force:
                if body["kind"].endswith(".delete") and set(bases) != set(tokens):
                    return "review", "conflict", []
                if any(tokens.get(group) != token for group, token in bases.items()):
                    return "review", "conflict", []
        if body["kind"].endswith(".delete"):
            effect = dict(record=current["record"] if current else body["record"], groups={}, tokens={}, deleted=True)
        else:
            groups.update(body["groups"])
            for group in body["groups"]:
                tokens[group] = digest(dict(proposal=digest(body), group=group))
            effect = dict(record=current["record"] if current else body["record"], groups=groups, tokens=tokens, deleted=False)
        if len(effect["groups"]) > 16:
            return "rejected", "group-limit", []
        if len(canonical(effect)) > 48 * 1024:
            return "rejected", "effect-too-large", []
        if not force and self.store.adapter is not None and body["kind"].endswith(".add"):
            matches = self.store.adapter.matches(body)
            if matches:
                if matches[0]["proven"]:
                    return "accepted-as-existing", "existing", [dict(record=body["record"], groups={}, tokens=matches[0]["tokens"], deleted=False, alias=matches[0]["record"])]
                return "review", "possible-duplicate", []
        return "accepted", "accepted", [effect]

    def _consider_command(self, body, *, force=False):
        """A command waits for review when its target row changed since the
        device saw it; an earlier pending command of its own is its base."""
        from .commands import command, selection_token, target_slot
        if ((body["kind"].startswith("command.automation.") or body["kind"] == "command.undo.replay")
                and (body["origin"]["device"] != self.store.config["device"]
                     or body["origin"]["incarnation"] != self.store.config["incarnation"])):
            return "rejected", "home-only", []
        for dependency in body["dependencies"]:
            state = self.status(origin_id(dependency))
            if state is not None and state["status"] == "rejected":
                return "rejected", "dependency-rejected", []
            if state is None or state["status"] not in {"accepted", "accepted-as-existing"}:
                return "wait", "dependency", []
        slot = target_slot(body["kind"], body["groups"])
        base = body["bases"]["args"]
        creates = command(body["kind"]).creates
        if slot is None and creates:
            if self.store.adapter.row_token(creates + ":" + canonical(body["record"]).decode()):
                return "rejected", "record-exists", []
        elif slot is not None and not force and not (base is None and body["dependencies"]) and self.store.adapter.row_token(slot) != base:
            # No base and no pending predecessor means the device saw no such row.
            return "review", "conflict", []
        elif (command(body["kind"]).targets and not force and not (base is None and body["dependencies"])
              and selection_token(self.store.adapter, body["kind"], body["groups"]) != base):
            return "review", "conflict", []  # A selected row changed since the device saw it.
        return "accepted", "accepted", [dict(record=body["record"], groups={}, tokens={}, deleted=False)]

    def _finish(self, row, outcome, reason, effects):
        if outcome not in {"accepted", "accepted-as-existing", "rejected"}:
            raise JournalError("Only terminal decisions advance origin progress")
        if effects and self.store.adapter is not None and outcome == "accepted":
            from lightning.core.errors import LightningError as ValidationError
            try:
                with self.db.transaction():
                    domain = self.store.adapter.confirm(unpack(bytes(row["wire"]))["body"], effects[0])
                    if domain is not None:  # None: a command that found nothing to change.
                        effects[0]["domain"] = domain
                    if len(canonical(effects[0])) > 48 * 1024:
                        raise ValidationError("The confirmed action exceeds the effect limit")
            except ValidationError as error:
                self.store.adapter.refused(unpack(bytes(row["wire"]))["body"], error)
                outcome, reason, effects = "rejected", "financial-validation", []
        proposal_body = unpack(bytes(row["wire"]))["body"]
        if effects and self.store.adapter is not None and proposal_body["kind"].endswith(".add") and proposal_body["groups"].get("source"):
            effects[0]["source"] = proposal_body["groups"]["source"] | {"hash": self.store.adapter.source_token(proposal_body["groups"]["money"])}
        for effect in effects:
            self.store._put_record(effect)
        self.fault("home_effects")
        current = self.store.cursor()
        body = dict(version=2, type="commit", profile=self.store.config["profile"],
                    generation=self.store.config["generation"], revision=current["revision"] + 1,
                    previous=current["hash"], proposal_id=row["proposal_id"], proposal_hash=row["hash"],
                    outcome=outcome, reason=reason, effects=effects, fingerprint=self.store.fingerprint())
        _commit(body)
        wire = seal(body, self.signer)
        authenticate(unpack(wire), self.store.config["home_key"])
        self.db.execute("INSERT INTO journal_commits VALUES(?,?,?,?)", (body["revision"], digest(body), body["proposal_id"], wire))
        self.db.execute("UPDATE journal_inbox SET status=?,reason=?,review_token=NULL WHERE proposal_id=?",
                        (outcome, reason, row["proposal_id"]))
        self.db.execute("UPDATE journal_origins SET progress=? WHERE device=? AND incarnation=?",
                        (row["seq"], row["device"], row["incarnation"]))
        own = self.db.one("SELECT wire FROM journal_outbox WHERE proposal_id=?", (row["proposal_id"],))
        if own:
            if digest(unpack(bytes(own[0]))["body"]) != row["hash"]:
                raise JournalError("Decision does not match local proposal")
            self.db.execute("UPDATE journal_outbox SET decision=? WHERE proposal_id=?", (wire, row["proposal_id"]))
        self.fault("home_receipt")
        return wire

    def _decision(self, proposal_id):
        # Receipt payloads are retained in this milestone; no compaction yet.
        row = self.db.one("SELECT wire FROM journal_commits WHERE proposal_id=?", (proposal_id,))
        if row:
            return bytes(row[0])
        raise JournalError("Missing committed receipt; repair required")

    def status(self, proposal_id):
        row = self.db.one("SELECT status,reason FROM journal_inbox WHERE proposal_id=?", (proposal_id,))
        if row:
            return dict(row)
        inherited = self.db.scalar("SELECT wire FROM journal_commits WHERE proposal_id=?", (proposal_id,))
        if inherited is None:
            return None
        body = unpack(bytes(inherited))["body"]
        return dict(status=body["outcome"], reason=body["reason"])

    def decision(self, proposal_id):
        """Return the original signed terminal decision, including after restart."""
        state = self.status(proposal_id)
        if state is None or state["status"] not in {"accepted", "accepted-as-existing", "rejected"}:
            return None
        return self._decision(proposal_id)

    def _review_token(self, row):
        body = unpack(bytes(row["wire"]))["body"]
        if body["kind"].startswith("command.") and self.store.adapter is not None:
            # Commands may change keyed rows or a selection rather than a cash
            # register record. Bind approval to the confirmed ledger actually
            # displayed; a later write must force a fresh review.
            return digest(dict(proposal=row["hash"], fingerprint=self.store.fingerprint()))
        matches = self.store.adapter.matches(body) if self.store.adapter is not None else []
        return digest(dict(proposal=row["hash"], current=self.store.record(body["record"]), matches=matches))

    def review_state(self, proposal_id):
        with self.db.transaction():
            row = self.db.one("SELECT * FROM journal_inbox WHERE proposal_id=? AND status='review'", (proposal_id,))
            if row is None:
                raise JournalError("Proposal is not waiting for review")
            body = unpack(bytes(row["wire"]))["body"]
            token = self._review_token(row)
            self.db.execute("UPDATE journal_inbox SET review_token=? WHERE proposal_id=?", (token, proposal_id))
            base = {}
            expected = dict(body["bases"])
            for dependency in body["dependencies"]:
                state = self.status(origin_id(dependency))
                if state and state["status"] in {"accepted", "accepted-as-existing"}:
                    for effect in unpack(self._decision(origin_id(dependency)))["body"]["effects"]:
                        for group in expected:
                            if expected[group] is None and group in effect["tokens"]:
                                expected[group] = effect["tokens"][group]
            for commit in self.db.all("SELECT wire FROM journal_commits ORDER BY revision DESC"):
                for effect in unpack(bytes(commit[0]))["body"]["effects"]:
                    if self.store.resolve(effect["record"]) == self.store.resolve(body["record"]):
                        for group, value in effect["groups"].items():
                            if group not in base and expected.get(group) == effect["tokens"].get(group):
                                base[group] = value
            return dict(proposal_id=proposal_id, token=token, proposed=body,
                        current=self.store.record(body["record"]), base=base,
                        matches=self.store.adapter.matches(body) if self.store.adapter is not None else [])

    @_confirmation
    def review(self, *, command_id, proposal_id, token, choice, existing=None):
        """Called only by the local home in the lab; not a network control endpoint."""
        uuid(command_id)
        if type(choice) is not str or choice not in {"apply", "reject", "link"}:
            raise JournalError("Invalid review choice")
        request_hash = digest(dict(proposal_id=proposal_id, token=token, choice=choice, existing=existing))
        with self.db.transaction():
            known = self.db.one("SELECT request_hash,result FROM journal_reviews WHERE command_id=?", (command_id,))
            if known:
                if request_hash != known["request_hash"]:
                    raise JournalError("Review identity reused with different content")
                return bytes(known["result"])
            row = self.db.one("SELECT * FROM journal_inbox WHERE proposal_id=? AND status='review'", (proposal_id,))
            if row is None or token != self._review_token(row):
                raise JournalError("Review changed; refresh before choosing")
            member = self.db.one("SELECT revoked FROM journal_origins WHERE device=? AND incarnation=?",
                                 (row["device"], row["incarnation"]))
            if member is None or member[0]:
                raise JournalError("Origin is not currently trusted")
            proposal_body = unpack(bytes(row["wire"]))["body"]
            if choice == "link":
                matches = self.store.adapter.matches(proposal_body) if self.store.adapter else []
                if existing not in {match["record"] for match in matches if not match.get("collision")}:
                    raise JournalError("Refresh the duplicate comparison before linking")
                matched = next(match for match in matches if match["record"] == existing)
                result = ("accepted-as-existing", "existing", [dict(record=proposal_body["record"], groups={}, tokens=matched["tokens"], deleted=False, alias=existing)])
            else:
                result = self._consider(proposal_body, force=True) if choice == "apply" else ("rejected", "cancelled", [])
            wire = self._finish(row, *result)
            self.db.execute("INSERT INTO journal_reviews VALUES(?,?,?)", (command_id, request_hash, wire))
            self.fault("review_receipt")
        self.fault("review_committed")
        return wire
