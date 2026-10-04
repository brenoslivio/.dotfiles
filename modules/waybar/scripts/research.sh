#!/usr/bin/env bash

file="${RESEARCH_FILE:-$HOME/Dropbox/Ikiru/Research/SMART.md}"

if [[ ! -r "$file" ]]; then
    printf '{"text":"0","tooltip":"Research file not found: %s"}\n' "$file"
    exit 0
fi

tasks=$(awk -F'|' '
  function parse_date(d,m,y) {
    return y m d
  }
  BEGIN {
    header_found = 0
  }
  /^[ \t]*\|/ {
    if (!header_found) {
      header_found = 1
      next
    }
    for(i=1; i<=NF; i++) gsub(/^[ \t]+|[ \t]+$/, "", $i)

    line = $0
    if (index(line, "%") == 0) next

    task = $2
    status = tolower($5)
    if (task ~ /^\*\*/ || task ~ /^:/ || task ~ /^---/) next
    if (status == "✓" || status == "done") next

    split($6, dateparts, ".")
    if (length(dateparts) == 3) {
      d = dateparts[1]
      m = dateparts[2]
      y = dateparts[3]
    } else {
      d = "01"; m = "01"; y = "2100"
    }
    sortdate = y m d

    print sortdate "|" $2 "|" $3 "|" $6
  }
' "$file" | sort)

if [[ -n "$tasks" ]]; then
  task_count=$(printf '%s\n' "$tasks" | grep -c '^')
else
  task_count=0
fi
text="${task_count}"

# Show top 5 tasks in tooltip
tooltip=$(printf '%s\n' "$tasks" | head -n 5 | awk -F'|' 'NF > 1 {printf "• %s - %s (%s)\n", $2, $3, $4}')

# Escape JSON special characters
escape_json() {
  printf '%s' "$1" | sed \
    -e 's/\\/\\\\/g' \
    -e 's/"/\\"/g' \
    -e ':a;N;$!ba;s/\n/\\n/g'
}

escaped_text=$(escape_json "$text")
escaped_tooltip=$(escape_json "$tooltip")

printf '{"text":"%s","tooltip":"%s"}\n' "$escaped_text" "$escaped_tooltip"
