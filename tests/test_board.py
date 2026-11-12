"""The board works out each issue's state from GitHub's facts; nobody types a state."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("board", ROOT / "tools" / "board.py")
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)

NOW = "2026-11-11T12:00:00+00:00"


def issue(n, labels=(), body="", children=(), blocked_by=(), assignees=(), blocking=0, title=None):
    return {"n": n, "title": title or f"Issue {n}", "body": body, "labels": list(labels), "assignees": list(assignees),
            "children": list(children), "blocked_by": list(blocked_by), "blocking": blocking}


def pr(n, body, updated="2026-11-11T11:00:00Z"):
    return {"n": n, "title": f"PR {n}", "body": body, "branch": f"claude/x{n}", "draft": True, "updated": updated}


def rows(issues, prs=()):
    data = {"issues": issues, "prs": list(prs), "merged": [], "now": NOW}
    return {r["n"]: r for r in board.derive(data)}, data


def test_a_step_takes_when_can_and_area_from_its_parent_unless_it_says_otherwise():
    got, _ = rows([issue(1, ["when:launch", "can:opus"], "Area: lightning/sync, tests", children=[2, 3]),
                   issue(2), issue(3, body="Can: sonnet\nArea: lightning/ui/static")])
    assert got[1]["state"] == "group"
    assert (got[2]["when"], got[2]["can"], got[2]["areas"]) == ("launch", "opus", {"lightning/sync"})
    assert (got[3]["can"], got[3]["areas"]) == ("sonnet", {"lightning/ui/static"})


def test_an_open_pull_request_that_closes_it_makes_it_running_and_an_old_one_stale():
    got, _ = rows([issue(1, ["when:launch"]), issue(2, ["when:launch"])],
                  [pr(10, "Closes #1"), pr(11, "fixes #2", updated="2026-11-08T11:00:00Z")])
    assert got[1]["state"] == "running" and got[2]["state"] == "stale"


def test_blockers_are_native_ones_an_open_pull_request_or_something_outside():
    got, _ = rows([issue(1, ["when:launch"], blocked_by=[9]), issue(9, ["when:launch"]),
                   issue(2, ["when:launch"], "Blocked by: PR #10 (prices)"),
                   issue(3, ["when:launch"], "Blocked by: PR #77"),
                   issue(4, ["when:launch"], "Blocked by: a test from a home connection (human)"),
                   issue(5, ["when:launch"], "Blocked by: none"),
                   issue(6, ["when:launch"], blocked_by=[9], children=[7]), issue(7)], [pr(10, "")])
    assert got[1]["state"] == "blocked" and got[1]["why"] == ["#9"]
    assert got[2]["state"] == "blocked" and got[3]["state"] == "ready", "a merged or closed pull request no longer blocks"
    assert got[4]["state"] == "blocked" and got[5]["state"] == "ready"
    assert got[7]["state"] == "blocked", "a step waits for what its parent waits for"


def test_people_work_is_set_apart_and_the_same_area_is_never_run_twice():
    got, data = rows([issue(1, ["when:launch", "can:owner"]),
                      issue(2, ["when:launch"], "Area: lightning/ui/static"),
                      issue(3, ["when:launch"], "Area: lightning/ui/static/app.js, tests"),
                      issue(7, ["when:launch"], "Area: lightning/ui, lightning/sync/journal"),
                      issue(4, ["when:launch"], "Area: lightning/sync", blocking=2),
                      issue(5, ["when:launch"], "Area: lightning/sync"),
                      issue(6, ["when:after-launch"], "Area: guideline")], [pr(10, "Closes #2")])
    assert got[1]["state"] == "person" and got[3]["state"] == "held"
    assert got[7]["state"] == "ready", "a whole folder such as lightning/ui is too broad to hold anything back"
    picked = [i["n"] for i in board.pick(board.derive(data), cap=3)]
    assert picked == [4], "one already runs, the most-unblocking goes first, #5 shares its area, #6 is not for launch"
    assert "Start now" in board.tally(data, board.derive(data), 3)
    assert 'href="https://github.com/LightningEg/Lightning/issues/4"' in board.page(data, board.derive(data))
