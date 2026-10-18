"""Require branches, PRs and passing checks while allowing owner-account merges.

Run without arguments to preview. --apply saves the old rules locally, installs
a rule with no bypass, then reads it back. Requires the owner's local gh login.
This tool changes only the app/website rulesets, not accounts or secrets.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from urllib.parse import quote

OWNER = 'elfekimuhammed'
RULE_NAME = 'main: PR and checks, no bypass'
REPOSITORIES = {
    'LightningEg/Lightning': ['tests', 'dependency-review', 'analyze'],
    'LightningEg/Lightning_website': ['website-security'],
}


def api(method, path, body=None, optional=False):
    command = ['gh', 'api', '--method', method, path]
    if body is not None:
        command += ['--input', '-']
    result = subprocess.run(command, input=json.dumps(body) if body is not None else None,
                            text=True, capture_output=True)
    if result.returncode:
        if optional and 'HTTP 404' in result.stderr:
            return None
        raise RuntimeError(f'{method} {path}: {result.stderr.strip()}')
    return json.loads(result.stdout) if result.stdout.strip() else None


def collection(path):
    rows = []
    for page in range(1, 1001):
        chunk = api('GET', f'{path}{"&" if "?" in path else "?"}per_page=100&page={page}')
        if not isinstance(chunk, list):
            raise RuntimeError(f'Expected a list: {path}')
        rows.extend(chunk)
        if len(chunk) < 100:
            return rows
    raise RuntimeError('Pagination limit reached')


def desired_rules(checks):
    return {
        'name': RULE_NAME, 'target': 'branch', 'enforcement': 'active',
        'conditions': {'ref_name': {'include': ['~DEFAULT_BRANCH'], 'exclude': []}},
        'bypass_actors': [],
        'rules': [
            {'type': 'deletion'}, {'type': 'non_fast_forward'},
            {'type': 'required_linear_history'},
            {'type': 'pull_request', 'parameters': {
                'required_approving_review_count': 0,
                'dismiss_stale_reviews_on_push': True,
                'require_code_owner_review': False,
                'require_last_push_approval': False,
                'require_extra_approval_for_unattributed_changes': False,
                'required_reviewers': [],
                'required_review_thread_resolution': True,
                'allowed_merge_methods': ['squash'],
            }},
            {'type': 'required_status_checks', 'parameters': {
                'strict_required_status_checks_policy': True,
                'required_status_checks': checks,
            }},
        ],
    }


def prepare(repo, default_checks):
    metadata = api('GET', f'repos/{repo}')
    if not metadata.get('permissions', {}).get('admin'):
        raise RuntimeError(f'Administrator access is required for {repo}')
    if not metadata.get('allow_squash_merge'):
        raise RuntimeError(f'Enable squash merges in {repo} before continuing')
    branch = quote(metadata['default_branch'], safe='')
    classic = api('GET', f'repos/{repo}/branches/{branch}/protection', optional=True)
    if classic and classic.get('enforce_admins', {}).get('enabled'):
        review = classic.get('required_pull_request_reviews') or {}
        if (review.get('required_approving_review_count', 0) or
                review.get('require_code_owner_reviews') or review.get('require_last_push_approval')):
            raise RuntimeError(f'{repo}: classic branch protection still requires another reviewer. '
                               'Adjust that review requirement before using owner-account merges.')
    effective = api('GET', f'repos/{repo}/rules/branches/{branch}')
    effective_ids = {r['ruleset_id'] for r in effective}
    rulesets = collection(f'repos/{repo}/rulesets')
    snapshots = [api('GET', f'repos/{repo}/rulesets/{r["id"]}') for r in rulesets]
    matching = [r for r in snapshots if r['name'] == RULE_NAME and r['target'] == 'branch'
                and r.get('source_type', 'Repository') == 'Repository']
    if len(matching) > 1:
        raise RuntimeError(f'{repo}: duplicate setup rulesets; resolve these first')
    checks = {name: {'context': name} for name in default_checks}
    for ruleset in snapshots:
        if ruleset['id'] not in effective_ids or ruleset['enforcement'] != 'active':
            continue
        if matching and ruleset['id'] == matching[0]['id']:
            continue
        admin_bypass = any(b.get('actor_type') == 'RepositoryRole' and b.get('actor_id') == 5
                           and b.get('bypass_mode') in ('always', 'pull_request')
                           for b in ruleset.get('bypass_actors', []))
        for rule in ruleset['rules']:
            params = rule.get('parameters', {})
            if rule['type'] == 'required_status_checks':
                for check in params['required_status_checks']:
                    checks[check['context']] = check
            if rule['type'] == 'pull_request' and not admin_bypass:
                if (params.get('required_approving_review_count', 0) or
                        params.get('require_code_owner_review') or
                        params.get('require_last_push_approval') or params.get('required_reviewers') or
                        params.get('require_extra_approval_for_unattributed_changes')):
                    raise RuntimeError(f'{repo}: ruleset "{ruleset["name"]}" still requires another '
                                       'identity. Review that rule before applying this setup.')
    if matching:
        previous_checks = next((r['parameters']['required_status_checks'] for r in matching[0]['rules']
                                if r['type'] == 'required_status_checks'), [])
        for check in previous_checks:
            checks[check['context']] = check
    endpoint = f'repos/{repo}/rulesets'
    if matching:
        endpoint += f'/{matching[0]["id"]}'
    return {'repo': repo, 'method': 'PUT' if matching else 'POST', 'endpoint': endpoint,
            'desired': desired_rules(list(checks.values())),
            'before': {'rulesets': snapshots, 'classic_branch_protection': classic}}


def verify(actual, desired):
    for key in ('name', 'target', 'enforcement', 'conditions', 'bypass_actors'):
        if actual.get(key) != desired[key]:
            raise RuntimeError(f'Rule verification failed: {key}')
    actual_rules = {r['type']: r.get('parameters', {}) for r in actual['rules']}
    for rule in desired['rules']:
        if rule['type'] not in actual_rules:
            raise RuntimeError(f'Missing rule: {rule["type"]}')
        for key, value in rule.get('parameters', {}).items():
            if key == 'required_status_checks':
                current = actual_rules[rule['type']].get(key, [])
                for expected in value:
                    if not any(all(check.get(k) == v for k, v in expected.items())
                               for check in current):
                        raise RuntimeError(f'Missing or changed required check: {expected["context"]}')
                continue
            if actual_rules[rule['type']].get(key) != value:
                raise RuntimeError(f'Rule verification failed: {rule["type"]}.{key}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if api('GET', 'user')['login'].lower() != OWNER.lower():
        raise RuntimeError(f'Use gh auth login as @{OWNER} on your own computer')
    # Finish every read/preflight before the first write.
    plans = [prepare(repo, checks) for repo, checks in REPOSITORIES.items()]
    for plan in plans:
        checks = plan['desired']['rules'][-1]['parameters']['required_status_checks']
        print(f'{plan["repo"]}: require PR + squash merge + resolved conversations; '
              f'no approving review; no bypass; checks: {", ".join(c["context"] for c in checks)}')
    if not args.apply:
        print('Preview only. Run again with --apply to activate these settings.')
        return 0
    backups = Path(__file__).resolve().parents[1] / '.security-backups'
    backups.mkdir(mode=0o700, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    backup = backups / f'pr-workflow-{stamp}.json'
    backup.write_text(json.dumps(plans, indent=2), encoding='utf-8')
    backup.chmod(0o600)
    print(f'Previous rules saved privately to {backup}')
    for plan in plans:
        response = api(plan['method'], plan['endpoint'], plan['desired'])
        current = api('GET', f'repos/{plan["repo"]}/rulesets/{response["id"]}')
        verify(current, plan['desired'])
        print(f'Activated and verified: {plan["repo"]}')
    print('AI sessions using your account may merge passing PRs. Direct main pushes are blocked. '
          'Admins can still edit settings; AI sessions must preserve these protections.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        raise SystemExit(str(exc))
