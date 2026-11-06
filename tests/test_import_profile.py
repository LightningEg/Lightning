"""IT-7AA1: a file's date order is decided once for the whole file."""
import pytest

from lightning.core.errors import ValidationError
from lightning.import_profile import profile_dates, read_date


def test_month_first_file_is_read_month_first():
    cells = ["10/02/2026", "10/13/2026", "11/03/2026"]
    profile = profile_dates(cells)
    assert (profile.order, profile.ambiguous) == ("mdy", False)
    assert [read_date(c, profile).isoformat() for c in cells] == ["2026-10-02", "2026-10-13", "2026-11-03"]


def test_day_first_file_and_ambiguous_default():
    profile = profile_dates(["13/10/2026", "10/02/2026"])
    assert profile.order == "dmy" and not profile.ambiguous
    assert read_date("10/02/2026", profile).isoformat() == "2026-02-10"
    assert profile_dates(["10/02/2026", "03/04/2026"]).ambiguous


def test_times_month_names_and_iso():
    assert read_date("2026-10-02 14:05:33").isoformat() == "2026-10-02"
    assert read_date("2026-10-02T14:05:33Z").isoformat() == "2026-10-02"
    assert read_date("02/10/2026 2:05 PM").isoformat() == "2026-10-02"
    assert read_date("01-Oct-2026").isoformat() == "2026-10-01"
    assert read_date("2 Oct 26").isoformat() == "2026-10-02"
    assert read_date("Oct 2, 2026").isoformat() == "2026-10-02"
    assert read_date("٠٢/١٠/٢٠٢٦").isoformat() == "2026-10-02"
    assert profile_dates(["2026-10-02", "2026-11-03"]).order == "ymd"


def test_bad_date_errors():
    with pytest.raises(ValidationError):
        read_date("31/02/2026")


def test_direction_column_sets_the_sign():
    import pytest as _p
    from lightning.bank_import_parsing import normalize_rows
    from lightning.bank_import_rows import direction_sign
    mapping = {"Date": "D", "Amount": "A", "Direction": "T"}
    raw = [{"D": "01/10/2026", "A": "250.50", "T": "DR", "__line__": "2"},
           {"D": "02/10/2026", "A": "15,000", "T": "Credit", "__line__": "3"},
           {"D": "03/10/2026", "A": "-80", "T": "Expense", "__line__": "4"},
           {"D": "04/10/2026", "A": "5", "T": "Card", "__line__": "5"}]
    rows = [parsed for _raw, parsed in normalize_rows(raw, mapping, "SINGLE", False)]
    assert [r["Amount"] for r in rows[:3]] == ["-250.50", "15000", "-80"]
    assert rows[3]["_errors"]
    assert direction_sign("Income") == 1


def test_type_column_is_no_longer_a_category(c, setup):
    headers = ["Date", "Amount", "Type", "Direction"]
    mapping = c.bank_imports.suggested_mapping(setup[0]["cib"].id, headers)
    assert mapping.get("Direction") == "Direction" and "Category" not in mapping


def test_bare_type_column_is_a_direction_only_when_its_values_are(c, setup):
    acc = setup[0]["cib"].id
    drcr = [{"Date": "2026-10-01", "Amount": "5", "Type": "DR"}, {"Date": "2026-10-02", "Amount": "6", "Type": "CR"}]
    assert c.bank_imports.suggested_mapping(acc, ["Date", "Amount", "Type"], drcr).get("Direction") == "Type"
    kinds = [{"Date": "2026-10-01", "Amount": "5", "Type": "Card"}]
    assert "Direction" not in c.bank_imports.suggested_mapping(acc, ["Date", "Amount", "Type"], kinds)
