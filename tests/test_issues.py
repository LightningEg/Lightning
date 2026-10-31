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


def _item(code="9Z", **meta):
    base = {"type": "feature", "status": "ready", "pillar": "own", "size": "M", "tag": "NF", "code": code, "steps": [],
            "file": f"9-later/{code}-x.md", "title": "T"}
    return {**base, **meta}


def test_a_step_names_its_size_and_a_posted_step_its_issue():
    module = _tool()
    found = module.STEP.findall("## 5A1 The table · L\n## 5A2 Wrappers · M · #212\n## 5A3 Owner try · owner\n## 5A4 No size\n")
    assert found == [("5A1", "The table", "L", ""), ("5A2", "Wrappers", "M", "212"), ("5A3", "Owner try", "owner", ""),
                     ("5A4", "No size", "", "")]


def test_every_step_in_the_plan_has_a_size():
    module = _tool()
    milestones, _ = module.load()
    steps = [s for m in milestones for i in m["items"] for s in i["steps"]]
    assert steps and all(s["size"] in (*module.COINS, "owner") for s in steps)


def test_only_ready_unclaimed_sized_work_is_offered_to_contributors():
    module = _tool()
    step = lambda code, size, github="": {"code": code, "title": "s", "size": size, "github": github}
    milestones = [{"items": [
        _item("9A"),                                                    # ready, no steps: offered
        _item("9B", status="building"), _item("9C", status="new"), _item("9D", status="blocked"),
        _item("9E", type="owner", size=None, tag="OW"), _item("9F", post="no"),   # held: owner task, kept off the list
        _item("9G", size="L"),                                          # large and unsplit: split it first
        _item("9H", github="12"),                                       # already on GitHub
        _item("9J", size="L", steps=[step("9J1", "M"), step("9J2", "owner"), step("9J3", "S", "30")]),
    ]}]
    units, held = module.post_units(milestones)
    assert [u["code"] for u in units] == ["NF-9A", "NF-9J1"]
    why = dict(held)
    assert "building" in why["NF-9B"] and "new" in why["NF-9C"] and "blocked" in why["NF-9D"]
    assert why["OW-9E"] == "owner task" and "post: no" in why["NF-9F"] and "split" in why["NF-9G"]
    assert "#12" in why["NF-9H"] and why["NF-9J2"] == "owner step" and "#30" in why["NF-9J3"]


def test_an_issue_body_links_to_github_not_to_a_relative_path():
    module = _tool()
    text = module.absolute_links("See [the report](../../reports/a/report.md#x) and [web](https://e.com) and [here](#top).",
                                 "2-safe/2F-x.md")
    assert "(https://github.com/LightningEg/Lightning/blob/main/reports/a/report.md#x)" in text
    assert "(https://e.com)" in text and "(#top)" in text


def test_the_public_list_in_the_plan_carries_coins_and_never_an_owner_task():
    module = _tool()
    milestones, _ = module.load()
    units, _ = module.post_units(milestones)       # empty once everything contributor-ready is posted
    assert all(u["size"] in module.COINS and u["item"]["type"] != "owner" for u in units)
    unit = {"code": "NF-9Z", "title": "T", "size": "M", "item": _item("9Z", file="9-later/9Z-x.md", pillar="own"), "step": None}
    assert module.COINS["M"] == 500 and module.coins_for(unit) == 500


def test_a_reward_can_be_raised_above_its_size_but_never_lowered():
    module = _tool()
    unit = {"item": _item(coins="800"), "step": None, "size": "M"}
    assert module.coins_for(unit) == 800
    assert module.coins_for({"item": _item(), "step": None, "size": "M"}) == 500
    assert module.coins_for({"item": _item(coins="800"), "step": {"code": "9Z1"}, "size": "S"}) == 200  # a step keeps its own size


def test_a_step_waits_until_the_steps_it_needs_are_finished():
    module = _tool()
    step = lambda code, needs=(): {"code": code, "title": "s", "size": "M", "github": "", "needs": list(needs)}
    milestones = [{"items": [_item("9K", size="L", steps=[step("9K1"), step("9K2", ["9K1"]), step("9K3", ["9K1", "9K2"]), step("9K4")])]}]
    units, held = module.post_units(milestones)
    assert [u["code"] for u in units] == ["NF-9K1", "NF-9K4"]
    assert dict(held)["NF-9K3"].startswith("waits for 9K1, 9K2") and "9K1" in dict(held)["NF-9K2"]
    milestones[0]["items"][0]["steps"].pop(0)           # 9K1 finished: its heading is gone, so 9K2 is offered
    assert "NF-9K2" in [u["code"] for u in module.post_units(milestones)[0]]


def test_the_needs_sentence_in_a_real_item_is_read(tmp_path):
    module = _tool()
    milestones, _ = module.load()
    five_a = next(i for m in milestones for i in m["items"] if i["code"] == "5A")
    needs = {s["code"]: s["needs"] for s in five_a["steps"]}
    assert needs["5A2"] == ["5A1"] and needs["5A4"] == ["5A1", "5A2"] and needs["5A1"] == []


def test_a_step_issue_does_not_repeat_the_item_plan_or_its_sibling_steps(tmp_path, monkeypatch):
    module = _tool()
    (tmp_path / "9-later").mkdir()
    (tmp_path / "9-later" / "9Z-x.md").write_text(
        "---\ntitle: T\n---\n\n## Report\nWhy this matters.\n\n## Fix\nThe whole plan: A then B.\n\n"
        "## 9Z1 First · M\nDo A. Done when: A works.\n\n## 9Z2 Second · M\nDo B.\n", encoding="utf-8")
    monkeypatch.setattr(module, "ISSUES", tmp_path)
    step = {"code": "9Z1", "title": "First", "size": "M", "github": "", "needs": []}
    body = module.issue_text({"code": "NF-9Z1", "title": "First", "size": "M", "item": _item("9Z", file="9-later/9Z-x.md"), "step": step})[1]
    assert "Do A. Done when: A works." in body and "Why this matters." in body
    assert "How it was planned" not in body and "The whole plan" not in body and "Do B." not in body
