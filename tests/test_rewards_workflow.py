"""The rewards workflow (8Q part 1): every merge counts, and the safety rules stay.

A merged pull request from someone who is not a bot or the owner is ALWAYS reported to record_merge first, closing an
issue or not; award_merge (coins) follows only when issues were closed. The workflow never checks out pull request
code and never puts ${{ }} inside the script.
"""
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "rewards.yml"


def merged_job() -> str:
    text = WORKFLOW.read_text()
    return text[text.index("\n  merged:"):]


def script() -> str:
    job = merged_job()
    return job[job.index("      - run: |"):]


def test_a_merge_with_no_issue_still_reaches_record_merge():
    body = script()
    non_owner = body[body.index("          else\n"):]
    assert "rpc record_merge" in non_owner
    before = non_owner[:non_owner.index("rpc record_merge")]
    assert "exit 0" not in before, "no early exit before the merge is recorded"
    assert non_owner.index("rpc record_merge") < non_owner.index("rpc award_merge")
    # coins only when the pull request closed an issue
    assert '"$issues" == "[]"' in non_owner[non_owner.index("rpc record_merge"):non_owner.index("rpc award_merge")]
    # the old early exit for 'no issue' is gone from the top of the script
    top = body[:body.index("if [[ \"$AUTHOR_TYPE\"")]
    assert "exit 0" not in top


def test_the_size_comes_from_the_file_list_without_lockfiles_and_generated_files():
    body = script()
    assert "gh pr view \"$PR\" --json files" in body
    for pattern in (r"\\.lock$", r"lock\\.json$", r"\\.generated\\.", r"\\.min\\."):
        assert pattern in body
    assert "p_lines:$lines" in body


def test_bots_and_the_owner_never_reach_record_merge():
    body = script()
    owner = body[body.index("if [[ \"$AUTHOR_TYPE\""):body.index("          else\n")]
    assert "record_merge" not in owner and "award_merge" not in owner
    assert "close_rewarded_issues" in owner


def test_the_safety_rules_stay():
    assert "actions/checkout" not in WORKFLOW.read_text()
    assert "${{" not in script(), "values reach the shell through env, never through ${{ }} in the script"
    assert "pull_request_target" in WORKFLOW.read_text()
    assert "jq -nc" in script()


def test_a_failed_points_call_never_stops_the_coins():
    """record_merge runs first under `set -e`; if it fails (not deployed yet), award_merge must still run."""
    body = script()
    call = body[body.index("rpc record_merge"):body.index("rpc award_merge")]
    assert '|| echo "::warning::record_merge failed' in call


def offer_job() -> str:
    text = WORKFLOW.read_text()
    start = text.index("\n  offer:")
    return text[start:text.index("\n  merged:")]


def test_a_coins_label_publishes_an_offer_only_for_people_who_can_write():
    text = WORKFLOW.read_text()
    assert "types: [assigned, unassigned, labeled, unlabeled]" in text
    job = offer_job()
    body = job[job.index("      - run: |"):]
    assert "${{" not in body, "label, login and title reach the script through env"
    assert "actions/checkout" not in text
    assert r"^coins:[0-9]{1,5}$" in body
    assert "collaborators/$SENDER/permission" in body
    # the permission check comes before any call to the database, and only write, maintain or admin pass
    assert body.index("collaborators/$SENDER/permission") < body.index("rpc publish_offer_from_label")
    assert body.index("collaborators/$SENDER/permission") < body.index("rpc close_offer_from_label")
    assert "admin|maintain|write) ;;" in body
    assert "publish_offer_from_label" in body and "close_offer_from_label" in body
    assert "github.event.sender.type != 'Bot'" in job


def test_assignment_events_only_reach_the_claim_job():
    text = WORKFLOW.read_text()
    claim = text[text.index("\n  claim:"):text.index("\n  offer:")]
    assert "github.event.action == 'assigned'" in claim and "github.event.action == 'unassigned'" in claim
