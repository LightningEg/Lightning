"""Which POST routes of the app work on a journal profile (J6f)?

Static inventory: for every POST route of `create_app`, the container calls its handler makes (following
helpers in the same routes module, another routes module, or a workflow in FOLLOWED), each classed as a write by its name's verb (else a read); a write is
covered when a registered journal command (`sync/journal/commands.py`) names that service method.
Prints Markdown to stdout. `--check` exits 1 if a route listed in `tools/journal_coverage_allow.txt` is no
longer covered. Heuristic: only calls on `c` / `container(request)` are seen, not on values derived from them.
"""
from __future__ import annotations

import argparse
import ast
import inspect
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ALLOW = Path(__file__).with_name("journal_coverage_allow.txt")
# A method is a write when its name is one of these verbs or starts with one plus "_" (`record_expense`); anything
# else (get, list, find, summar, preview, search, history, count, quote, usual, earliest, opening, display,
# pickable, tree, month_view, ...) is taken as a read. A registered command's method is always a write.
WRITE_VERBS = (
    "record", "create", "update", "set", "save", "add", "delete", "remove", "apply", "confirm", "discard", "void", "restore",
    "adjust", "close", "unlock", "assign", "dismiss", "stage", "merge", "replay", "undo", "buy", "sell", "dividend", "move",
    "link", "unlink", "mark", "skip", "reopen", "allocate", "complete", "open", "deactivate", "reactivate", "sync",
    "process", "take", "change", "rename", "purchase", "redeem", "reset", "start", "pay", "ensure", "clear", "enable",
    "forget", "execute", "insert", "bulk", "backup", "not", "from", "auto_link", "import",
)


# Calls the verbs mistake for writes. `auto_link_transaction` only reports ambiguous reserve suggestions and
# `from_transaction` only prefills a plan form; `forget` deletes shared-price files downloaded to this device.
NOT_WRITES = {"reserves.auto_link_transaction", "planning.from_transaction", "workflow.forget",
              "journal_workflows.budget_settings_fingerprint", "journal_workflows.bulk_budget_fingerprint"}


# Writes that run only for new free text: the route works without them, and with them the app's guard answers
# "not available yet". They are listed in the Notes column and do not change a route's state.
CONDITIONAL = {}

# These operations intentionally stay outside the replicated command log. Undo history is
# connection-local and contains arbitrary row snapshots; backup and fresh-profile operations
# manage the database file itself. Reporting them separately keeps them visible without
# implying that a replay on another device has equivalent data.
LOCAL_ONLY = {
    "undo.replay": "connection-local history cannot be replayed on another device",
    "backup_now": "local backup operation",
    "db.close": "local database lifecycle operation",
}

# Work that a screen deliberately dispatches through a runtime object rather than
# calling a service through the route's container. Keep these explicit so static
# inventory still checks the commands that own their financial effects.
ROUTE_COMMANDS = {
    ("investments", "/investments/prices/market/fill"): ("automation.fill_prices_now",),
    ("investments", "/investments/prices/market/update"): ("automation.fill_prices_now",),
    ("investments", "/investments/prices/markets"): ("automation.fill_prices_now",),
    ("investments", "/investments/prices/online"): ("automation.mark_live_fetch", "automation.apply_live_prices"),
}


# Workflow modules whose functions a route hands its form to, followed like route helpers. Following every
# workflow would also reclassify the price routes (live_prices, market_prices); that is for the journal's owner.
FOLLOWED = ("lightning.ui.routes", "lightning.workflows.investment_entry")


def covered_calls() -> set[str]:
    from lightning.sync.journal.commands import COMMANDS
    return ({entry.call for entry in COMMANDS.values() if type(entry.call) is str}
            | set(COMMANDS))


def is_write(call: str, covered=()) -> bool:
    name = call.split(".")[-1]
    return call in covered or (call not in NOT_WRITES and not name.endswith("_preview") and any(name == v or name.startswith(v + "_") for v in WRITE_VERBS))


class _Module:
    """One routes module: its functions by name, parsed once."""
    def __init__(self, module):
        self.functions = {}
        for node in ast.walk(ast.parse(inspect.getsource(module))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions.setdefault(node.name, []).append(node)

    def node_of(self, function):
        line = function.__code__.co_firstlineno
        for node in self.functions.get(function.__name__, []):
            if min([node.lineno] + [d.lineno for d in node.decorator_list]) == line:
                return node
        return None


def _chain(node):
    """`c.a.b(...)` as (root node, ["a", "b"])."""
    names = []
    while isinstance(node, ast.Attribute):
        names.append(node.attr)
        node = node.value
    return node, names[::-1]


def _is_container(node, aliases):
    return (isinstance(node, ast.Name) and node.id in aliases) or (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "container")


def _helper(func, owner):
    """The routes-module (or FOLLOWED workflow) function a call names (same module, or `module.name`), else None."""
    namespace = vars(sys.modules[owner.__module__])
    if isinstance(func, ast.Name):
        target = namespace.get(func.id)
    elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        target = getattr(namespace.get(func.value.id), func.attr, None)
    else:
        return None
    return target if inspect.isfunction(target) and target.__module__.startswith(FOLLOWED) else None


def calls_of(function, modules, seen=None):
    """The container calls (`service.method`) a handler makes, following helpers it calls."""
    seen = set() if seen is None else seen
    node = modules(function.__module__).node_of(function)
    if node is None or (function.__module__, node.lineno) in seen:
        return set()
    seen.add((function.__module__, node.lineno))
    aliases = {"c"}
    for item in ast.walk(node):
        if isinstance(item, ast.Assign) and isinstance(item.value, ast.Call) and _is_container(item.value, aliases):
            aliases |= {t.id for t in item.targets if isinstance(t, ast.Name)}
    services = {}  # `inv = c.investments` names a service
    for item in ast.walk(node):
        if isinstance(item, ast.Assign) and isinstance(item.value, ast.Attribute):
            root, names = _chain(item.value)
            if _is_container(root, aliases) and len(names) == 1:
                services |= {t.id: names[0] for t in item.targets if isinstance(t, ast.Name)}
    found = set()
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        root, names = _chain(item.func)
        if isinstance(root, ast.Name) and root.id in services and names:
            found.add(".".join([services[root.id], names[0]]))
            continue
        if _is_container(root, aliases) and names:
            found.add(".".join(names))
            continue
        target = _helper(item.func, function)
        if target is not None:
            found |= calls_of(target, modules, seen)
        elif any(_is_container(_chain(arg)[0], aliases) and _chain(arg)[1] for arg in item.args):
            found.add("workflow." + (item.func.attr if isinstance(item.func, ast.Attribute) else getattr(item.func, "id", "?")))
    return found


def _routes(routes):
    """Every route, looking inside the routers an app includes (FastAPI keeps them as one entry)."""
    for route in routes:
        router = getattr(route, "original_router", None)
        yield from _routes(router.routes) if router is not None else [route]


def inventory():
    from lightning.ui.web import create_app
    cache = {}

    def modules(name):
        if name not in cache:
            cache[name] = _Module(sys.modules[name])
        return cache[name]

    covered = covered_calls()
    rows = []
    for route in _routes(create_app(None).routes):
        if "POST" not in getattr(route, "methods", ()):
            continue
        calls = calls_of(route.endpoint, modules)
        calls.update(ROUTE_COMMANDS.get((route.endpoint.__module__.rsplit(".", 1)[-1], route.path), ()))
        every = sorted(call for call in calls if is_write(call, covered))
        writes = [call for call in every if call not in CONDITIONAL]
        done = [call for call in writes if call in covered]
        local = [call for call in writes if call in LOCAL_ONLY]
        state = ("read-only" if not every else "uncovered" if not writes else
                 "covered" if len(done) == len(writes) else
                 "local-only" if len(local) == len(writes) else
                 "partial" if done or local else "uncovered")
        rows.append(dict(module=route.endpoint.__module__.rsplit(".", 1)[-1], path=route.path, state=state, writes=writes,
                         missing=[call for call in writes if call not in covered],
                         notes=([CONDITIONAL[call] for call in every if call in CONDITIONAL] +
                                [LOCAL_ONLY[call] for call in writes if call in LOCAL_ONLY])))
    return sorted(rows, key=lambda row: (row["module"], row["path"]))


def report(rows) -> str:
    out = ["# Journal coverage of POST routes", ""]
    by_module = defaultdict(list)
    for row in rows:
        by_module[row["module"]].append(row)
    for module, items in by_module.items():
        out += [f"## {module}", "", "| Route | State | Writes not covered | Notes |", "|---|---|---|---|"]
        out += [f"| `POST {row['path']}` | {row['state']} | {', '.join(row['missing'])} | "
                f"{'not for ' + ', '.join(row['notes']) if row['notes'] else ''} |" for row in items]
        out.append("")
    count = Counter(row["state"] for row in rows)
    out.append("Summary: " + ", ".join(f"{count[state]} {state}" for state in ("covered", "partial", "uncovered", "local-only", "read-only"))
               + f" ({len(rows)} POST routes)")
    top = Counter(call for row in rows for call in row["missing"] if call not in LOCAL_ONLY).most_common(10)
    out += ["", "Most used uncovered writes: " + ", ".join(f"{call} ({n})" for call, n in top)]
    return "\n".join(out)


def regressions(rows, allow=ALLOW) -> list[str]:
    state = {f"POST {row['path']}": row["state"] for row in rows}
    wanted = [line.strip() for line in allow.read_text().splitlines() if line.strip() and not line.startswith("#")]
    return [f"{line}: {state.get(line, 'missing')}" for line in wanted if state.get(line) != "covered"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if a route in the allowlist is no longer covered")
    args = parser.parse_args(argv)
    rows = inventory()
    print(report(rows))
    bad = regressions(rows) if args.check else []
    for line in bad:
        print("REGRESSION", line, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
