"""The source install reads requirements.txt: it must name every runtime dependency."""
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def _name(spec: str) -> str:
    return re.split(r"[<>=~!;\[ ]", spec.strip(), maxsplit=1)[0].lower()


def _lines(path: str) -> list[str]:
    text = (ROOT / path).read_text(encoding="utf-8")
    return [x.strip() for x in text.splitlines() if x.strip() and not x.strip().startswith("#")]


def test_requirements_txt_equals_project_dependencies():
    assert set(_lines("requirements.txt")) == set(PROJECT["dependencies"])


def test_requirements_dev_names_every_dev_dependency():
    named = {_name(x) for x in _lines("requirements-dev.txt") if not x.startswith("-r")}
    missing = {_name(x) for x in PROJECT["optional-dependencies"]["dev"]} - named
    assert not missing
