"""Protect the setup tool's mutation and ruleset-selection boundaries."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('security_setup', ROOT / 'tools/security_setup.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)

class FakeGitHub:
    apply = True
    def __init__(self):
        self.writes = []
    def collection(self, _):
        return [{'id': 10, 'name': 'unrelated', 'target': 'branch'},
                {'id': 20, 'name': 'intended', 'target': 'branch'}]
    def api(self, method, path, body=None, **kwargs):
        if method == 'GET':
            return {'rules': [{'type': 'required_signatures'}, {'type': 'pull_request', 'parameters': {'require_extra_approval_for_unattributed_changes': True}}]}
        self.writes.append((method, path, body))

def test_ruleset_update_matches_name_and_preserves_extra_restrictions():
    gh = FakeGitHub()
    setup.upsert_ruleset(gh, 'owner/repo', setup.branch_rules('intended'))
    method, endpoint, body = gh.writes[0]
    assert method == 'PUT' and endpoint.endswith('/20')
    assert any(r['type'] == 'required_signatures' for r in body['rules'])
    params = next(r['parameters'] for r in body['rules'] if r['type'] == 'pull_request')
    assert params['require_extra_approval_for_unattributed_changes'] is True
    assert body['bypass_actors'] == [{'actor_id': 5, 'actor_type': 'RepositoryRole', 'bypass_mode': 'pull_request'}]

def test_missing_ruleset_is_created_without_overwriting_another():
    gh = FakeGitHub()
    setup.upsert_ruleset(gh, 'owner/repo', setup.branch_rules('new'))
    assert gh.writes[0][0:2] == ('POST', 'repos/owner/repo/rulesets')

def test_default_preview_never_launches_mutating_api_commands(monkeypatch):
    launched = []
    def run(cmd, **kwargs):
        launched.append(cmd)
        return SimpleNamespace(returncode=0, stdout='{}', stderr='')
    monkeypatch.setattr(setup.subprocess, 'run', run)
    gh = setup.GitHub()
    for method in ['POST', 'PUT', 'PATCH', 'DELETE']:
        gh.api(method, 'repos/owner/repo/rulesets', {'test': True})
    assert launched == []
    gh.api('GET', 'user')
    assert len(launched) == 1

def test_market_rules_do_not_grant_general_ai_or_actions_bypass():
    rules = setup.branch_rules('price publication', updates_only=True)
    assert any(rule['type'] == 'update' for rule in rules['rules'])
    assert rules['bypass_actors'] == [{'actor_id': 5, 'actor_type': 'RepositoryRole', 'bypass_mode': 'always'}]


def test_workflow_actions_match_app_policy():
    """Every external action is pinned and allowed by the policy the tool installs."""
    import re
    seen_third_party = set()
    workflows = ROOT / '.github/workflows'
    for workflow in (*workflows.glob('*.yml'), *workflows.glob('*.yaml')):
        for line in workflow.read_text(encoding='utf-8').splitlines():
            match = re.search(r'\buses:\s*[\'"]?([^\s\'"]+)', line)
            if not match:
                continue
            action = match.group(1)
            if action.startswith('./'):
                continue
            assert re.fullmatch(r'[^@\s]+@[0-9a-f]{40}', action), (workflow, action)
            if not action.lower().startswith(('actions/', 'github/', setup.ORG.lower() + '/')):
                seen_third_party.add(action)
                assert action in setup.APP_ACTION_PATTERNS, (workflow, action)
    assert seen_third_party == set(setup.APP_ACTION_PATTERNS)


class FakeActions:
    def __init__(self, apply=False, *, owner=True, admin=True, selected=True):
        self.apply, self.owner, self.admin, self.selected = apply, owner, admin, selected
        self.calls, self.writes = [], []
        self.current = {'github_owned_allowed': True, 'verified_allowed': False,
                        'patterns_allowed': ['other/action@abcdef', setup.OLD_GRADLE_ACTION]}

    def api(self, method, path, body=None, **kwargs):
        self.calls.append((method, path))
        if method == 'GET' and path == 'user':
            return {'login': setup.OWNER if self.owner else 'someone-else', 'id': 1}
        if method == 'GET' and path == f'repos/{setup.APP}':
            return {'permissions': {'admin': self.admin}}
        if method == 'GET' and path == f'repos/{setup.APP}/actions/permissions':
            return {'enabled': True, 'allowed_actions': 'selected' if self.selected else 'all'}
        if method == 'GET' and path == f'repos/{setup.APP}/actions/permissions/selected-actions':
            return self.current
        if method != 'GET' and self.apply:
            self.writes.append((method, path, body))
        return None


def test_app_actions_only_previews_and_mutates_only_selected_policy(monkeypatch, capsys):
    preview = FakeActions()
    monkeypatch.setattr(setup, 'GitHub', lambda apply=False: preview)
    assert setup.main(['--app-actions-only']) == 0
    assert not preview.writes
    assert setup.APP_ACTION_PATTERNS[1] in capsys.readouterr().out
    assert all(path == 'user' or path.startswith(f'repos/{setup.APP}') for _, path in preview.calls)

    applied = FakeActions(apply=True)
    monkeypatch.setattr(setup, 'GitHub', lambda apply=False: applied)
    assert setup.main(['--app-actions-only', '--apply']) == 0
    assert len(applied.writes) == 1
    method, path, body = applied.writes[0]
    assert (method, path) == ('PUT', f'repos/{setup.APP}/actions/permissions/selected-actions')
    assert body['github_owned_allowed'] is True and body['verified_allowed'] is False
    assert body['patterns_allowed'] == ['other/action@abcdef', *setup.APP_ACTION_PATTERNS]
    assert setup.OLD_GRADLE_ACTION not in body['patterns_allowed']


def test_app_actions_only_refuses_missing_owner_admin_or_selected_policy(monkeypatch):
    import pytest
    for fake in (FakeActions(apply=True, owner=False), FakeActions(apply=True, admin=False),
                 FakeActions(apply=True, selected=False)):
        monkeypatch.setattr(setup, 'GitHub', lambda apply=False: fake)
        with pytest.raises(RuntimeError):
            setup.main(['--app-actions-only', '--apply'])
        assert fake.writes == []
    with pytest.raises(SystemExit):
        setup.main(['--app-actions-only', '--org-controls'])


def test_app_actions_only_requires_complete_existing_policy():
    import pytest
    fake = FakeActions(apply=True)
    fake.current.pop('verified_allowed')
    with pytest.raises(RuntimeError, match='complete'):
        setup.update_app_actions(fake)
    assert fake.writes == []


def test_app_actions_only_preserves_flags_and_is_idempotent():
    fake = FakeActions(apply=True)
    fake.current = {'github_owned_allowed': False, 'verified_allowed': True,
                    'patterns_allowed': ['other/action@abcdef', *setup.APP_ACTION_PATTERNS]}
    setup.update_app_actions(fake)
    assert fake.writes == []
    fake.current['patterns_allowed'].remove(setup.APP_ACTION_PATTERNS[1])
    setup.update_app_actions(fake)
    assert fake.writes[0][2]['github_owned_allowed'] is False
    assert fake.writes[0][2]['verified_allowed'] is True
    assert fake.writes[0][2]['patterns_allowed'] == ['other/action@abcdef', *setup.APP_ACTION_PATTERNS]
