#!/usr/bin/env bash
# One-shot, safe to re-run: applies the repository and organisation settings described in MAINTAINERS.md.
# Run it once from a checkout of this branch, logged in as the owner:  gh auth login   then   bash .github/apply-settings.sh
set -euo pipefail
ORG=LightningEg; REPO=$ORG/Lightning; R=repos/$REPO
cd "$(dirname "$0")"

echo "== Teams (created if missing; add people yourself afterwards)"
for t in "ai-reviewers:push" "internal:triage"; do
  slug=${t%%:*}; perm=${t##*:}
  gh api "orgs/$ORG/teams/$slug" >/dev/null 2>&1 || gh api -X POST "orgs/$ORG/teams" -f name="$slug" -f privacy=closed >/dev/null
  gh api -X PUT "orgs/$ORG/teams/$slug/repos/$REPO" -f permission="$perm"
done

echo "== Rulesets (update by name, else create)"
apply() { # file target
  id=$(gh api $R/rulesets --jq ".[]|select(.target==\"$2\")|.id" | head -1 || true)
  if [ -n "$id" ]; then gh api -X PUT $R/rulesets/$id --input "$1" --jq '"updated "+.name'
  else gh api -X POST $R/rulesets --input "$1" --jq '"created "+.name'; fi
}
apply rulesets/main.json branch
apply rulesets/tags.json tag

echo "== Merge settings"
gh api -X PATCH $R -F allow_squash_merge=true -F allow_merge_commit=false -F allow_rebase_merge=false \
  -F allow_auto_merge=false -F delete_branch_on_merge=true --silent

echo "== Security features"
gh api -X PATCH $R --input - --silent <<'JSON'
{"security_and_analysis":{"secret_scanning":{"status":"enabled"},"secret_scanning_push_protection":{"status":"enabled"},"dependabot_security_updates":{"status":"enabled"}}}
JSON
gh api -X PUT $R/vulnerability-alerts --silent
gh api -X PUT $R/private-vulnerability-reporting --silent

echo "== Actions: fork PRs need approval, read-only token, no PR approval by Actions"
gh api -X PUT $R/actions/permissions/workflow -f default_workflow_permissions=read -F can_approve_pull_request_reviews=false --silent
gh api -X PUT $R/actions/permissions/fork-pr-contributor-approval -f approval_policy=all_external_contributors --silent

echo "== Organisation: no default access, 2FA required (2FA fails if a member has none; read the error)"
gh api -X PATCH orgs/$ORG -f default_repository_permission=none -F two_factor_requirement_enabled=true --silent || echo "org patch failed: set it under Org Settings > Authentication security"

echo
echo "Done. Left for you (cannot be scripted): create the bot GitHub accounts for Claude, Codex, Luna and add them to team ai-reviewers;"
echo "create environment 'release' (Settings > Environments) with you as required reviewer and move the signing secrets into it."
