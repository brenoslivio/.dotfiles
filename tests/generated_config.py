"""Validate actual Home Manager output; syntax checks do not assert GUI behavior."""
import json
import os
from configparser import ConfigParser
from pathlib import Path
import subprocess
import sys
import tomllib
import json5

root = Path(sys.argv[1])
with (root / ".config/fastfetch/config.jsonc").open() as stream:
    json5.load(stream)

units = root / ".config/systemd/user"
unit = ConfigParser(interpolation=None)
unit.read(units / "quickshell-panel.service")
assert os.access(unit["Service"]["ExecStart"], os.X_OK)
assert (units / "wayland-session@hyprland.desktop.target.wants/quickshell-panel.service").exists()
assert not (units / "waybar.service").exists()
ui = Path(sys.argv[2])
commands = json.loads((ui / "Config.js").read_text().removeprefix("var commands = "))
for name, command in commands.items():
    if isinstance(command, str):
        assert Path(command.removeprefix("file://")).is_file(), name
        continue
    assert os.access(command[0], os.X_OK), name
    for argument in command[1:]:
        if argument.startswith("/nix/store/"):
            assert Path(argument).is_file(), (name, argument)

with (root / ".config/containers/containers.conf").open("rb") as stream:
    tomllib.load(stream)
# wlogout accepts a sequence of JSON objects, rather than a JSON array.
remaining = (root / ".config/wlogout/layout").read_text().strip()
while remaining:
    _, end = json.JSONDecoder().raw_decode(remaining)
    remaining = remaining[end:].lstrip()
for directory in (".config/hypr", ".config/rofi"):
    for path in (root / directory).rglob("*.sh"):
        subprocess.run(["bash", "-n", str(path)], check=True)
for path in (root / ".local/share/applications").glob("*.desktop"):
    subprocess.run(["desktop-file-validate", str(path)], check=True)
