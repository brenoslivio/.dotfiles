#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_NAME=${0##*/}
REPOSITORY=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

mode=""
host_name=""
target_root="/mnt"
target_user="brenoslivio"
user_description="Breno Livio"
user_email="brenoslivio@pm.me"
regenerate_hardware=false
dry_run=false
assume_yes=false
temporary_directory=""

usage() {
    cat <<EOF
Install this NixOS flake on an existing host or a completely new device.

Usage:
  $SCRIPT_NAME --host NAME [options]
  $SCRIPT_NAME --new-device NAME [options]

Modes:
  --host NAME            Install a committed host configuration.
  --new-device NAME      Generate a host from this device's hardware.

Options:
  --user NAME            Primary user for a new device (default: brenoslivio).
  --user-description S   Git/display name for the primary user.
  --email ADDRESS        Git email for the primary user.
  --root PATH            Mounted NixOS target (default: /mnt).
  --regenerate-hardware  Replace an existing host's hardware configuration.
  --dry-run              Validate and print actions without writing or installing.
  --yes                  Confirm hardware replacement non-interactively.
  -h, --help             Show this help.

The script never partitions or formats disks. Mount the target root and boot
filesystems before running it.
EOF
}

fail() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

log() {
    printf '==> %s\n' "$*"
}

cleanup() {
    local status=$?
    if [[ -n "$temporary_directory" && -d "$temporary_directory" ]]; then
        if (( status == 0 )); then
            rm -rf -- "$temporary_directory"
        else
            printf 'Generated files were preserved at %s\n' "$temporary_directory" >&2
        fi
    fi
}
trap cleanup EXIT

while (( $# > 0 )); do
    case "$1" in
        --host)
            [[ $# -ge 2 ]] || fail "--host requires a name"
            [[ -z "$mode" ]] || fail "select only one installation mode"
            mode="existing"
            host_name=$2
            shift 2
            ;;
        --new-device)
            [[ $# -ge 2 ]] || fail "--new-device requires a name"
            [[ -z "$mode" ]] || fail "select only one installation mode"
            mode="new"
            host_name=$2
            shift 2
            ;;
        --user)
            [[ $# -ge 2 ]] || fail "--user requires a name"
            target_user=$2
            shift 2
            ;;
        --user-description)
            [[ $# -ge 2 ]] || fail "--user-description requires a value"
            user_description=$2
            shift 2
            ;;
        --email)
            [[ $# -ge 2 ]] || fail "--email requires an address"
            user_email=$2
            shift 2
            ;;
        --root)
            [[ $# -ge 2 ]] || fail "--root requires a path"
            target_root=$2
            shift 2
            ;;
        --regenerate-hardware)
            regenerate_hardware=true
            shift
            ;;
        --dry-run)
            dry_run=true
            shift
            ;;
        --yes)
            assume_yes=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "unknown argument: $1"
            ;;
    esac
done

[[ -n "$mode" ]] || { usage >&2; fail "choose --host or --new-device"; }
[[ "$host_name" =~ ^[a-z0-9][a-z0-9-]*$ ]] || fail "invalid hostname: $host_name"
[[ "$target_user" =~ ^[a-z_][a-z0-9_-]*$ ]] || fail "invalid username: $target_user"
[[ "$user_email" != *$'\n'* && "$user_email" != *'"'* ]] || fail "email contains unsupported characters"
[[ "$user_description" != *$'\n'* && "$user_description" != *'"'* ]] || fail "user description contains unsupported characters"
[[ "$target_root" == /* ]] || fail "--root must be an absolute path"
[[ "$target_root" != "/" ]] || fail "refusing to use / as the installation target"
[[ -d "$target_root" ]] || fail "target root does not exist: $target_root"

for command_name in findmnt nix nixos-generate-config nixos-install; do
    command -v "$command_name" >/dev/null 2>&1 || fail "required command not found: $command_name"
done

if [[ $EUID -ne 0 && "$dry_run" == false ]]; then
    fail "run the installer as root (dry-run may be run without root)"
fi

findmnt --mountpoint "$target_root" >/dev/null 2>&1 \
    || fail "target root is not a mountpoint: $target_root"

if [[ -d "$target_root/boot" ]] && ! findmnt --mountpoint "$target_root/boot" >/dev/null 2>&1; then
    fail "$target_root/boot exists but is not a separate mounted boot filesystem"
fi

readonly hosts_directory="$REPOSITORY/hosts"
readonly host_directory="$hosts_directory/$host_name"
readonly template_directory="$REPOSITORY/templates/host"
repository_owner=$(stat -c '%u:%g' "$REPOSITORY")

escape_sed_replacement() {
    printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'
}

render_template() {
    local source=$1
    local destination=$2
    local rendered
    rendered=$(sed \
        -e "s|@HOSTNAME@|$(escape_sed_replacement "$host_name")|g" \
        -e "s|@USERNAME@|$(escape_sed_replacement "$target_user")|g" \
        -e "s|@USER_DESCRIPTION@|$(escape_sed_replacement "$user_description")|g" \
        -e "s|@USER_EMAIL@|$(escape_sed_replacement "$user_email")|g" \
        "$source")
    printf '%s\n' "$rendered" > "$destination"
}

confirm_hardware_replacement() {
    if [[ "$assume_yes" == true ]]; then
        return 0
    fi
    [[ -t 0 ]] || fail "hardware replacement requires an interactive terminal or --yes"
    printf 'Replace %s/hardware.nix with freshly detected hardware? [y/N] ' "$host_directory"
    read -r answer
    [[ "$answer" =~ ^[Yy]$ ]] || fail "hardware replacement cancelled"
}

temporary_directory=$(mktemp -d -t nixos-dotfiles-install.XXXXXXXX)

if [[ "$mode" == "new" ]]; then
    [[ ! -e "$host_directory" ]] || fail "host already exists: $host_name"
    [[ -f "$template_directory/default.nix" ]] || fail "missing host template"
    [[ -f "$template_directory/metadata.nix" ]] || fail "missing metadata template"

    log "Generating hardware configuration for new device $host_name"
    nixos-generate-config --root "$target_root" --show-hardware-config \
        > "$temporary_directory/hardware.nix"
    render_template "$template_directory/default.nix" "$temporary_directory/default.nix"
    render_template "$template_directory/metadata.nix" "$temporary_directory/metadata.nix"

    if [[ "$dry_run" == false ]]; then
        install -d -m 0755 "$host_directory"
        install -m 0644 "$temporary_directory/default.nix" "$host_directory/default.nix"
        install -m 0644 "$temporary_directory/hardware.nix" "$host_directory/hardware.nix"
        install -m 0644 "$temporary_directory/metadata.nix" "$host_directory/metadata.nix"
        chown -R "$repository_owner" "$host_directory"
    fi
else
    [[ -f "$host_directory/default.nix" ]] || fail "unknown host: $host_name"
    [[ -f "$host_directory/hardware.nix" ]] || fail "host has no hardware.nix: $host_name"
    [[ -f "$host_directory/metadata.nix" ]] || fail "host has no metadata.nix: $host_name"

    target_user=$(sed -n 's/^[[:space:]]*primaryUser = "\([^"]*\)";.*/\1/p' "$host_directory/metadata.nix")
    [[ -n "$target_user" ]] || fail "could not determine primary user from host metadata"

    if [[ "$regenerate_hardware" == true ]]; then
        confirm_hardware_replacement
        log "Generating replacement hardware configuration for $host_name"
        nixos-generate-config --root "$target_root" --show-hardware-config \
            > "$temporary_directory/hardware.nix"
        if [[ "$dry_run" == false ]]; then
            install -m 0644 "$temporary_directory/hardware.nix" "$host_directory/hardware.nix"
            chown "$repository_owner" "$host_directory/hardware.nix"
        fi
    fi
fi

flake_reference="path:$REPOSITORY#nixosConfigurations.$host_name.config.system.build.toplevel"
install_reference="path:$REPOSITORY#$host_name"
target_repository="$target_root/home/$target_user/.dotfiles"

if [[ "$dry_run" == true ]]; then
    log "Dry run complete; no files were written"
    printf 'Would build:   nix build --no-link %q\n' "$flake_reference"
    printf 'Would install: nixos-install --root %q --flake %q\n' "$target_root" "$install_reference"
    printf 'Would preserve repository at: %s\n' "$target_repository"
    exit 0
fi

log "Building $host_name before installation"
nix build --no-link "$flake_reference"

log "Installing $host_name into $target_root"
nixos-install --root "$target_root" --flake "$install_reference"

source_repository=$(realpath -m "$REPOSITORY")
destination_repository=$(realpath -m "$target_repository")

if [[ "$source_repository" != "$destination_repository" ]]; then
    [[ ! -e "$target_repository" ]] || fail "target repository already exists: $target_repository"
    log "Preserving the configured repository at $target_repository"
    install -d -m 0755 "$(dirname "$target_repository")"
    cp -a -- "$REPOSITORY" "$target_repository"
fi

if command -v nixos-enter >/dev/null 2>&1; then
    target_uid=$(nixos-enter --root "$target_root" -c "id -u $target_user")
    target_gid=$(nixos-enter --root "$target_root" -c "id -g $target_user")
    chown -R "$target_uid:$target_gid" "$target_repository"
fi

cat <<EOF

Installation completed for $host_name.

Next steps:
  1. Set the $target_user password if it is not already configured.
  2. Reboot into the installed system.
  3. Review and commit hosts/$host_name if this was a new device.
  4. Create ~/.ssh/allowed_signers after configuring the user's SSH key.

The installer did not partition disks, create Git commits, or push anything.
EOF
