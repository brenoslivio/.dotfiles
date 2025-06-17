#!/usr/bin/env bash

if pgrep -x rofi > /dev/null; then
    pkill rofi
else
    rofi -show drun -switchers drun -show-icons -modes drun,calc
fi