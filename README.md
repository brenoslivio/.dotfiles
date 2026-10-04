# NixOS dotfiles

Reproducible NixOS and Home Manager configuration for my machines. The flake
supports existing-host reinstalls and can generate a new host from a freshly
mounted device's hardware.

## Hosts

- `ahimsa`: primary AMD machine.
- `ahimsa-ufz`: Intel UFZ machine.

Each host lives under `hosts/<hostname>` and contains `default.nix`,
`hardware.nix`, and non-secret user metadata. Home Manager is integrated with
NixOS for atomic system switches, while the same home module is also exposed as
a standalone output for fast user-only changes.

## Daily commands

These are Fish functions and are invoked like ordinary aliases:

```console
up                # activate NixOS and Home Manager together
home              # activate only Home Manager
flake-update      # update inputs and check; do not activate
rollback          # return to the previous integrated generation
dotfiles-check    # evaluate and build-check without activating
```

The functions use `$DOTFILES_REPO`, which defaults to `~/.dotfiles`.

## Existing installation

To rebuild a running host from the repository:

```console
sudo nixos-rebuild switch --flake path:$PWD#ahimsa
```

To reinstall a mounted known host from the NixOS installer:

```console
sudo ./install-nixos.sh --host ahimsa --root /mnt
```

The installer does not partition or format disks. Mount the root filesystem at
`/mnt` and the EFI system partition at `/mnt/boot` first.

## Fresh device

From the NixOS installer, partition, format, and mount the new device first.
Then preserve the clone directly on the target filesystem:

```console
sudo mkdir -p /mnt/home/brenoslivio
sudo git clone \
  https://github.com/brenoslivio/.dotfiles.git \
  /mnt/home/brenoslivio/.dotfiles

cd /mnt/home/brenoslivio/.dotfiles

sudo ./install-nixos.sh \
  --new-device new-laptop \
  --user brenoslivio \
  --user-description "Breno Livio" \
  --email brenoslivio@pm.me \
  --root /mnt
```

Fresh-device mode generates `hosts/new-laptop/hardware.nix` from the mounted
system. It therefore uses the new device's real filesystem UUIDs, encryption,
swap, CPU microcode, and kernel modules instead of copying another machine's
hardware configuration.

Preview the operation without writing or installing:

```console
sudo ./install-nixos.sh \
  --new-device new-laptop \
  --root /mnt \
  --dry-run
```

Run `./install-nixos.sh --help` for every option. The script never stages or
commits generated files.

## Adding a host manually

Create:

```text
hosts/<hostname>/default.nix
hosts/<hostname>/hardware.nix
hosts/<hostname>/metadata.nix
```

Host directories containing those files are discovered automatically. Use
`templates/host` as the starting point and then check the host:

```console
nix build --no-link \
  "path:$PWD#nixosConfigurations.<hostname>.config.system.build.toplevel"
```

## Personal setup after installation

Passwords, private SSH keys, and cloud credentials are deliberately absent.
After installation:

1. Set the normal user's password.
2. Create or restore `~/.ssh/id_ed25519` and its public key.
3. Create the allowed-signers file used by Git verification:

   ```console
   mkdir -p ~/.ssh
   awk -v principal="$(git config user.email)" \
     '{ print principal, $1, $2 }' \
     ~/.ssh/id_ed25519.pub > ~/.ssh/allowed_signers
   chmod 600 ~/.ssh/allowed_signers
   ```

4. Sign in to Dropbox, Proton VPN, and other personal applications as needed.

Waybar's tasks and research integrations handle missing Dropbox files without
preventing the bar from starting. Their paths can be overridden with
`TASKS_FILE` and `RESEARCH_FILE`.

## Assets

Required desktop images are tracked under `assets` and installed to
`~/.local/share/dotfiles/assets`. Active configuration does not depend on files
under `~/Pictures`.

JPEG metadata has been removed. Before publishing a fork, review
`assets/README.md`, confirm redistribution rights for the wallpapers, and
decide whether the personal lock-screen photograph should remain public.

## Updating and recovery

`flake-update` changes the lock file and runs checks but does not activate the
result. Review the diff and then run `up`.

If an integrated activation causes a problem:

```console
rollback
```

Home-only generations can be listed with:

```console
home-manager generations
```

## Repository layout

```text
assets/       managed icons, wallpapers, and photographs
hosts/        machine-specific configuration and hardware
modules/      shared Home Manager modules and desktop configuration
system/       shared NixOS configuration
templates/    templates used by the fresh-device installer
```
