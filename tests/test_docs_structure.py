"""The docs stay cheap to read: the rules in AGENTS.md section 2, checked so they cannot drift."""

import importlib.util
import re
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"  # for people: short pages, the big picture
AI = ROOT / "ai"      # for AI sessions: depth and detail
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
    overview = (AI / "PROJECT_OVERVIEW.md").read_text(encoding="utf-8")
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


def test_docs_and_ai_hold_only_the_carrying_files():
    allowed = {"README.md", "STATUS.md", "product.md", "how-it-is-built.md", "journeys.md", "themes.md", "google-play.md",
               "pillars"}  # google-play.md: the owner's Console answers (NF-11B2, 11B5)
    extra = {path.name for path in DOCS.iterdir()} - allowed
    assert not extra, f"new files under docs/ (people read these; AGENTS.md section 1; designs go in issues/): {sorted(extra)}"
    allowed = {"INDEX.md", "PROJECT_OVERVIEW.md", "ARCHITECTURE.md", "GLOSSARY.md", "COMPETITION.md", "handbook",
               "changelog", "archive"}
    extra = {path.name for path in AI.iterdir()} - allowed
    assert not extra, f"new files under ai/ (AGENTS.md section 1; designs go in issues/): {sorted(extra)}"


def test_every_long_doc_lists_all_its_sections():
    for name in ("PROJECT_OVERVIEW.md", "ARCHITECTURE.md", "GLOSSARY.md"):
        text = (AI / name).read_text(encoding="utf-8")
        contents = text.split("## Contents", 1)[1].split("\n## ", 1)[0]
        listed = set(re.findall(r"^\| ([^|]+?) \|", contents, re.M)) - {"Section"}
        headings = set(re.findall(r"^## (.+)$", text, re.M)) - {"Contents"}
        assert headings == listed, f"{name}: Contents and headings differ: {sorted(headings ^ listed)}"


def test_generated_pages_are_up_to_date():
    """STATUS, the pillar pages' work blocks and the AI map are built from the plan: python tools/status.py."""
    from tools import status
    stale = [path.relative_to(ROOT).as_posix() for path, text in status.expected().items()
             if not path.exists() or path.read_text(encoding="utf-8") != text]
    assert not stale, f"out of date, run python tools/status.py: {stale}"


def test_the_pillars_are_one_list_everywhere():
    from tools import issues, status
    assert list(issues.PILLARS) == list(status.PILLARS) == list(status.PROSE)
    readme = (DOCS / "README.md").read_text(encoding="utf-8")
    for key in issues.PILLARS:
        assert f"(pillars/{key}.md)" in readme, f"docs/README.md does not link the {key} pillar"


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
    assert [n for n, _, _ in found if n.startswith("B")][-1] == "B12" and [n for n, _, _ in found if n.startswith("C")][-1] == "C13"
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


def test_the_app_and_website_guidelines_are_all_mirrored():
    """AGENTS.md section 1: change both copies together. Checked when the website repo sits beside this one."""
    beside = [ROOT.parent / name / "guideline" for name in ("Lightning_website", "lightning_website")]
    website = next((path for path in beside if path.is_dir()), None)
    if website is None:
        pytest.skip("the website repository is not checked out next to this one")
    tool = _docs_check_tool()
    assert not tool.mirrors(ROOT, website.parent)


def _docs_check_tool():
    spec = importlib.util.spec_from_file_location("docs_check", ROOT / "tools" / "docs_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_documentation_links_and_catalogues():
    assert not _docs_check_tool().check(ROOT)


def test_every_report_has_its_header_lines_and_open_follow_ups():  # IT-1K: the template's Date and Reviewed commit
    for report in sorted((ROOT / "issues").glob("*/r*/report.md")):
        head = "\n".join(report.read_text(encoding="utf-8").splitlines()[:8])
        assert re.search(r"^Date: \d{4}-\d\d-\d\d", head, re.M), f"{report.parent.name}: no Date: line"
        assert re.search(r"Reviewed commit: `?[0-9a-f]{7,40}", head), f"{report.parent.name}: no Reviewed commit: line"
    spec = importlib.util.spec_from_file_location("issues_tool", ROOT / "tools" / "issues.py")
    issues = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(issues)
    open_codes = {i["code"] for m in issues.load()[0] for i in m["items"]}
    rows = re.findall(r"^\| [a-z0-9.-]+ \| \[.*\]\(.*\) \| [\d-]+ \| (\w+) \| (.*) \|$",
                      (ROOT / "issues" / "REPORTS.md").read_text(encoding="utf-8"), re.M)
    assert len(rows) == len(list((ROOT / "issues").glob("*/r*/report.md")))
    for kind, follow in rows:
        assert kind in ("audit", "review", "release", "research", "reference")
        finished = {c for c in follow.split(", ") if c != "none"} - open_codes
        assert not finished, f"issues/REPORTS.md lists finished items as open follow-ups: {sorted(finished)}"


def test_mirror_check_detects_missing_arabic_and_changed_voice(tmp_path):
    own, peer = tmp_path / "app", tmp_path / "site"
    for base in (own, peer):
        (base / "guideline").mkdir(parents=True)
        (base / "guideline" / "brand-voice.md").write_text("same")
    (own / "guideline" / "phone-ar.html").write_text("Arabic")
    (peer / "guideline" / "brand-voice.md").write_text("changed")
    errors = _docs_check_tool().mirrors(own, peer)
    assert any("phone-ar.html" in error and "missing" in error for error in errors)
    assert any("brand-voice.md" in error and "differs" in error for error in errors)


def test_documentation_check_detects_unregistered_reports_and_dead_links(tmp_path):
    for name in ("docs", "feedback", "templates", "guideline", "issues"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "README.md").write_text("# Index")
    (tmp_path / "issues" / "REPORTS.md").write_text("# Reports\n")
    folder = tmp_path / "issues" / "3-polish" / "r1-review"
    folder.mkdir(parents=True)
    (folder / "report.md").write_text("[Lost evidence](evidence/missing.png)")
    errors = _docs_check_tool().check(tmp_path)
    assert any("missing link evidence/missing.png" in error for error in errors)
    assert any("absent from catalogue" in error for error in errors)


def test_report_codes_are_sequential_unique_and_in_their_folder_names():  # reports are r1, r2, ... in order written
    tool = _docs_check_tool()
    folders = [d for pic in (ROOT / "issues").iterdir() if pic.is_dir() for d in pic.iterdir()]
    folders += list((ROOT / "ai" / "archive" / "reports").iterdir())
    codes = [int(d.name.split("-")[0][1:]) for d in folders if d.is_dir() and re.match(r"r\d+-", d.name)]
    assert sorted(codes) == list(range(1, len(codes) + 1))
    assert tool.next_report_code(ROOT) == f"r{len(codes) + 1}"


def test_finished_milestones_move_to_the_archive(tmp_path):
    spec = importlib.util.spec_from_file_location("archive_tool", ROOT / "tools" / "archive.py")
    archive = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(archive)
    issues = tmp_path / "issues"
    (issues / "5-done").mkdir(parents=True)
    (issues / "5-done" / "README.md").write_text("---\ntitle: Done\ndone: 5A, 5B\n---\n")
    (issues / "6-open").mkdir()
    (issues / "6-open" / "README.md").write_text("---\ntitle: Open\n---\n")
    (issues / "6-open" / "6A-item.md").write_text("item")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "page.md").write_text("[old](../issues/5-done/README.md)\n")
    assert [d.name for d in archive.finished_milestones(tmp_path)] == ["5-done"]
    archive.archive_milestone(tmp_path, issues / "5-done")
    assert (tmp_path / "ai" / "archive" / "issues" / "5-done" / "README.md").exists()
    assert "5A, 5B" in (tmp_path / "ai" / "archive" / "issues" / "README.md").read_text()
    assert "../ai/archive/issues/5-done/README.md" in (tmp_path / "docs" / "page.md").read_text()


def test_reserved_report_codes_are_skipped_and_duplicate_report_numbers_fail(tmp_path):
    tool = _docs_check_tool()
    for name in ("docs", "feedback", "templates", "guideline", "issues"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "README.md").write_text("# Index")
    catalogue = ["# Reports"]
    for subject in ("r30-a", "r30-b"):
        folder = tmp_path / "issues" / "3-polish" / subject
        folder.mkdir(parents=True)
        (folder / "report.md").write_text("Code: r30\n")
        catalogue.append(f"[x]({'3-polish/' + subject + '/report.md'})")
    (tmp_path / "issues" / "REPORTS.md").write_text("\n".join(catalogue))
    assert any("code r30 is also used" in error for error in tool.check(tmp_path))
    assert tool.next_report_code(tmp_path) == "r31"
    (tmp_path / "NOW.md").write_text("## Claimed\n\nReserved codes: r31 Claude, 12U-12W Claude\n")
    assert tool.next_report_code(tmp_path) == "r32"
