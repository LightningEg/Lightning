"""The docs stay cheap to read: the rules in AGENTS.md section 2, checked so they cannot drift."""

import importlib.util
import re
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
GUIDELINE = ROOT / "guideline"
DOCUMENTS = {"A": "app.html", "B": "website.html", "C": "phone.html", "D": "coders.html"}


def _guideline_tool():
    spec = importlib.util.spec_from_file_location("guideline", ROOT / "tools" / "guideline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_hand_off_is_short_and_has_its_parts():
    text = (ROOT / "NOW.md").read_text(encoding="utf-8")
    assert len(text.encode("utf-8")) < 4500, "NOW.md must stay under 4,500 bytes: done work is in the changelog, owner questions in GitHub issues"
    for heading in ("## Claimed", "## Messages", "## Next"):
        assert re.search(rf"^{re.escape(heading)}", text, re.M), f"NOW.md lost its {heading!r} part"
    assert "| Who | Work | Files | Since |" in text, "NOW.md's claims are one table: Who, Work, Files, Since"
    old_parts = re.findall(r"^## (?:Claude|Codex|For the owner)\b.*$", text, re.M)
    assert not old_parts, f"NOW.md has no lanes: claims go in Claimed (AGENTS.md section 3): {old_parts}"
    overview = (DOCS / "PROJECT_OVERVIEW.md").read_text(encoding="utf-8")
    assert "## Now and next" not in overview, "the hand-off lives in NOW.md only"


def test_no_message_to_all_is_older_than_seven_days():
    text = (ROOT / "NOW.md").read_text(encoding="utf-8")
    old = []
    for who, day in re.findall(r"^- \*\*To all, from ([^,]+?),? (\d{4}-\d{2}-\d{2}):\*\*", text, re.M):
        if (date.today() - date.fromisoformat(day)).days > 7:
            old.append(f"{who} {day}")
    assert not old, f"a message to all stays seven days (AGENTS.md section 3); its author removes it: {old}"


def test_every_next_step_says_what_to_read():
    text = (ROOT / "NOW.md").read_text(encoding="utf-8")
    steps = re.split(r"(?m)^(?=\d+\. )", text.split("\n## Next", 1)[1].split("\n## ", 1)[0])[1:]
    assert steps, "NOW.md's Next part lists its steps as 1. 2. 3."
    missing = [step.split("\n", 1)[0][:70] for step in steps if "Read:" not in step]
    assert not missing, f"each Next step has a Read: line naming what it needs (AGENTS.md section 3): {missing}"


def test_docs_holds_only_the_carrying_files():
    allowed = {"PROJECT_OVERVIEW.md", "ARCHITECTURE.md", "GLOSSARY.md", "COMPETITION.md"}
    extra = {path.name for path in DOCS.iterdir()} - allowed
    assert not extra, f"new files under docs/ (AGENTS.md section 1; designs go in issues/): {sorted(extra)}"


def test_every_long_doc_lists_all_its_sections():
    for name in ("PROJECT_OVERVIEW.md", "ARCHITECTURE.md", "GLOSSARY.md"):
        text = (DOCS / name).read_text(encoding="utf-8")
        contents = text.split("## Contents", 1)[1].split("\n## ", 1)[0]
        listed = set(re.findall(r"^\| ([^|]+?) \|", contents, re.M)) - {"Section"}
        headings = set(re.findall(r"^## (.+)$", text, re.M)) - {"Contents"}
        assert headings == listed, f"{name}: Contents and headings differ: {sorted(headings ^ listed)}"


def test_unreleased_comes_first_newest_first():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.findall(r"^## (.+)$", text, re.M)[0] == "[Unreleased]"
    unreleased = text.split("\n## [Unreleased]\n", 1)[1].split("\n## ", 1)[0]
    dates = re.findall(r"^- (\d{4}-\d{2}-\d{2}) ·", unreleased, re.M)
    assert dates == sorted(dates, reverse=True), "add new changelog entries at the top of Unreleased"


def test_agents_md_carries_the_guidelines_a16_checklist():
    tool = _guideline_tool()
    section = next(block for number, _, block in tool.all_sections(GUIDELINE) if number == "A16")
    items = re.findall(r"<div><b>([^<]+)</b>([^<]+)</div>", section)
    assert len(items) >= 10, "could not read A16's items; update this test with the guideline's markup"
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    checklist = agents.split("**Before it ships (guideline A16).**", 1)[1].split("\n", 1)[0]
    missing = [f"{name}: {rule}" for name, rule in items if f"{name}: {rule}" not in checklist]
    assert not missing, f"AGENTS.md's A16 list is missing: {missing}"


def test_the_guideline_tool_prints_one_section_as_text():
    tool = _guideline_tool()
    found = tool.all_sections(GUIDELINE)
    assert [n for n, _, _ in found if n.startswith("A")][-1] == "A16"
    assert [n for n, _, _ in found if n.startswith("B")][-1] == "B12" and [n for n, _, _ in found if n.startswith("C")][-1] == "C12"
    assert [n for n, _, _ in found if n.startswith("D")][-1] == "D12"
    a16 = tool.as_text(next(block for number, _, block in found if number == "A16"))
    assert "Before it ships" in a16 and "<" not in a16 and len(a16) < 2000


def _title(path: Path) -> str:
    return re.search(r"<title>([^<]*)</title>", path.read_text(encoding="utf-8")).group(1)


def test_each_guideline_document_holds_only_its_part_and_names_the_others():
    for letter, name in DOCUMENTS.items():
        html = (GUIDELINE / name).read_text(encoding="utf-8")
        numbers = [n for n, _, _ in _guideline_tool().sections(html)]
        assert numbers and all(n.startswith(letter) for n in numbers), f"{name} holds sections of another part: {numbers}"
        assert "AI AGENTS: this is ONE of FOUR guideline documents" in html, f"{name} lost its hint to the other documents"
        for other in set(DOCUMENTS.values()) - {name}:
            assert f'href="{other}"' in html, f"{name} does not link to {other}"
    versions = {_title(GUIDELINE / name).split(" · ")[0] for name in DOCUMENTS.values()}
    assert len(versions) == 1, f"the four documents carry different versions: {versions}"


def test_the_app_and_website_guidelines_are_the_same_four_files():
    """AGENTS.md section 1: change both copies together. Checked when the website repo sits beside this one."""
    beside = [ROOT.parent / name / "guideline" for name in ("Lightning_website", "lightning_website")]
    website = next((path for path in beside if path.is_dir()), None)
    if website is None:
        pytest.skip("the website repository is not checked out next to this one")
    for name in DOCUMENTS.values():
        same = (GUIDELINE / name).read_bytes().replace(b"\r\n", b"\n") == (website / name).read_bytes().replace(b"\r\n", b"\n")
        assert same, (f"guideline/{name} ({_title(GUIDELINE / name)}) differs from the website's copy "
                      f"({_title(website / name)}): pull both repos, copy the newer over the older, and push both")
