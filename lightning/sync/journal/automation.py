"""Durable home-only scheduler for automatic financial service work.

Jobs are issued as ordinary signed commands. The home executes them under the
normal journal confirmation transaction and publishes exact synchronized rows;
replicas never run this scheduler or the underlying services.
"""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid5

from .codec import JournalError, canonical, origin_id, unpack
from .effects import CHUNK_BYTES, MAX_CHUNKS

_ACTIONS = {
    "automation.fill_prices",
    "automation.fill_prices_now",
    "automation.process_due",
    "automation.match_bills",
    "automation.mark_live_fetch",
    "automation.apply_live_prices",
}


def _plan_record(work) -> dict:
    def want_record(item):
        return dict(asset_id=item.asset_id, name=item.name, key=item.key, pack=item.pack,
                    month_ends=item.month_ends, purity=format(item.purity, "f"))

    return dict(
        on=work.on, wants=[want_record(item) for item in work.wants],
        rates=[dict(currency=item.currency, days=item.days) for item in work.rates],
        unknown=work.unknown, other_currency=work.other_currency,
        unlinked=[want_record(item) for item in work.unlinked],
        linked={str(key): value for key, value in work.linked.items()},
    )


def _plan_from_record(value):
    from lightning.workflows.live_prices import Plan, RateWant, Want
    expected = {"on", "wants", "rates", "unknown", "other_currency", "unlinked", "linked"}
    if type(value) is not dict or set(value) != expected:
        raise JournalError("Stored live-price plan is malformed")

    def wants(name):
        rows = value[name]
        if type(rows) is not list or len(rows) > 256:
            raise JournalError("Stored live-price plan exceeds its limit")
        result = []
        for row in rows:
            if type(row) is not dict or set(row) != {"asset_id", "name", "key", "pack", "month_ends", "purity"}:
                raise JournalError("Stored live-price request is malformed")
            if type(row["asset_id"]) is not int or type(row["month_ends"]) is not list or len(row["month_ends"]) > 120:
                raise JournalError("Stored live-price request exceeds its limit")
            try:
                purity = Decimal(row["purity"])
                if not purity.is_finite():
                    raise ValueError
            except (InvalidOperation, ValueError, TypeError) as error:
                raise JournalError("Stored live-price purity is invalid") from error
            result.append(Want(row["asset_id"], row["name"], row["key"], row["pack"], row["month_ends"], purity))
        return result

    if type(value["rates"]) is not list or len(value["rates"]) > 32:
        raise JournalError("Stored exchange-rate request exceeds its limit")
    rates = [RateWant(item["currency"], item["days"]) for item in value["rates"]]
    return Plan(value["on"], wants("wants"), rates, value["unknown"], value["other_currency"],
                wants("unlinked"), {int(key): item for key, item in value["linked"].items()})


def apply_live_prices(container, job_key: str):
    row = container.db.one(
        "SELECT payload_json,payload_sha256,state FROM journal_automation_results WHERE job_key=?", (job_key,),
    )
    if row is None or hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest() != row["payload_sha256"]:
        raise JournalError("Fetched prices are missing or damaged; keep the profile for repair")
    if row["state"] == "applied":
        return 0  # A second home command for one fetched result cannot write it twice.
    if row["state"] != "queued":
        raise JournalError("Fetched prices are already being applied or were refused")
    try:
        payload = json.loads(row["payload_json"])
    except (ValueError, TypeError) as error:
        raise JournalError("Fetched prices are malformed; keep the profile for repair") from error
    if set(payload) != {"plan", "found", "failed"} or type(payload["found"]) is not dict:
        raise JournalError("Fetched prices are malformed; keep the profile for repair")
    if type(payload["failed"]) is not list or len(payload["failed"]) > 16:
        raise JournalError("Fetched source status exceeds its limit")
    found = {}
    for identity, closes in payload["found"].items():
        if type(identity) is not str or type(closes) is not dict or len(closes) > 120:
            raise JournalError("Fetched price set exceeds its limit")
        key = identity if identity.startswith("fx:") else int(identity)
        found[key] = {}
        for day, raw in closes.items():
            value = Decimal(raw)
            if not value.is_finite() or len(day) != 10:
                raise JournalError("Fetched price has an invalid value")
            found[key][day] = value
    container.db.execute("UPDATE journal_automation_results SET state='applying' WHERE job_key=?", (job_key,))
    from lightning.workflows.live_prices import save
    return save(container, _plan_from_record(payload["plan"]), found, payload["failed"])


class JournalAutomation:
    """Run due financial automation through the home's normal command path.

    Call ``tick`` on the home loop. Its date-keyed jobs are retryable while
    staged and idempotent after a durable decision.
    """

    def __init__(self, home_device):
        self.device = home_device
        self.store = home_device.store
        if (self.store.config.get("role") != "home" or home_device.home is None
                or home_device.home.store is not self.store
                or home_device.store.config["device"] != home_device.identity.device_id
                or home_device.store.config["origin_key"] != home_device.identity.public_key
                or home_device.store.config["home_key"] != home_device.identity.public_key):
            raise JournalError("Scheduled financial work requires the enrolled home device")
        self.db = self.store.db
        self._fetch_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="journal-price-fetch")
        self._fetch_future: Future | None = None
        self._fetch_work = None
        self._fetch_now = None
        # The attached CashAdapter denies DDL as well as financial writes.
        # Temporarily lift it only around these fixed local journal tables, and
        # restore the exact adapter guard even if schema creation fails.
        self.db.conn.set_authorizer(None)
        try:
            with self.db.transaction():
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS journal_automation_jobs("
                    "job_key TEXT PRIMARY KEY, action TEXT NOT NULL, args_json TEXT NOT NULL, "
                    "proposal_id TEXT, state TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '')"
                )
                self.db.execute(
                    "CREATE TABLE IF NOT EXISTS journal_automation_results("
                    "job_key TEXT PRIMARY KEY, payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, "
                    "state TEXT NOT NULL)"
                )
        finally:
            self.db.conn.set_authorizer(self.store.adapter._authorize)

    def dispatch_once(self, job_id: str, action: str, **args) -> dict:
        """Issue one immutable home command per key; retries resume its receipt."""
        if (type(job_id) is not str or not 1 <= len(job_id) <= 160
                or any(ord(char) < 32 for char in job_id)):
            raise JournalError("Invalid automation job key")
        if action not in _ACTIONS:
            raise JournalError("This automated action is not enabled")
        args_json = canonical(args).decode("utf-8")
        record = str(uuid5(UUID(self.store.config["profile"]), "journal-automation:" + job_id))
        with self.db.transaction():
            row = self.db.one("SELECT * FROM journal_automation_jobs WHERE job_key=?", (job_id,))
            if row is not None:
                if row["action"] != action or row["args_json"] != args_json:
                    raise JournalError("Automation job key was reused with different work")
                proposal_id = row["proposal_id"]
                if proposal_id is None:
                    raise JournalError("Automation job is missing its durable proposal; preserve the profile for repair")
                state = self.device.home.status(proposal_id)
                if state is None or state["status"] not in {"accepted", "accepted-as-existing", "rejected"}:
                    wire = self.db.scalar("SELECT wire FROM journal_outbox WHERE proposal_id=?", (proposal_id,))
                    if wire is None:
                        raise JournalError("Automation proposal is missing; preserve the profile for repair")
                    self.device._offer(bytes(wire))
                    state = self.device.home.status(proposal_id)
                status = state["status"] if state else "pending"
                reason = state["reason"] if state else "queued"
                self.db.execute("UPDATE journal_automation_jobs SET state=?,reason=? WHERE job_key=?",
                                (status, reason, job_id))
                return dict(job_key=job_id, proposal_id=proposal_id, state=status, reason=reason)

            self.db.execute(
                "INSERT INTO journal_automation_jobs(job_key,action,args_json,state) VALUES(?,?,?,'pending')",
                (job_id, action, args_json),
            )
            wire = self.device.command(action, record=record, **args)
            proposal_id = origin_id(unpack(wire)["body"]["origin"])
            state = self.device.home.status(proposal_id)
            status = state["status"] if state else "pending"
            reason = state["reason"] if state else "queued"
            self.db.execute("UPDATE journal_automation_jobs SET proposal_id=?,state=?,reason=? WHERE job_key=?",
                            (proposal_id, status, reason, job_id))
            return dict(job_key=job_id, proposal_id=proposal_id, state=status, reason=reason)

    def tick(self, as_of: date | None = None) -> list[dict]:
        """Run one bounded daily pass: local market prices, revaluation, bill links.

        The market-file command is queued only when a newer file or month is due.
        Online fetch workers return data only. The owning loop stores their
        bounded result and asks the normal journal command path to apply it.
        """
        if (self.db.has_table("journal_local") and self.db.scalar(
                "SELECT 1 FROM journal_local WHERE name IN ('upgrade_barrier','cutover_normalization') LIMIT 1") is not None):
            return []
        if as_of is None:
            from lightning.core.dates import today
            as_of = today()
        if type(as_of) is not date:
            raise JournalError("Automation date must be a calendar date")
        results = []
        results.extend(self.resume_live_price_results())
        day = as_of.isoformat()
        from lightning.workflows.market_prices import FILLED_SETTING, current_set, followed_packs
        market = current_set(self.device.c.data_dir, followed_packs(self.device.c))
        filled = self.device.c.settings.get(FILLED_SETTING)
        did_fill = market is not None and filled != f"{market.created_at[:10]}|{day[:7]}"
        if did_fill:
            market_key = f"prices:{market.created_at[:10]}:{day[:7]}"
            results.append(self.dispatch_once(market_key, "automation.fill_prices", as_of=day))
        else:
            results.append(self.dispatch_once(f"revaluation:{day}", "automation.process_due"))
        results.append(self.dispatch_once(f"bill-match:{day}", "automation.match_bills", as_of=day))
        pending = self.poll_live_prices()
        if pending is not None:
            results.append(pending)
        if self._fetch_future is None:
            self.start_live_price_fetch(as_of)
        return results

    def start_live_price_fetch(self, as_of: date, now=None) -> bool:
        """Plan on the owner thread, then fetch using no database access in worker code."""
        from lightning.workflows import live_prices
        if (type(as_of) is not date or not live_prices.enabled()
                or self.device.c.settings.get(live_prices.TRIED_SETTING) == as_of.isoformat()):
            return False
        if self._fetch_future is not None:
            return False
        work = live_prices.plan(self.device.c, as_of, now)
        if not work.month_ends_missing():
            return False
        key = f"live-fetch-start:{as_of.isoformat()}"
        marked = self.dispatch_once(key, "automation.mark_live_fetch", as_of=as_of.isoformat())
        if marked["state"] != "accepted":
            return False
        self._fetch_work, self._fetch_now = work, now
        self._fetch_future = self._fetch_executor.submit(live_prices.gather, work, None, now, 30.0)
        return True

    def poll_live_prices(self) -> dict | None:
        """Accept a completed fetch on the owning thread; workers never save prices."""
        future = self._fetch_future
        if future is None or not future.done():
            return None
        self._fetch_future = None
        try:
            found, failed = future.result()
        except Exception:  # a source/parser failure stays a normal failed-source report
            found, failed = {}, ["the price sources"]
        work, self._fetch_work = self._fetch_work, None
        self._fetch_now = None
        return self.accept_prices((work, found, failed))

    def accept_prices(self, results) -> dict:
        """Durably stage worker output, then apply it through a signed home command."""
        if type(results) not in (tuple, list) or len(results) != 3:
            raise JournalError("Live-price result has an invalid shape")
        work, found, failed = results
        if work is None or type(found) is not dict or type(failed) is not list or len(failed) > 16:
            raise JournalError("Live-price result exceeds its limits")
        packed_found = {}
        if len(found) > 256:
            raise JournalError("Live-price result contains too many instruments")
        for identity, closes in found.items():
            key = str(identity)
            if type(closes) is not dict or len(closes) > 120:
                raise JournalError("Live-price result exceeds its limits")
            packed_found[key] = {}
            for day, raw in closes.items():
                try:
                    amount = Decimal(raw)
                    if not amount.is_finite() or type(day) is not str or len(day) != 10:
                        raise ValueError
                except (InvalidOperation, TypeError, ValueError) as error:
                    raise JournalError("Live-price result contains an invalid close") from error
                packed_found[key][day] = format(amount, "f")
        payload = dict(plan=_plan_record(work), found=packed_found,
                       failed=[str(item)[:120] for item in failed])
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        raw = encoded.encode("utf-8")
        if len(raw) > CHUNK_BYTES * MAX_CHUNKS:
            raise JournalError("Live-price result exceeds the journal staging limit")
        job_key = f"live-prices:{work.on}"
        fingerprint = hashlib.sha256(raw).hexdigest()
        with self.db.transaction():
            existing = self.db.one("SELECT payload_sha256 FROM journal_automation_results WHERE job_key=?", (job_key,))
            if existing and existing["payload_sha256"] != fingerprint:
                raise JournalError("Live-price job already has a different durable result")
            if not existing:
                self.db.execute(
                    "INSERT INTO journal_automation_results VALUES(?,?,?,'queued')",
                    (job_key, encoded, fingerprint),
                )
        result = self.dispatch_once(job_key, "automation.apply_live_prices", job_key=job_key)
        if result["state"] in {"accepted", "accepted-as-existing"}:
            with self.db.transaction():
                self.db.execute("UPDATE journal_automation_results SET state='applied' WHERE job_key=?", (job_key,))
        elif result["state"] == "rejected":
            with self.db.transaction():
                self.db.execute("UPDATE journal_automation_results SET state='rejected' WHERE job_key=?", (job_key,))
        return result

    def resume_live_price_results(self) -> list[dict]:
        """Retry persisted results after restart without making another source request."""
        results = []
        for row in self.db.all("SELECT job_key FROM journal_automation_results WHERE state IN ('queued','applying') ORDER BY job_key"):
            result = self.dispatch_once(row["job_key"], "automation.apply_live_prices", job_key=row["job_key"])
            if result["state"] in {"accepted", "accepted-as-existing"}:
                with self.db.transaction():
                    self.db.execute("UPDATE journal_automation_results SET state='applied' WHERE job_key=?", (row["job_key"],))
            elif result["state"] == "rejected":
                with self.db.transaction():
                    self.db.execute("UPDATE journal_automation_results SET state='rejected' WHERE job_key=?", (row["job_key"],))
            results.append(result)
        return results

    def close(self) -> None:
        """Stop worker resources on profile lock; the worker itself never owns the DB."""
        self._fetch_executor.shutdown(wait=False, cancel_futures=True)
