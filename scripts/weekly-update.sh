#!/usr/bin/env bash
set -Eeuo pipefail
branch=automation/flake-update
# Keep an outstanding proposal intact, including failures and manual repairs.
existing=$(gh pr list --repo "$GITHUB_REPOSITORY" --state open --base main --head "$branch" --json number --jq '.[0].number // empty')
if [[ -n $existing ]]; then
  echo "Keeping existing proposal #$existing and its CI unchanged." >> "$GITHUB_STEP_SUMMARY"
  exit 0
fi
# Do not overwrite an orphan branch that may contain unfinished work.
if git ls-remote --exit-code --heads origin "$branch" >/dev/null; then
  echo "Branch $branch exists without an open PR; review it before retrying." >&2
  exit 1
fi
cp flake.lock /tmp/previous-flake.lock
nix flake update
if git diff --quiet -- flake.lock; then
  echo 'No input changes.' >> "$GITHUB_STEP_SUMMARY"
  exit 0
fi
python3 - <<'PY'
import json
from pathlib import Path
old = json.loads(Path('/tmp/previous-flake.lock').read_text())['nodes']
new = json.loads(Path('flake.lock').read_text())['nodes']
lines = ['Update pinned flake inputs. No system activation.', '', '| Input | Before | After |', '|---|---|---|']
for name in sorted(old.keys() | new.keys()):
    before = old.get(name, {}).get('locked', {})
    after = new.get(name, {}).get('locked', {})
    if before != after:
        a = before.get('rev', before.get('narHash', 'absent'))
        b = after.get('rev', after.get('narHash', 'absent'))
        lines.append(f'| `{name}` | `{a}` | `{b}` |')
Path('/tmp/proposal-body.md').write_text('\n'.join(lines) + '\n')
PY
git switch -c "$branch"
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add flake.lock
git -c commit.gpgsign=false commit -m 'Update pinned flake inputs'
git push origin "$branch"
gh pr create --repo "$GITHUB_REPOSITORY" --base main --head "$branch" \
  --title 'Update pinned flake inputs' --body-file /tmp/proposal-body.md
# The pull_request event starts CI; approve the bot-triggered run in GitHub if requested.
