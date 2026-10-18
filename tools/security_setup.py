"""Apply the documented GitHub security setup using the owner's local gh login.

Default: read settings and print planned writes. Add --apply to perform writes.
No token or signing key is read from GitHub or printed. No repository is transferred.
"""
from __future__ import annotations
import argparse
import copy
import getpass
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OWNER, ORG = 'elfekimuhammed', 'LightningEg'
APP = f'{ORG}/Lightning'
WEBSITE = f'{ORG}/Lightning_website'
DOWNLOADS = f'{ORG}/Lightning-downloads'
MARKET = f'{ORG}/Lightning_Market_Data'

class GitHub:
    def __init__(self, apply=False):
        self.apply = apply
    def api(self, method, path, body=None, optional=False):
        if method != 'GET' and not self.apply:
            print(f'PLAN {method} {path}')
            return None
        cmd = ['gh', 'api', '--method', method, path]
        if body is not None:
            cmd += ['--input', '-']
        result = subprocess.run(cmd, input=json.dumps(body) if body is not None else None, text=True, capture_output=True)
        if result.returncode:
            if optional and '404' in result.stderr:
                return None
            raise RuntimeError(f'{method} {path}: {result.stderr.strip()}')
        return json.loads(result.stdout) if result.stdout.strip() else None
    def collection(self, path):
        rows = []
        for page in range(1, 1001):
            values = self.api('GET', f'{path}{"&" if "?" in path else "?"}per_page=100&page={page}')
            if not isinstance(values, list):
                raise RuntimeError(f'Expected a collection: {path}')
            rows.extend(values)
            if len(values) < 100:
                return rows
        raise RuntimeError('Pagination limit reached')
    def secret(self, repo, name, value, environment=None):
        if not self.apply:
            print(f'PLAN set secret {repo}/{environment or "repository"}/{name}')
            return
        cmd = ['gh', 'secret', 'set', name, '--repo', repo]
        if environment:
            cmd += ['--env', environment]
        result = subprocess.run(cmd, input=value, text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(f'Could not set {name}; existing repository copy was retained.')

def upsert_ruleset(gh, repo, desired):
    """Match by name AND target. Never overwrite the first unrelated ruleset."""
    candidates = [r for r in gh.collection(f'repos/{repo}/rulesets')
                  if r['name'] == desired['name'] and r['target'] == desired['target']
                  and r.get('source_type', 'Repository') == 'Repository']
    if len(candidates) > 1:
        raise RuntimeError(f'Duplicate rulesets named {desired["name"]}; resolve manually.')
    if candidates:
        endpoint = f'repos/{repo}/rulesets/{candidates[0]["id"]}'
        current = gh.api('GET', endpoint)
        # Preserve stronger/extra rule types and parameter options on existing rulesets.
        by_type = {r['type']: copy.deepcopy(r) for r in current.get('rules', [])}
        for rule in desired['rules']:
            merged = by_type.get(rule['type'], {})
            params = {**merged.get('parameters', {}), **rule.get('parameters', {})}
            if rule['type'] == 'required_status_checks':
                checks = {c['context']: c for c in merged.get('parameters', {}).get('required_status_checks', [])}
                checks.update({c['context']: c for c in params['required_status_checks']})
                params['required_status_checks'] = list(checks.values())
            by_type[rule['type']] = {**merged, **rule}
            if params:
                by_type[rule['type']]['parameters'] = params
        desired = {**desired, 'rules': list(by_type.values())}
        gh.api('PUT', endpoint, desired)
    else:
        gh.api('POST', f'repos/{repo}/rulesets', desired)

def branch_rules(name, checks=(), updates_only=False):
    rules = [{'type': 'deletion'}, {'type': 'non_fast_forward'}]
    if updates_only:
        rules.append({'type': 'update'})
    else:
        rules.append({'type': 'pull_request', 'parameters': {
            'required_approving_review_count': 1, 'dismiss_stale_reviews_on_push': True,
            'require_code_owner_review': False, 'require_last_push_approval': True,
            'required_review_thread_resolution': True, 'allowed_merge_methods': ['squash']}})
        if checks:
            rules.append({'type': 'required_status_checks', 'parameters': {
                'strict_required_status_checks_policy': True,
                'required_status_checks': [{'context': c} for c in checks]}})
    return {'name': name, 'target': 'branch', 'enforcement': 'active',
            'conditions': {'ref_name': {'include': ['~DEFAULT_BRANCH'], 'exclude': []}},
            'bypass_actors': [{'actor_id': 5, 'actor_type': 'RepositoryRole',
                               'bypass_mode': 'always' if updates_only else 'pull_request'}], 'rules': rules}

def environment(gh, name, owner_id, repo=APP, approval=True, tags=True):
    endpoint = f'repos/{repo}/environments/{name}'
    gh.api('PUT', endpoint, {'wait_timer': 0, 'prevent_self_review': False,
        'reviewers': [{'type': 'User', 'id': owner_id}] if approval else [],
        'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True}})
    if not gh.apply:
        print(f'PLAN deployment restrictions for {name}: main branch' + (' and v* tags' if tags else ''))
        return
    existing = gh.api('GET', endpoint + '/deployment-branch-policies')['branch_policies']
    intended = {('branch', 'main'), ('tag', 'v*')} if tags else {('branch', 'main')}
    for kind, pattern in sorted(intended):
        if not any(x.get('type') == kind and x['name'] == pattern for x in existing):
            gh.api('POST', endpoint + '/deployment-branch-policies', {'type': kind, 'name': pattern})
    # Remove broad policies only after intended replacements exist.
    for policy in existing:
        if (policy.get('type'), policy['name']) not in intended:
            gh.api('DELETE', endpoint + f'/deployment-branch-policies/{policy["id"]}')

def migrate_secrets(gh):
    if not gh.apply:
        raise RuntimeError('--migrate-secrets requires --apply')
    names = ['ANDROID_KEYSTORE_BASE64', 'ANDROID_KEYSTORE_PASSWORD', 'ANDROID_KEY_ALIAS', 'ANDROID_KEY_PASSWORD']
    print('Enter the existing signing values. Input is hidden; blank cancels the migration.')
    values = {name: getpass.getpass(name + ': ') for name in names}
    if any(not v for v in values.values()):
        raise RuntimeError('Migration cancelled; no signing secrets were changed.')
    for name, value in values.items():
        gh.secret(APP, name, value, 'android-signing')
    for name in names:  # all destination writes succeeded before any source is removed
        gh.api('DELETE', f'repos/{APP}/actions/secrets/{name}')
    value = getpass.getpass('LIGHTNING_DOWNLOADS_TOKEN (blank to leave unchanged): ')
    if value:
        gh.secret(APP, 'LIGHTNING_DOWNLOADS_TOKEN', value, 'production-release')
        gh.api('DELETE', f'repos/{APP}/actions/secrets/LIGHTNING_DOWNLOADS_TOKEN')
    for repo, env, names in [(APP, 'market-publishing', ['LIGHTNING_MARKET_TOKEN']),
                             (WEBSITE, 'website-analytics', ['GOATCOUNTER_API_KEY', 'ANALYTICS_READ_KEY'])]:
        for name in names:
            value = getpass.getpass(name + ' (blank to leave unchanged): ')
            if value:
                gh.secret(repo, name, value, env)
                gh.api('DELETE', f'repos/{repo}/actions/secrets/{name}')

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--org-controls', action='store_true', help='Also enforce no default org access and required 2FA')
    p.add_argument('--migrate-secrets', action='store_true', help='Prompt for known signing/publish values and move them into environments')
    p.add_argument('--analytics-key', action='store_true', help='Prompt for the rotated analytics key and set the website GitHub secret')
    p.add_argument('--market-publisher-app-id', type=int, help='Optional dedicated publisher GitHub App ID; never use a general AI app here')
    args = p.parse_args(argv)
    gh = GitHub(args.apply)
    actor = gh.api('GET', 'user')
    if actor['login'].lower() != OWNER.lower():
        raise RuntimeError(f'Run this using the owner login @{OWNER}.')
    # Preflight every repository before starting any writes.
    for repo in [APP, WEBSITE, DOWNLOADS, MARKET]:
        if not gh.api('GET', f'repos/{repo}').get('permissions', {}).get('admin'):
            raise RuntimeError(f'Administrator access required: {repo}')
    if args.org_controls:
        disabled = gh.collection(f'orgs/{ORG}/members?filter=2fa_disabled')
        disabled += gh.collection(f'orgs/{ORG}/outside_collaborators?filter=2fa_disabled')
        if disabled:
            raise RuntimeError('Enroll these accounts in 2FA before enforcing it: ' + ', '.join(sorted({u['login'] for u in disabled})))
    if args.org_controls:
        gh.api('PATCH', f'orgs/{ORG}', {'default_repository_permission': 'none', 'two_factor_requirement_enabled': True})
    # The app's and website's main rule comes from configure_pr_workflow.py, run last (CONTRIBUTING.md › Owner: once).
    upsert_ruleset(gh, APP, json.loads((ROOT / '.github/rulesets/tags.json').read_text()))
    upsert_ruleset(gh, DOWNLOADS, branch_rules('security: downloads main'))
    market = branch_rules('security: price publication', updates_only=True)
    if args.market_publisher_app_id:
        market['bypass_actors'].append({'actor_id': args.market_publisher_app_id, 'actor_type': 'Integration', 'bypass_mode': 'always'})
    upsert_ruleset(gh, MARKET, market)
    tags = json.loads((ROOT / '.github/rulesets/tags.json').read_text())
    upsert_ruleset(gh, DOWNLOADS, tags)
    for repo in [APP, WEBSITE, DOWNLOADS, MARKET]:
        gh.api('PATCH', f'repos/{repo}', {'allow_squash_merge': True, 'allow_merge_commit': False,
            'allow_rebase_merge': False, 'allow_auto_merge': False, 'delete_branch_on_merge': True})
        gh.api('PUT', f'repos/{repo}/actions/permissions', {'enabled': True, 'allowed_actions': 'selected'})
        patterns = ['android-actions/setup-android@be39fa834029ff78f1a44aa3bb0819b8fc2bd8fd',
                    'gradle/actions/setup-gradle@0723195856401067f7a2779048b490ace7a47d7c'] if repo == APP else []
        gh.api('PUT', f'repos/{repo}/actions/permissions/selected-actions', {
            'github_owned_allowed': True, 'verified_allowed': False, 'patterns_allowed': patterns})
        gh.api('PUT', f'repos/{repo}/actions/permissions/workflow', {
            'default_workflow_permissions': 'read', 'can_approve_pull_request_reviews': False})
        gh.api('PUT', f'repos/{repo}/actions/permissions/fork-pr-contributor-approval', {'approval_policy': 'first_time_contributors'})
        gh.api('PUT', f'repos/{repo}/vulnerability-alerts')
        gh.api('PUT', f'repos/{repo}/automated-security-fixes')
        gh.api('PUT', f'repos/{repo}/private-vulnerability-reporting')
        gh.api('PATCH', f'repos/{repo}', {'security_and_analysis': {
            'secret_scanning': {'status': 'enabled'}, 'secret_scanning_push_protection': {'status': 'enabled'}}})
    environment(gh, 'android-signing', actor['id'])
    environment(gh, 'production-release', actor['id'])
    environment(gh, 'market-publishing', actor['id'], approval=False, tags=False)
    environment(gh, 'website-analytics', actor['id'], repo=WEBSITE, approval=False, tags=False)
    if args.migrate_secrets:
        migrate_secrets(gh)
    if args.analytics_key:
        if not args.apply:
            raise RuntimeError('--analytics-key requires --apply')
        key = getpass.getpass('New analytics key (hidden): ')
        if not key:
            raise RuntimeError('No key supplied')
        gh.secret(WEBSITE, 'ANALYTICS_READ_KEY', key, 'website-analytics')
        gh.api('DELETE', f'repos/{WEBSITE}/actions/secrets/ANALYTICS_READ_KEY')
    pr_rule = subprocess.run([sys.executable, str(ROOT / 'tools/configure_pr_workflow.py')] + (['--apply'] if args.apply else []))
    if pr_rule.returncode and args.apply:
        raise RuntimeError('The main-branch PR rule was not activated; read the message above.')
    print('Applied.' if args.apply else 'Preview only; add --apply to perform these writes.')
    print('No accounts were added or removed. Check with one harmless contributor PR from a fork.')
    print('Market publishing now requires an owner-admin identity or the explicitly supplied publisher App; verify the scheduled collector.')
    print('Secret migration requires known secret values; GitHub cannot return stored values. Deployment and bot identity setup remain separate.')
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
