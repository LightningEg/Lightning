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
