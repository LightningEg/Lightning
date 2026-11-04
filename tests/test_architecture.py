"""Architecture rules from pyproject.toml, enforced as a test."""

import ast
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("lint-imports") is None, reason="import-linter not installed")
def test_import_contracts():
    result = subprocess.run(["lint-imports"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_top_level_module_has_a_layer():
    """9K: a module left out of the layer contract can import upward unseen (18 were, before Audit 3)."""
    import tomllib
    contract = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["importlinter"]
    layers = next(c["layers"] for c in contract["contracts"] if c["type"] == "layers")
    placed = {name.strip() for layer in layers for name in layer.split("|")}
    package = ROOT / "lightning"
    modules = {f"lightning.{p.stem}" for p in package.glob("*.py") if p.stem not in ("__init__", "__main__")}
    modules |= {f"lightning.{p.name}" for p in package.iterdir() if (p / "__init__.py").exists()}
    assert sorted(modules - placed) == []


def test_no_float_money_in_financial_code():
    """Financial modules must never construct floats."""
    for folder in ("core", "accounts", "transactions", "reporting", "workflows"):
        for path in (ROOT / "lightning" / folder).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "float(" not in text, f"{path} uses float()"


def test_ui_contains_no_sql():
    for path in (ROOT / "lightning" / "ui").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            text = node.value.lstrip()
            if re.match(r"(?is)^(SELECT\b.*\bFROM\b|INSERT\s+INTO\b|UPDATE\s+\w+\s+SET\b|DELETE\s+FROM\b)", text):
                raise AssertionError(f"SQL literal in UI route: {path}:{node.lineno}")


def test_one_row_id_parser_keeps_each_callers_rules():
    from lightning.core.errors import ValidationError
    from lightning.core.refs import MAX_ROW_ID, parse_row_id
    assert parse_row_id(" 42 ", "id") == 42 and parse_row_id(7, "id") == 7
    assert parse_row_id("", "id", blank=True) is None and parse_row_id(None, "id", blank=True) is None
    for bad in (True, 0, -1, MAX_ROW_ID + 1, "4.0", "٤٢", "", None, 4.0):
        with pytest.raises(ValidationError):
            parse_row_id(bad, "id")
    with pytest.raises(ValidationError, match="activity"):
        parse_row_id("42", "transaction_id", "Choose a valid activity or review option.", digits=False)


def test_budgeting_gets_the_schedule_passed_in_and_never_imports_planning():
    """IT-9K: Budget reads loans, bills, income and reserve needs from a ScheduleView its caller passes (``schedule=``);
    no callback is wired from the composition root, and no budgeting module imports planning."""
    import inspect
    from lightning.budgeting.service import BudgetService
    for path in (ROOT / "lightning" / "budgeting").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
            names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            assert not any(name == "lightning.planning" or name.startswith("lightning.planning.") for name in names), path
    assert not any(hasattr(BudgetService, name) for name in
                   ("scheduled_loans", "scheduled_bills", "scheduled_income", "reserve_goal_needs"))
    for name in ("month_view", "income_average", "amounts_for", "has_plan", "save_month", "set_budget", "plan_summary"):
        parameter = inspect.signature(getattr(BudgetService, name)).parameters["schedule"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY and parameter.default is parameter.empty


def test_bootstrap_wires_no_callback_into_a_service():
    """IT-9K: services get what they need through their constructors or call arguments, not by assigned lambdas."""
    tree = ast.parse((ROOT / "lightning" / "bootstrap.py").read_text(encoding="utf-8"))
    assigned = [ast.unparse(node.targets[0]) for node in ast.walk(tree) if isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Attribute) and isinstance(node.value, (ast.Lambda, ast.Attribute))
                and isinstance(node.targets[0].value, ast.Name) and node.targets[0].value.id in
                {"budgets", "forecaster", "health", "planning", "reporting"}]
    assert assigned == []


def test_other_asset_value_is_saved_through_the_account_service(c):
    """9J: the route saves an Other asset value through AccountService, never the reporting repository; the journal
    command keeps its key but calls the service method."""
    route = (ROOT / "lightning" / "ui" / "routes" / "accounts.py").read_text(encoding="utf-8")
    assert "other_asset_values" not in route
    assert "accounts.save_other_asset_value" in route
    from lightning.sync.journal.areas.master import COMMANDS
    assert COMMANDS["reporting.other_asset_values.save"].call == "accounts.save_other_asset_value"
    flat = c.account_flows.open_account("Flat", "OTHER_ASSET", "2026-01-01", "1000000")
    saved = c.accounts.save_other_asset_value(c.accounts.get(flat.id), "2026-02-01", "1200000", " note ")
    assert saved["value_e6"] == 1_200_000_000_000 and saved["notes"] == "note"
    with pytest.raises(Exception, match="Choose an Other asset account"):
        c.accounts.save_other_asset_value(c.accounts.get(c.account_flows.open_account("B", "BANK", "2026-01-01", "1").id),
                                          "2026-02-01", "5")
def test_sync_module_policies_and_boundaries():
    from tools.backend_policy import check
    assert check() == []


def test_sync_policy_detects_unassigned_modules_and_forbidden_protocol_imports(tmp_path):
    from tools.backend_policy import policy_problems
    package = tmp_path / 'lightning' / 'sync'
    package.mkdir(parents=True)
    (package / 'domain.py').write_text('from lightning.runtime import app\n')
    (package / 'new.py').write_text('')
    policies = {'protocol': ['lightning.sync.domain'], 'financial_adapters': [], 'runtime_boundary': []}
    problems = policy_problems(package, policies)
    assert 'unassigned: lightning.sync.new' in problems
    assert any('imports upper layer lightning.runtime' in item for item in problems)
    (package / 'domain.py').write_text('from lightning import runtime\n')
    assert any('imports upper layer lightning.runtime' in item for item in policy_problems(package, policies))
    (package / 'domain.py').write_text('from lightning.sync import new\n')
    problems = policy_problems(package, policies)
    assert any('imports outside protocol lightning.sync.new' in item for item in problems)
    policies['financial_adapters'].append('lightning.sync.new')
    (package / 'domain.py').write_text('')
    (package / 'new.py').write_text('from lightning.ui import routes\n')
    assert any('imports upper layer lightning.ui' in item for item in policy_problems(package, policies))
    (package / 'new.py').write_text('')
    assert policy_problems(package, policies) == []
    policies['runtime_boundary'].append('lightning.sync.new')
    assert 'multiple policies: lightning.sync.new' in policy_problems(package, policies)


def test_sync_package_initializers_are_assigned_and_checked(tmp_path):
    from tools.backend_policy import policy_problems
    package = tmp_path / 'lightning' / 'sync'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('from lightning import runtime, harmless\n')
    policies = {'protocol': [], 'financial_adapters': [], 'runtime_boundary': []}
    problems = policy_problems(package, policies)
    assert 'unassigned: lightning.sync' in problems
    assert any('imports upper layer lightning.runtime' in item for item in problems)
    policies['runtime_boundary'].append('lightning.sync')
    (package / '__init__.py').write_text('')
    assert policy_problems(package, policies) == []


def test_financial_adapter_cannot_import_runtime_module(tmp_path):
    from tools.backend_policy import policy_problems
    package = tmp_path / 'lightning' / 'sync'
    package.mkdir(parents=True)
    (package / 'adapter.py').write_text('from . import runtime\n')
    (package / 'runtime.py').write_text('')
    policies = {'protocol': [], 'financial_adapters': ['lightning.sync.adapter'],
                'runtime_boundary': ['lightning.sync.runtime']}
    assert any('imports runtime module lightning.sync.runtime' in problem
               for problem in policy_problems(package, policies))


def test_required_financial_collaborators_are_wired_and_validated(c):
    from lightning.investments.service import InvestmentService
    from lightning.planning.forecast import CashForecaster

    assert c.investments.reevaluations is c.reevaluations
    assert c.forecaster.deposits is c.deposits
    assert c.forecaster.deposit_receipts is c.deposit_receipts
    investment_args = (c.db, c.accounts, c.assets, c.categories, c.transactions, c.reporting)
    with pytest.raises(TypeError):
        InvestmentService(*investment_args)
    with pytest.raises(TypeError, match='reevaluations'):
        InvestmentService(*investment_args, None)
    forecast_args = (c.planning, c.reporting, c.reserves, c.budgets, c.categories,
                     c.position, c.schedules, c.health)
    with pytest.raises(TypeError):
        CashForecaster(*forecast_args, c.deposits)
    with pytest.raises(TypeError, match='deposit_receipts'):
        CashForecaster(*forecast_args, c.deposits, object())
    with pytest.raises(TypeError, match='deposits'):
        CashForecaster(*forecast_args, None, c.deposit_receipts)
