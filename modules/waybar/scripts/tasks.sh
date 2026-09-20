#!/usr/bin/env bash

file="$HOME/Dropbox/Ikiru/Ikiru.md"

tasks=$(awk '
/^- \[[ xX]\]/ {
    done = ($0 ~ /\[[xX]\]/)
    if (!done) {
        sub(/^- \[[ xX]\] /, "", $0)  # remove prefix
        print $0
    }
}
' "$file")

task_count=$(echo "$tasks" | grep -c .)

# Tooltip: first 5 pending tasks
tooltip=$(echo "$tasks" | head -n 5 | sed 's/^/• /')

# Escape JSON
escape_json() {
  sed -e 's/\\/\\\\/g' \
      -e 's/"/\\"/g' \
      -e ':a;N;$!ba;s/\n/\\n/g'
}

escaped_text=$(echo "$task_count" | escape_json)
escaped_tooltip=$(echo "$tooltip" | escape_json)

echo "{\"text\": \"$escaped_text\", \"tooltip\": \"$escaped_tooltip\"}"