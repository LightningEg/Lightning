"""Skills stay findable and true: one folder each, listed in the README, with a Claude stub, naming only tools that exist."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
# These skills work in the website repository, whose tools are not in this one.
WEBSITE_SKILLS = {"owner-console-view", "supabase-migration", "website-sync", "site-recapture", "usage-question"}


def _folders():
    return sorted(p for p in SKILLS.iterdir() if p.is_dir())


def _front(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0] == "---", f"{path} has no front matter"
    out = {}
    for line in lines[1:]:
        if line == "---":
            return out
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    raise AssertionError(f"{path}: front matter never closes")


def test_every_skill_has_a_matching_name_and_a_real_description():
    assert len(_folders()) >= 19
    for folder in _folders():
        meta = _front(folder / "SKILL.md")
        assert meta["name"] == folder.name, f"{folder.name}: name must equal its folder"
        assert 60 <= len(meta["description"]) <= 700, f"{folder.name}: description says when to use it, in 60-700 characters"


def test_every_skill_is_listed_in_the_readme_and_has_a_claude_stub():
    readme = (SKILLS / "README.md").read_text(encoding="utf-8")
    for folder in _folders():
        assert f"]({folder.name}/SKILL.md)" in readme, f"skills/README.md does not list {folder.name}"
        stub = ROOT / ".claude" / "skills" / folder.name / "SKILL.md"
        assert stub.is_file(), f".claude/skills/{folder.name}/SKILL.md is missing"
        assert _front(stub)["name"] == folder.name
        assert f"skills/{folder.name}/SKILL.md" in stub.read_text(encoding="utf-8"), f"{folder.name}: the stub must point at the skill"


def test_a_skill_names_only_tools_and_skills_that_exist():
    names = {p.name for p in _folders()}
    for folder in _folders():
        text = (folder / "SKILL.md").read_text(encoding="utf-8")
        if folder.name not in WEBSITE_SKILLS:
            for tool in set(re.findall(r"\btools/[a-z_]+\.py\b", text)):
                assert (ROOT / tool).is_file(), f"{folder.name} names {tool}, which does not exist"
        for other in set(re.findall(r"skill `([a-z-]+)`", text)):
            assert other in names, f"{folder.name} points at skill {other}, which does not exist"
