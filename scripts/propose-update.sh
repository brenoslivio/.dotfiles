#!/usr/bin/env bash
set -Eeuo pipefail
repo=${DOTFILES_REPO:-$HOME/.dotfiles}
cd -- "$repo"
[[ $(git branch --show-current) != main ]] || { echo 'Create a proposal branch first.' >&2; exit 1; }
[[ -z $(git status --porcelain) ]] || { echo 'Start from a clean checkout.' >&2; exit 1; }
nix flake update --flake "$repo"
DOTFILES_REPO=$repo bash "$repo/scripts/check.sh" quick
echo 'Review flake.lock, commit, and open a PR. Nothing was activated.'
