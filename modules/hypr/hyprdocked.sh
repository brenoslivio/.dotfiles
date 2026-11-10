#!/usr/bin/env bash

# Use the external display exclusively when it is connected. Fall back to the
# notebook panel as soon as the external display is disconnected.

INTERNAL="eDP-1"
EXTERNAL="HDMI-A-1"
EXTERNAL_MODE="2560x1080@60"

enable_internal() {
    hyprctl eval "hl.monitor({output = '$INTERNAL', mode = 'preferred', position = '0x0', scale = 1, disabled = false})" >/dev/null || return 1
}

enable_external_only() {
    # Bring up HDMI before disabling the panel so a failed mode-set can never
    # leave the session without an active output.
    hyprctl eval "hl.monitor({output = '$EXTERNAL', mode = '$EXTERNAL_MODE', position = '1920x0', scale = 1, disabled = false})" >/dev/null || return 1
    hyprctl -j monitors | jq -e --arg output "$EXTERNAL" \
        'any(.[]; .name == $output and .disabled == false and .width > 0 and .height > 0)' >/dev/null || return 1
    session_is_unlocked || return 1
    hyprctl eval "hl.monitor({output = '$INTERNAL', disabled = true})" >/dev/null || return 1
    hyprctl eval "hl.monitor({output = '$EXTERNAL', mode = '$EXTERNAL_MODE', position = '0x0', scale = 1, disabled = false})" >/dev/null
}

session_is_unlocked() {
    # Fail closed if IPC is stale or unavailable. Never change the display
    # layout underneath the lock screen or during compositor recovery.
    hyprctl -j locked 2>/dev/null | jq -e '.locked == false' >/dev/null 2>&1
}

session_is_locked() {
    hyprctl -j locked 2>/dev/null | jq -e '.locked == true' >/dev/null 2>&1
}

refresh_instance() {
    local instance

    # A watchdog restart changes the signature but normally reuses the same
    # Wayland display. Do not attach to a different login session.
    instance=$(hyprctl -j instances | jq -er --arg display "$WAYLAND_DISPLAY" \
        '[.[] | select(.wl_socket == $display)] | if length == 1 then .[0].instance else empty end') || return 1
    export HYPRLAND_INSTANCE_SIGNATURE="$instance"
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
    local workspace

    # The human-readable prefix changed in 0.57; JSON keeps this independent
    # of output formatting. Only remember ordinary numbered workspaces.
    workspace=$(hyprctl -j activeworkspace | jq -er '.id') || return 1
    if [[ "$workspace" =~ ^[1-9][0-9]*$ ]]; then
        printf '%s\n' "$workspace"
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

    hyprctl dispatch "hl.dsp.workspace.move({workspace = $workspace, monitor = '$target'})" >/dev/null || return 1
    hyprctl dispatch "hl.dsp.focus({workspace = $workspace})" >/dev/null
    echo "restored workspace $workspace on $target"
}

# Poll the kernel connector state as well as reacting to startup. This avoids a
# missed or transient Hyprland hotplug event leaving every output disabled.
last_state=""
last_workspace=""
while true; do
    if ! session_is_unlocked; then
        # Unplugging HDMI must still leave a screen on which to unlock. Only
        # enable the panel here; never disable outputs or reload the config.
        if session_is_locked && [ "$(connection_state)" = disconnected ] && ! layout_is_applied disconnected; then
            enable_internal
        fi
        refresh_instance || true
        sleep 1
        continue
    fi

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
