"""Every POST declares who completes it; a database write never spans a request await."""
import ast
from pathlib import Path

ROUTES = Path(__file__).parents[1] / "lightning/ui/routes"
# These handlers have a different completion boundary, or perform no financial write.
OTHER_BOUNDARIES = {
    "history": {"replay"},  # History restores both rows and links in its own replay transaction.
    "exports": {"transactions", "categories", "reevaluations", "preview_workbook_import"},
    "transactions": {"all_accounts_entry", "all_accounts_update"},  # register.create/update own the save.
    "accounts": {"investment_entry", "register_entry", "register_update"},
    "investments": {"market_fill", "market_update", "test_price_sources"},  # _fill_from owns the save after fetch.
    "sms": {"allow", "read_one_message"},  # OS permission and read-only parsing.
    "planning": {"not_recurring"},  # Suggestion visibility, a single settings write.
    "dashboard": {"add_demo_household", "add_sample_2026", "add_sample_story", "needs_you_state"},
    "settings": {"ask_ai", "prepare_ai_analysis", "backup_now", "start_fresh", "save_privacy"},  # Exports, dedicated file workflows, and the display preference (no undo group, no settlement).
    "weekly": {"complete", "dismiss"},  # Review preferences never settle a financial issue.
}


def _settled(scope):
    return isinstance(scope, ast.With) and any(isinstance(i.context_expr, ast.Call)
        and ast.unparse(i.context_expr.func) == "settled_save" for i in scope.items)


def test_write_handlers_declare_their_completion_boundary_and_never_await_inside_it():
    found = set()
    for path in ROUTES.glob("*.py"):
        tree = ast.parse(path.read_text())
        for fn in tree.body:
            if not isinstance(fn, ast.AsyncFunctionDef):
                continue
            for scope in (n for n in ast.walk(fn) if _settled(n)):
                assert not any(isinstance(n, ast.Await) for n in ast.walk(scope)), (path.name, fn.name)
            if not any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                       and d.func.attr == "post" for d in fn.decorator_list):
                continue
            if fn.name in OTHER_BOUNDARIES.get(path.stem, set()):
                found.add((path.stem, fn.name))
            else:
                assert any(_settled(n) for n in ast.walk(fn)), (path.name, fn.name)
    assert found == {(module, name) for module, names in OTHER_BOUNDARIES.items() for name in names}
