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
assert unit["Service"]["BusName"] == "org.freedesktop.Notifications"
activation = ConfigParser()
activation.read(root / ".local/share/dbus-1/services/org.freedesktop.Notifications.service")
assert activation["D-BUS Service"]["SystemdService"] == "quickshell-panel.service"
assert not (units / "swaync.service").exists()
assert (units / "battery-alert.timer").exists()
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
power_actions = json.loads((ui / "PowerActions.js").read_text().removeprefix("var actions = "))
assert [(action["label"], action["key"]) for action in power_actions] == [
    ("Lock", "l"), ("Suspend", "u"), ("Hibernate", "h"),
    ("Log Out", "e"), ("Reboot", "r"), ("Shut Down", "s"),
]
for action in power_actions:
    assert (ui / (action["symbol"] + "-symbolic.svg")).is_file(), action["label"]
    assert os.access(action["command"][0], os.X_OK), action["label"]
assert os.access(root / ".config/quickshell/power-menu", os.X_OK)
for directory in (".config/hypr", ".config/rofi"):
    for path in (root / directory).rglob("*.sh"):
        subprocess.run(["bash", "-n", str(path)], check=True)
for path in (root / ".local/share/applications").glob("*.desktop"):
    subprocess.run(["desktop-file-validate", str(path)], check=True)
