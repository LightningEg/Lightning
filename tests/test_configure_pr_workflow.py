"""Prevent the owner-account setup from bypassing checks or writing during preview."""
import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'configure_pr_workflow', Path(__file__).resolve().parents[1] / 'tools/configure_pr_workflow.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def fake_api(monkeypatch, *, blocking_review=False):
    calls = []
    previous = {
        'id': 12, 'name': 'existing main', 'target': 'branch', 'enforcement': 'active',
        'source_type': 'Repository',
        'bypass_actors': [] if blocking_review else [
            {'actor_type': 'RepositoryRole', 'actor_id': 5, 'bypass_mode': 'pull_request'}],
        'rules': [
            {'type': 'pull_request', 'parameters': {'required_approving_review_count': 1}},
            {'type': 'required_status_checks', 'parameters': {
                'required_status_checks': [{'context': 'extra-check', 'integration_id': 42}]}},
        ],
    }

    def api(method, path, body=None, **kwargs):
        calls.append((method, path, body))
        assert method == 'GET', 'Preview/preflight unexpectedly attempted a write'
        if path == 'user':
            return {'login': 'elfekimuhammed'}
        if path.endswith('/rulesets/12'):
            return copy.deepcopy(previous)
        if '/rulesets?' in path:
            return [copy.deepcopy(previous)]
        if '/rules/branches/' in path:
            return [{'ruleset_id': 12}]
        if path.endswith('/protection'):
            return None
        return {'permissions': {'admin': True}, 'default_branch': 'main', 'allow_squash_merge': True}

    monkeypatch.setattr(setup, 'api', api)
    return calls


def test_preview_reads_both_repos_without_writes(monkeypatch, capsys):
    calls = fake_api(monkeypatch)
    assert setup.main([]) == 0
    assert all(method == 'GET' for method, _, _ in calls)
    output = capsys.readouterr().out
    assert 'Preview only' in output and 'LightningEg/Lightning_website' in output


def test_guard_has_no_bypass_and_preserves_existing_bound_check(monkeypatch):
    fake_api(monkeypatch)
    plan = setup.prepare('LightningEg/Lightning', ['tests'])
    desired = plan['desired']
    assert desired['bypass_actors'] == []
    rules = {r['type']: r.get('parameters', {}) for r in desired['rules']}
    assert rules['pull_request']['required_approving_review_count'] == 0
    assert rules['pull_request']['require_code_owner_review'] is False
    assert rules['pull_request']['require_last_push_approval'] is False
    assert rules['pull_request']['require_extra_approval_for_unattributed_changes'] is False
    assert rules['pull_request']['required_reviewers'] == []
    assert rules['pull_request']['required_review_thread_resolution'] is True
    assert rules['pull_request']['allowed_merge_methods'] == ['squash']
    assert {'type': 'non_fast_forward'} in desired['rules']
    assert rules['required_status_checks']['strict_required_status_checks_policy'] is False
    assert {'context': 'extra-check', 'integration_id': 42} in rules[
        'required_status_checks']['required_status_checks']


def test_conflicting_review_rule_stops_apply_before_any_writes(monkeypatch):
    calls = fake_api(monkeypatch, blocking_review=True)
    with pytest.raises(RuntimeError, match='still requires another identity'):
        setup.main(['--apply'])
    assert all(method == 'GET' for method, _, _ in calls)


@pytest.mark.parametrize('change', ['bypass', 'inactive', 'checks'])
def test_readback_rejects_incomplete_or_bypassed_guard(change):
    desired = setup.desired_rules([{'context': 'tests'}])
    actual = copy.deepcopy(desired)
    if change == 'bypass':
        actual['bypass_actors'] = [{'actor_type': 'RepositoryRole', 'actor_id': 5,
                                    'bypass_mode': 'always'}]
    elif change == 'inactive':
        actual['enforcement'] = 'disabled'
    else:
        actual['rules'] = [r for r in actual['rules'] if r['type'] != 'required_status_checks']
    with pytest.raises(RuntimeError):
        setup.verify(actual, desired)


def test_readback_accepts_server_defaults_but_rejects_changed_check_identity():
    desired = setup.desired_rules([{'context': 'tests'}, {'context': 'security', 'integration_id': 42}])
    actual = copy.deepcopy(desired)
    checks = actual['rules'][-1]['parameters']['required_status_checks']
    checks[0]['integration_id'] = None
    setup.verify(actual, desired)
    checks[1]['integration_id'] = 99
    with pytest.raises(RuntimeError, match='changed required check'):
        setup.verify(actual, desired)
