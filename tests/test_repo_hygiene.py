"""Keep stray binaries out of Git: wheels only in packaging/third-party/, no tracked file over 5 MB."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 5 * 1024 * 1024
# Path -> reason. Empty: nothing tracked is over the limit today.
LARGE_ALLOWED: dict[str, str] = {}


def _tracked() -> list[str]:
    if not shutil.which("git"):
        pytest.skip("git is not available")
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [p for p in out.decode().split("\0") if p]


def test_wheels_only_in_third_party():
    stray = [p for p in _tracked() if p.endswith(".whl") and not p.startswith("packaging/third-party/")]
    assert not stray


def test_no_large_tracked_files():
    big = [p for p in _tracked() if (ROOT / p).is_file() and (ROOT / p).stat().st_size > LIMIT and p not in LARGE_ALLOWED]
    assert not big
