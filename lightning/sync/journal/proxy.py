"""The services the app's screens use on a journal profile (J6f).

Reads go straight to the confirmed copy. A covered write becomes a command
proposal: on the home it is confirmed at once and returns what the service
returned (or raises its refusal); on any other device it is saved and raises
`PendingOnHome`, which the screen shows as saved-and-waiting. Writes that are
not covered still reach the connection guard and are refused.
"""
from __future__ import annotations

import inspect
from contextlib import contextmanager
from datetime import date
from enum import Enum

from lightning.core.errors import ValidationError
from lightning.core.money import to_decimal

from .codec import origin_id, unpack
from .commands import COMMANDS


class PendingOnHome(Exception):
    """Saved on this device; it takes effect when the home confirms it. Not a
    LightningError, so screens that show refusals inline let it reach the app."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class JournalServices:
    is_journal = True

    @property
    def history_is_home(self):
        """Whether home-local history may be replayed in this session."""
        return self._device.store.config.get("role") == "home"

    def __init__(self, device, *, backup=None):
        self._device = device
        self._backup = backup
        # Module-level workflow commands (a function `call`) are reached by their own screens, not through here.
        self._calls = {entry.call: name for name, entry in COMMANDS.items() if type(entry.call) is str}

    def __getattr__(self, name):
        if name == "backup_now" and self._backup is not None:
            return self._backup
        service = getattr(self._device.c, name)
        if service is None:
            return None
        if name in self._calls:  # A container-level action, e.g. set_profile_currency.
            return lambda *args, **kwargs: self._run(name, service, args, kwargs)
        if name == "db":
            return _Database(service)
        if any(call.split(".")[0] == name for call in self._calls):
            return _Service(self, name, service)
        return service

    def _run(self, call, method, args, kwargs):
        action = self._calls[call]
        entry = COMMANDS[action]
        signature = inspect.signature(method)
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        arguments = {}
        for name, value in bound.arguments.items():  # A **values parameter (a trade edit) carries its own names.
            if signature.parameters[name].kind is inspect.Parameter.VAR_KEYWORD:
                arguments.update(value)
            else:
                arguments[name] = value
        if call in {"budgets.save_month", "budgets.apply_fill"} and "amounts" in arguments:
            # The app's budget workflow takes id-keyed dictionaries; the portable
            # command carries category UUIDs in explicit rows.
            amounts = arguments.pop("amounts") or {}
            averages = arguments.pop("average_months", None) or {}
            arguments["lines"] = [dict(category=category_id, amount=amount,
                                        average_months=averages.get(category_id))
                                  for category_id, amount in amounts.items()]
        if call == "budgets.set_carryover" and "settings" in arguments:
            arguments["lines"] = [dict(category=category_id, enabled=enabled)
                                  for category_id, enabled in arguments.pop("settings").items()]
        if call in {"account_flows.open_account", "account_flows.update_account"}:
            arguments["opening_balance"] = self._device.c.account_flows.parse_opening(arguments["opening_balance"])
        for name, value in arguments.items():
            parameter = signature.parameters.get(name)
            if name not in entry.args and (parameter is None or value is not parameter.default):
                raise ValidationError("This option is not available on a synchronized profile yet.")
        adapter = self._device.adapter
        values = {name: _wire(adapter, spec, arguments.get(name)) for name, spec in entry.args.items()}
        if entry.encode is not None:
            values = entry.encode(adapter, values)
        if self._device.home is None:
            rehearsed = self._rehearse(method, args, kwargs)
            if isinstance(rehearsed, dict) and rehearsed.get("errors"):
                return rehearsed  # Row-level refusals (an import): shown at once, nothing is saved.
        wire = self._device.command(action, **values)
        identifier = origin_id(unpack(wire)["body"]["origin"])
        home = self._device.home
        state = home.status(identifier) if home else None
        if state is None or state["status"] in ("staged", "review"):
            raise PendingOnHome("Saved on this device. It takes effect when the home confirms it.")
        if state["status"] == "rejected":
            raise ValidationError(adapter.errors.pop(identifier, "The home could not apply this action."))
        return adapter.results.pop(identifier, None)


    def _rehearse(self, method, args, kwargs):
        """Run the action against this device's confirmed copy and roll it back, so
        a refusal the service would give shows at once, in its own words."""
        try:
            with self._device.store.db.transaction():
                with self._device.adapter.writing():
                    result = method(*args, **kwargs)
                raise _Rehearsed(result)
        except _Rehearsed as rehearsed:
            return rehearsed.args[0]
        finally:
            # A rehearsed profile-currency change rolls its SQL back, but it also
            # refreshes the live service graph. Restore those caches from settings.
            from .areas.settings import refresh
            refresh(self._device.c)


class _Rehearsed(Exception):
    pass


class _Database:
    """The database as a screen sees it. A screen wraps its save in a transaction; a command saved on this device
    must survive the PendingOnHome that leaves that block, so the block commits and then re-raises it."""

    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    @contextmanager
    def transaction(self, *args, **kwargs):
        waiting = None
        with self._db.transaction(*args, **kwargs) as conn:
            try:
                yield conn
            except PendingOnHome as error:
                waiting = error
        if waiting is not None:
            raise waiting


class _Service:
    def __init__(self, outer, name, service):
        self._outer, self._name, self._service = outer, name, service

    def __getattr__(self, method):
        target = getattr(self._service, method)
        call = f"{self._name}.{method}"
        if call not in self._outer._calls:
            if any(name.startswith(call + ".") for name in self._outer._calls):
                return _Service(self._outer, call, target)
            return target
        def journaled(*args, **kwargs):
            return self._outer._run(call, target, args, kwargs)
        return journaled


def _wire(adapter, spec, value):
    """A service argument as the command carries it (UUIDs, exact text)."""
    if type(spec) is tuple and spec[0] == "list":
        return [_wire(adapter, spec[1], item) for item in value or []]
    if type(spec) is tuple and spec[0] == "map":
        out = {}
        for key, item in dict(value or {}).items():
            inner = spec[1].get(key)
            if inner is None:
                if spec[2] and item not in (None, ""):  # A strict record refuses what it cannot carry.
                    raise ValidationError("This option is not available on a synchronized profile yet.")
                continue
            if item is None or (item == "" and inner.lstrip("?") not in ("text", "long")):
                continue  # Left blank: not given.
            out[key] = _wire(adapter, inner, item)
        return out
    if type(spec) is tuple:  # Records may arrive as tuples in the field order; a mapping as its (key, value) pairs.
        value = list(value.items()) if isinstance(value, dict) else value
        return [{name: _wire(adapter, inner, item[name] if isinstance(item, dict) else item[index])
                 for index, (name, inner) in enumerate(spec[1].items())} for item in value or []]
    bare = spec.lstrip("?")
    if value is None:
        return None
    if spec.startswith("?") and value == "" and bare not in ("text", "long"):
        return None
    if isinstance(value, Enum):
        value = value.value
    if bare.startswith("ref:"):
        return adapter.uid(bare[len("ref:"):], int(getattr(value, "id", value)))
    if bare == "bytes":
        import base64
        return base64.b64encode(value).decode("ascii")
    if bare == "json":
        return value
    if bare in ("amount", "rate"):
        if spec.startswith("?") and not str(value).strip():
            return None  # An optional amount left blank (a fee) is not given.
        return format(to_decimal(value), "f")
    if bare == "date" and type(value) is str:
        from lightning.core.dates import parse_date
        value = parse_date(value)  # The screens accept short dates (1/7); the command carries ISO.
    if bare in ("date", "month") and isinstance(value, date):
        return value.isoformat()[:7 if bare == "month" else 10]
    if bare == "int":
        return int(value)
    if bare == "flag":
        return bool(value)
    return value if type(value) is str else str(value)
