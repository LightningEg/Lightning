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
