#!/usr/bin/env bash

set -Eeuo pipefail

repository="${DOTFILES_REPO:-$HOME/.dotfiles}"

notify() {
    notify-send "System update" "$1" "${@:2}" >/dev/null 2>&1 || true
}

if [[ ! -f "$repository/flake.nix" || ! -f "$repository/flake.lock" ]]; then
    notify "Cannot check updates: dotfiles repository not found." -u critical
    exit 1
fi

temporary_directory=$(mktemp -d -t flake-update-check.XXXXXXXX)
cleanup() {
    rm -rf -- "$temporary_directory"
}
trap cleanup EXIT

git clone --quiet --no-local "$repository" "$temporary_directory/repository"

notify "Checking flake inputs..." -i software-update-available

if ! update_output=$(nix flake update --flake "$temporary_directory/repository" 2>&1); then
    printf '%s\n' "$update_output" >&2
    notify "The flake update check failed. See the user journal for details." -u critical
    exit 1
fi

if cmp -s "$repository/flake.lock" "$temporary_directory/repository/flake.lock"; then
    notify "No flake input updates found." -i software-update-available
else
    notify "Flake input updates are available. Run flake-update to review them." \
        -u critical -i software-update-urgent
fi
