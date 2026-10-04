#!/usr/bin/env bash

set -o pipefail

cava -p "${XDG_CONFIG_HOME:-$HOME/.config}/waybar/cava.conf" 2>/dev/null |
    awk -F ';' '
        BEGIN {
            bars[0] = "▁"
            bars[1] = "▂"
            bars[2] = "▃"
            bars[3] = "▄"
            bars[4] = "▅"
            bars[5] = "▆"
            bars[6] = "▇"
            bars[7] = "█"
        }
        {
            output = ""
            for (i = 1; i <= NF; i++) {
                if ($i ~ /^[0-7]$/) {
                    output = output bars[$i]
                }
            }
            if (output != "") {
                print output
                fflush()
            }
        }
    '
