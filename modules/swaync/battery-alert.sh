# Read the laptop battery and AC adapter. Other power supplies include peripherals.
supplies=$1
state_file="${XDG_RUNTIME_DIR:?}/battery-alert-level"
[[ -r "$supplies/BAT0/status" ]] || exit 0
read -r status < "$supplies/BAT0/status"
if [[ -r "$supplies/ADP0/online" ]]; then
    read -r online < "$supplies/ADP0/online"
else
    online=0
fi

if [[ $online == 1 || $status == Charging || $status == Full ]]; then
    rm -f -- "$state_file"
    exit 0
fi
[[ $status == Discharging ]] || exit 0
read -r capacity < "$supplies/BAT0/capacity"
[[ $capacity =~ ^[0-9]{1,3}$ ]] || exit 1

previous=
if [[ -f "$state_file" ]]; then
    read -r previous < "$state_file"
fi
if (( 10#$capacity <= 10 )); then
    [[ $previous != critical ]] || exit 0
    level=critical
    urgency=critical
    timeout=0
    title="Battery critically low"
    icon=battery-caution-symbolic
elif (( 10#$capacity <= 20 )); then
    [[ -z $previous ]] || exit 0
    level=warning
    urgency=normal
    timeout=10000
    title="Battery running low"
    icon=battery-low-symbolic
else
    exit 0
fi

notify-send --app-name=Power --category=device --icon="$icon" \
    --urgency="$urgency" --expire-time="$timeout" \
    "$title" "$capacity% remaining. Connect your charger."
# Only record a delivered alert, so a failed notification is retried.
printf '%s\n' "$level" > "$state_file.tmp"
mv -f -- "$state_file.tmp" "$state_file"
