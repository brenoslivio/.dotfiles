#!/usr/bin/env nix-shell
#! nix-shell -p bash libnotify
#! nix-shell -i bash
 
# Enabling service
# systemctl --user daemon-reexec
# systemctl --user enable --now flakeUpdate.timer

set -eufo pipefail

cd "$HOME/.dotfiles"

echo "[INFO] Checking updates for Flake: $(date)"
notify-send "Sytem update" "Checking for Flake updates..." -i software-update-available

cp flake.lock{,.bak}
flake_update_output=`nix flake update 2>&1`
mv flake.lock{.bak,}

if ( echo "$flake_update_output" | grep -q 'Updated' ); then 
    notify-send "Sytem update" "$( echo "$flake_update_output" | grep -vE '^warning' )" -u critical -i software-update-urgent
else
    notify-send "Sytem update" "No updates found." -i software-update-available
fi

echo "[INFO] Checking done: $(date)"