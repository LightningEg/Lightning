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
