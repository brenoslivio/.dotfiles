#!/usr/bin/env bash

# Use the external display exclusively when it is connected. Fall back to the
# notebook panel as soon as the external display is disconnected.

INTERNAL="eDP-1"
EXTERNAL="HDMI-A-1"
INTERNAL_MODE="1920x1080@60"
EXTERNAL_MODE="2560x1080@60"

enable_internal() {
    hyprctl keyword monitor "$INTERNAL, $INTERNAL_MODE, 0x0, 1" >/dev/null
}

enable_external_only() {
    # The static rules first activate HDMI beside the panel. Disable the panel
    # before moving HDMI to the origin so the outputs never overlap.
    hyprctl keyword monitor "$INTERNAL, disable" >/dev/null
    hyprctl keyword monitor "$EXTERNAL, $EXTERNAL_MODE, 0x0, 1" >/dev/null
}

external_is_connected() {
    hyprctl monitors all | grep -Fq "Monitor $EXTERNAL ("
}

apply_layout() {
    if external_is_connected; then
        enable_external_only
    else
        enable_internal
    fi
}

apply_layout

SOCKET="$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock"

# Reconnect if the event socket is temporarily interrupted.
while true; do
    socat - "UNIX-CONNECT:$SOCKET" | while IFS= read -r event; do
        case "$event" in
            "monitoradded>>$EXTERNAL")
                enable_external_only
                ;;
            "monitorremoved>>$EXTERNAL")
                enable_internal
                ;;
            "configreloaded>>")
                apply_layout
                ;;
        esac
    done
    sleep 1
done
