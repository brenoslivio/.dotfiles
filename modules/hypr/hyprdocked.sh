#!/usr/bin/env bash

# Use the external display exclusively when it is connected. Fall back to the
# notebook panel as soon as the external display is disconnected.

INTERNAL="eDP-1"
EXTERNAL="HDMI-A-1"
EXTERNAL_MODE="2560x1080@60"

enable_internal() {
    hyprctl keyword monitor "$INTERNAL, preferred, 0x0, 1" >/dev/null || return 1
    # Hyprland 0.55 can acknowledge the rule without modesetting eDP when the
    # disconnected external display was the last active output. A full reload
    # forces Aquamarine to apply the configured internal-panel rule.
    hyprctl reload >/dev/null
}

enable_external_only() {
    # Bring up HDMI before disabling the panel so a failed mode-set can never
    # leave the session without an active output.
    hyprctl keyword monitor "$EXTERNAL, $EXTERNAL_MODE, 1920x0, 1" >/dev/null || return 1
    hyprctl keyword monitor "$INTERNAL, disable" >/dev/null || return 1
    hyprctl keyword monitor "$EXTERNAL, $EXTERNAL_MODE, 0x0, 1" >/dev/null
}

connection_state() {
    local status

    # `hyprctl monitors all` can temporarily retain a disconnected output.
    # The DRM connector state is authoritative during hotplug transitions.
    for status in /sys/class/drm/card*-"$EXTERNAL"/status; do
        if [ -r "$status" ] && grep -qx connected "$status"; then
            echo connected
            return
        fi
    done

    echo disconnected
}

apply_layout() {
    case "$1" in
        connected)
            echo "$EXTERNAL connected; enabling external-only layout"
            enable_external_only
            ;;
        disconnected)
            echo "$EXTERNAL disconnected; enabling $INTERNAL"
            enable_internal
            ;;
    esac
}

layout_is_applied() {
    local active_monitors
    active_monitors=$(hyprctl monitors)

    case "$1" in
        connected)
            grep -Fq "Monitor $EXTERNAL (" <<<"$active_monitors" &&
                ! grep -Fq "Monitor $INTERNAL (" <<<"$active_monitors"
            ;;
        disconnected)
            grep -Fq "Monitor $INTERNAL (" <<<"$active_monitors"
            ;;
        *)
            return 1
            ;;
    esac
}

active_workspace() {
    local label type workspace rest

    IFS=' ' read -r label type workspace rest < <(hyprctl activeworkspace)
    if [ "$label" = workspace ] && [ "$type" = ID ] && [[ "$workspace" =~ ^[1-9][0-9]*$ ]]; then
        echo "$workspace"
    fi
}

restore_workspace() {
    local state="$1"
    local workspace="$2"
    local target

    [ -n "$workspace" ] || return 0

    if [ "$state" = connected ]; then
        target="$EXTERNAL"
    else
        target="$INTERNAL"
    fi

    hyprctl dispatch moveworkspacetomonitor "$workspace $target" >/dev/null || return 1
    hyprctl dispatch workspace "$workspace" >/dev/null
    echo "restored workspace $workspace on $target"
}

# Poll the kernel connector state as well as reacting to startup. This avoids a
# missed or transient Hyprland hotplug event leaving every output disabled.
last_state=""
last_workspace=""
while true; do
    current_state=$(connection_state)

    # Remember the focused workspace only while the current layout is stable.
    # During a hotplug transition Hyprland may briefly report a fallback
    # workspace, which should not replace the user's actual workspace.
    if [ "$current_state" = "$last_state" ] && layout_is_applied "$current_state"; then
        current_workspace=$(active_workspace)
        if [ -n "$current_workspace" ]; then
            last_workspace="$current_workspace"
        fi
    fi

    if [ "$current_state" != "$last_state" ] || ! layout_is_applied "$current_state"; then
        if apply_layout "$current_state" && layout_is_applied "$current_state"; then
            restore_workspace "$current_state" "$last_workspace"
            last_state="$current_state"
        else
            # Hyprland can acknowledge a monitor command before a DRM hotplug
            # transition is complete. Keep retrying until the output is active.
            last_state=""
        fi
    fi
    sleep 1
done
