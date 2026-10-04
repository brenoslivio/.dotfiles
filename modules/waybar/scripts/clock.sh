#!/usr/bin/env bash

# Config file to store the current timezone state
CONFIG_FILE="${XDG_STATE_HOME:-$HOME/.local/state}/waybar/clock_timezone"

# Default timezone (when not set)
DEFAULT_TZ="America/Sao_Paulo"

# Function to get current timezone setting
get_current_tz() {
    if [ -f "$CONFIG_FILE" ]; then
        cat "$CONFIG_FILE"
    else
        echo "$DEFAULT_TZ"
    fi
}

# Function to toggle timezone
toggle_timezone() {
    mkdir -p "$(dirname "$CONFIG_FILE")"
    current_tz=$(get_current_tz)
    if [ "$current_tz" = "Europe/Berlin" ]; then
        echo "America/Sao_Paulo" > "$CONFIG_FILE"
    else
        echo "Europe/Berlin" > "$CONFIG_FILE"
    fi
}

# Function to display the time
display_time() {
    current_tz=$(get_current_tz)
    
    # Set the timezone for this command only
    # NixOS stores timezone data in /etc/zoneinfo rather than
    # /usr/share/zoneinfo, which glibc otherwise searches by default.
    time=$(TZDIR=/etc/zoneinfo TZ="$current_tz" LC_TIME=de_DE.UTF-8 date +"%A, %d. %B  %H:%M:%S")
    calendar=$(TZDIR=/etc/zoneinfo TZ="$current_tz" LC_TIME=de_DE.UTF-8 date +"%d.%m.%Y")
    
    calendar="$calendar ($current_tz)"
    
    echo "{\"text\":\"$time\", \"tooltip\":\"$calendar\"}"
}

# Handle different commands
case "${1:-}" in
    "toggle")
        toggle_timezone
        # Send signal to waybar to update the module
        pkill -RTMIN+1 waybar
        ;;
    "check")
        # This just ensures the script can be executed (for exec-if)
        exit 0
        ;;
    *)
        display_time
        ;;
esac
