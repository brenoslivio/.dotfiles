# NixOS dotfiles

NixOS unstable and Home Manager for `ahimsa` (AMD). Inputs are pinned in
`flake.lock`; state versions remain `24.11`. Brave temporarily uses `release-26.05`.

## Updates

Friday proposals → PR checks → review/merge → final `main` checks → `up`.

```console
up                  # verified update: now, next boot, or later
home                # verified standalone Home Manager update
dotfiles-check      # full local suite; add quick for syntax/evaluation only
dotfiles-status     # pending, active, and next-boot systems
dotfiles-mark-good  # protect the active system after hardware testing
rollback            # previous system generation, offline
rollback-good       # protected known-good system, offline
flake-update        # update inputs on a clean proposal branch
```

`up` requires clean `main`, GitHub authentication, and successful CI for the
exact revision. It never updates dependencies or reboots. Notifications run
daily and Friday evening. See [setup and recovery](docs/updates.md).

## Installation

Mount root at `/mnt` and EFI at `/mnt/boot`; the installer never formats disks.

```console
sudo ./install-nixos.sh --host ahimsa --root /mnt
sudo ./install-nixos.sh --new-device new-laptop --user brenoslivio \
  --user-description "Breno Livio" --email brenoslivio@pm.me --root /mnt
```

Use `--dry-run` to preview or `--help` for options. Fresh devices get generated
hardware configuration. Set passwords and restore private credentials afterward.
New hosts require their own CI/update policy before using the guarded updater.

## Layout

```text
hosts/       hardware and user metadata
system/      shared NixOS configuration
modules/     Home Manager and desktop configuration
scripts/     checking and update commands
tests/       configuration, updater, and VM checks
assets/      managed desktop assets
templates/   fresh-device templates
```

`DOTFILES_REPO` defaults to `~/.dotfiles`. Rootless Podman preserves user IDs
with `keep-id`. Asset notes: [assets/README.md](assets/README.md).
