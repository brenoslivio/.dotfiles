#!/usr/bin/env bash

file="${TASKS_FILE:-$HOME/Dropbox/Ikiru/Ikiru.md}"

if [[ ! -r "$file" ]]; then
    printf '{"text":"0","tooltip":"Task file not found: %s"}\n' "$file"
    exit 0
fi

# In the Tasks section, top-level bullets are projects/categories. Only
# indented `- ` subitems contribute to the count, while the tooltip shows both.
task_data=$(awk '
/^##[[:space:]]+Tasks[[:space:]]*$/ {
    in_tasks = 1
    next
}

in_tasks && /^#{1,6}[[:space:]]+/ {
    exit
}

in_tasks && /^-[[:space:]]+/ {
    text = $0
    sub(/^-[[:space:]]+/, "", text)

    if (text !~ /[^[:space:]]/) next

    tooltip = tooltip (tooltip == "" ? "" : "\n") "• " text
    next
}

in_tasks && /^[[:space:]]+-[[:space:]]+/ {
    text = $0
    sub(/^[[:space:]]+-[[:space:]]+/, "", text)

    if (text !~ /[^[:space:]]/) next

    task_count++
    tooltip = tooltip (tooltip == "" ? "" : "\n") "  ✓ " text
}

END {
    print task_count + 0
    printf "%s", tooltip
}
' "$file")

task_count=${task_data%%$'\n'*}
if [[ "$task_data" == *$'\n'* ]]; then
    tooltip=${task_data#*$'\n'}
else
    tooltip=""
fi

# Escape JSON
escape_json() {
  sed -e 's/\\/\\\\/g' \
      -e 's/"/\\"/g' \
      -e ':a;N;$!ba;s/\n/\\n/g'
}

escaped_text=$(printf '%s' "$task_count" | escape_json)
escaped_tooltip=$(printf '%s' "$tooltip" | escape_json)

printf '{"text":"%s","tooltip":"%s"}\n' "$escaped_text" "$escaped_tooltip"
