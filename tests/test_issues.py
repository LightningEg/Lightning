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


def test_a_bug_says_how_bad_it_is_and_every_area_is_on_the_list():  # IT-1K
    module = _tool()
    assert module.severity_problem({"type": "bug"}) and module.severity_problem({"type": "bug", "severity": "urgent"})
    assert module.severity_problem({"type": "bug", "severity": "high"}) is None
    assert module.severity_problem({"type": "feature", "severity": "low"})  # only bugs have one
    milestones, _ = module.load()
    assert {i["pillar"] for m in milestones for i in m["items"]} <= set(module.PILLARS)
    index = module.render(milestones)
    bugs = [i for m in milestones for i in m["items"] if i["type"] == "bug"]
    assert bugs and all(f"**{i['tag']}-{i['code']}**" in line and f"· {i['severity']} |" in line
                        for i in bugs for line in index.splitlines() if f"**{i['tag']}-{i['code']}**" in line)


def test_a_building_item_without_a_claim_warns_but_never_fails(tmp_path, monkeypatch, capsys):  # IT-1K
    module = _tool()
    now = tmp_path / "NOW.md"
    now.write_text("# Now\n\n## Claimed\n\n| Who | Work |\n|---|---|\n| Claude | BT-2A restore |\n\n## Next\n\n- 2B next\n",
                   encoding="utf-8")
    milestones = [{"items": [{"code": c, "status": s, "file": f"2-x/{c}-x.md"}
                             for c, s in (("2A", "building"), ("2B", "building"), ("2AB", "building"), ("2C", "ready"))]}]
    warned = module.warnings(milestones, now)
    assert [w.split()[1] for w in warned] == ["2-x/2B-x.md", "2-x/2AB-x.md"]  # 2B is only in Next; 2AB is not 2A
    monkeypatch.setattr(module, "warnings", lambda _milestones: ["warning: 9Z is building"])
    monkeypatch.setattr(module.sys, "argv", ["issues.py", "--check"])
    assert module.main() == 0 and "warning: 9Z" in capsys.readouterr().out
