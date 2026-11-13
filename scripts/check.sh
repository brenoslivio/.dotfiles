#!/usr/bin/env bash
set -Eeuo pipefail
repo=${DOTFILES_REPO:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}
mode=${1:-full}
case "$mode" in full|quick|ahimsa|ahimsa-vps|vps-vm) ;; *) echo 'Usage: dotfiles-check [full|quick|ahimsa|ahimsa-vps|vps-vm]' >&2; exit 2 ;; esac
# CI passes an immutable Git URL; local checks intentionally include working changes.
flake=${DOTFILES_FLAKE:-path:$repo}
flags=(--no-update-lock-file --no-write-lock-file)
if [[ $mode == full || $mode == quick ]]; then
  nix flake check "${flags[@]}" --no-build "$flake"
  nix build "${flags[@]}" --no-link \
    "$flake#checks.x86_64-linux.generated-config" \
    "$flake#checks.x86_64-linux.updater"
fi
if [[ $mode == quick ]]; then
  echo 'Quick checks passed; full system, Home Manager, and VM builds were not run.'
  exit 0
fi
if [[ $mode == full || $mode == ahimsa ]]; then
  nix build "${flags[@]}" --no-link \
    "$flake#nixosConfigurations.ahimsa.config.system.build.toplevel" \
    "$flake#homeConfigurations.brenoslivio.activationPackage"
  nix build "${flags[@]}" --no-link -L "$flake#checks.x86_64-linux.ahimsa-vm"
fi
if [[ $mode == full || $mode == ahimsa-vps ]]; then
  nix build "${flags[@]}" --no-link \
    "$flake#nixosConfigurations.ahimsa-vps.config.system.build.toplevel" \
    "$flake#checks.x86_64-linux.vps-config"
fi
if [[ $mode == vps-vm ]]; then
  nix build "${flags[@]}" --no-link -L "$flake#checks.x86_64-linux.vps-vm"
fi
