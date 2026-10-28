"""issues/ holds the plan: milestone folders with well-formed, uniquely coded items, and a current INDEX.md (tools/issues.py)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _tool():
    spec = importlib.util.spec_from_file_location("issues_tool", ROOT / "tools" / "issues.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_item_is_well_formed_coded_once_and_indexed():
    module = _tool()
    milestones, problems = module.load()
    assert not problems, problems
    assert (ROOT / "issues" / "INDEX.md").read_text(encoding="utf-8") == module.render(milestones), "run python tools/issues.py"


def test_codes_run_a_to_z_then_aa_and_never_reuse_a_done_code():
    module = _tool()
    assert [module.letters(n) for n in (1, 26, 27, 28)] == ["A", "Z", "AA", "AB"]
    milestone = {"n": 3, "items": [{"code": "3A"}, {"code": "3C"}], "done": ["3D"]}
    assert module.next_code(milestone) == "3E"
    assert module.next_code({"n": 9, "items": [], "done": []}) == "9A"


def test_the_tag_says_bug_or_improvement_and_visual_or_technical():
    module = _tool()
    cases = [({"type": "bug", "look": "visual"}, "BV"), ({"type": "bug", "look": "technical"}, "BT"),
             ({"type": "polish"}, "IV"), ({"type": "polish", "look": "technical"}, "IT"), ({"type": "tech"}, "IT"),
             ({"type": "feature"}, "NF"), ({"type": "owner"}, "OW")]
    assert [module.tag(meta) for meta, _ in cases] == [want for _, want in cases]
    assert module.look_problem({"type": "bug"}) and module.look_problem({"type": "tech", "look": "visual"})
    assert module.look_problem({"type": "bug", "look": "technical"}) is None
