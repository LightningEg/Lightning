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
    text = board.tally(data, board.derive(data), 3)
    assert "Start now" not in text and "Running" not in text and "Shipped" not in text
    assert 'href="https://github.com/LightningEg/Lightning/issues/4"' in board.page(data, board.derive(data))


def test_every_open_issue_lands_in_ready_blocked_or_parked():
    got, data = rows([issue(1, ["when:launch"]), issue(2, ["when:launch"], blocked_by=[1]),
                      issue(3, ["when:launch", "can:owner"]), issue(4, ["when:launch"]),
                      issue(5, ["when:after-launch"]), issue(6, ["when:someday"]), issue(7),
                      issue(8, ["when:launch"], children=[9]), issue(9)], [pr(10, "Closes #4")])
    kinds = {n: board.bucket(r) for n, r in got.items() if r["state"] != "group"}
    assert kinds == {1: "ready", 2: "blocked", 3: "ready", 4: "ready", 5: "parked", 6: "parked", 7: "parked",
                     9: "ready"}, "a step takes launch from its parent; an issue with no when: is parked"
    text = board.tally(data, board.derive(data), 2)
    assert "[taken: PR #10]" in text and "[owner]" in text
    assert text.index("Ready (") < text.index("Blocked (") < text.index("Parked (")


def test_a_status_label_set_by_the_owner_wins_over_the_worked_out_list():
    got, data = rows([issue(1, ["when:launch", "status:parked"]), issue(2, ["when:after-launch", "status:ready"]),
                      issue(3, ["when:launch", "status:blocked"]), issue(4, ["when:launch"])])
    assert {n: board.bucket(r) for n, r in got.items()} == {1: "parked", 2: "ready", 3: "blocked", 4: "ready"}
    assert [i["n"] for i in board.pick(board.derive(data), cap=4)] == [4], "a parked or blocked pick is never started"


def test_the_owners_priority_issue_orders_every_list_and_is_not_itself_a_row():
    prio = issue(9, title="[PRIORITY] Order", body="First is first.\n1. #3 the third\n2. #1\n3. #3 again\n4. #2")
    got, data = rows([issue(1, ["when:launch"]), issue(2, ["when:launch"]), issue(3, ["when:after-launch"]),
                      issue(4, ["when:launch"], blocking=5), prio])
    assert 9 not in got, "the order issue never appears as work"
    assert [r["n"] for r in board.derive(data)] == [3, 1, 2, 4], "ranked first in the owner's order, a repeat counts once, the rest follow"
    assert got[3]["rank"] == 0 and got[4]["rank"] is None
    text = board.tally(data, board.derive(data), 2)
    assert text.index("#1 ") < text.index("#2 ") < text.index("#4 ")
    assert [i["n"] for i in board.pick(board.derive(data), cap=2)] == [1, 2], "AIs start the owner's first ready issues"
