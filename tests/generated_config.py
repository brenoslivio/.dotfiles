"""Validate actual Home Manager output; syntax checks do not assert GUI behavior."""
import json
from pathlib import Path
import subprocess
import sys
import tomllib
import json5

root = Path(sys.argv[1])
for relative in (".config/waybar/config.jsonc", ".config/fastfetch/config.jsonc"):
    with (root / relative).open() as stream:
        json5.load(stream)
with (root / ".config/containers/containers.conf").open("rb") as stream:
    tomllib.load(stream)
# wlogout accepts a sequence of JSON objects, rather than a JSON array.
remaining = (root / ".config/wlogout/layout").read_text().strip()
while remaining:
    _, end = json.JSONDecoder().raw_decode(remaining)
    remaining = remaining[end:].lstrip()
for directory in (".config/hypr", ".config/waybar", ".config/rofi"):
    for path in (root / directory).rglob("*.sh"):
        subprocess.run(["bash", "-n", str(path)], check=True)
for path in (root / ".local/share/applications").glob("*.desktop"):
    subprocess.run(["desktop-file-validate", str(path)], check=True)
