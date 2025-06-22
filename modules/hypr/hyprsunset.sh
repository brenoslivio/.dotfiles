#!/usr/bin/env bash

# Kill current hyprsunset session
pkill hyprsunset

current_hour=$(date +%H)

# Temperature settings
day_temp=6500    # Daytime temperature (6:00-16:59)
night_temp=3000  # Nighttime temperature (21:00-5:00)

if [ "$current_hour" -ge 17 ] && [ "$current_hour" -lt 21 ]; then
    # Gradual decrease from 17:00 to 21:00 (4 hours)
    hours_past_17=$((current_hour - 17))
    temp=$((day_temp - (hours_past_17 * (day_temp - night_temp) / 4)))
    echo "Evening transition (17:00-21:00): Setting temperature to $temp"
    hyprsunset -t $temp
elif [ "$current_hour" -ge 21 ] || [ "$current_hour" -le 5 ]; then
    # Full nighttime (21:00-5:00)
    echo "Nighttime: Setting temperature to $night_temp"
    hyprsunset -t $night_temp
else
    # Daytime (6:00-16:59)
    echo "Daytime: Setting temperature to $day_temp"
    hyprsunset -t $day_temp
fi