#!/usr/bin/env bash
# Run after reviewing this policy and publishing the first successful CI run.
set -Eeuo pipefail
repo=brenoslivio/.dotfiles
gh auth status
policy=$(mktemp)
trap 'rm -f "$policy"' EXIT
cat > "$policy" <<'JSON'
{
  "required_status_checks": {"strict": true, "contexts": ["ahimsa-ready", "ahimsa-vps-ready"]},
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0
  },
  "restrictions": null,
  "required_conversation_resolution": true,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
gh api --method PATCH "repos/$repo" -F delete_branch_on_merge=true >/dev/null
gh api --method PUT "repos/$repo/actions/permissions/workflow" \
  -f default_workflow_permissions=read -F can_approve_pull_request_reviews=true >/dev/null
gh api --method PUT "repos/$repo/branches/main/protection" --input "$policy" >/dev/null
echo 'Configured proposal permissions, merged-branch cleanup, and required CI.'
