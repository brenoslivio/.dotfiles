#!/usr/bin/env bash

set -euo pipefail

eval "$(ssh-agent -s)"
ssh-add "${HOME}/.ssh/id_ed25519"
sudo rfkill unblock bluetooth
