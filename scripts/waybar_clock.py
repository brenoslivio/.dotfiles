"""Waybar's local date, clock and time zone menu."""
from datetime import datetime, timezone
import json
import locale
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from desktop_menu import item, menu, show_menu


DEFAULT_ZONE = "America/Sao_Paulo"
CITIES = {DEFAULT_ZONE: "São Paulo", "Europe/Berlin": "Berlin"}


def state_file():
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state"
    return Path(base) / "waybar/clock_timezone"


def read_zone(path):
    try:
        zone = path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, UnicodeDecodeError):
        return DEFAULT_ZONE
    return zone if zone in CITIES else DEFAULT_ZONE


def save_zone(path, zone):
    if zone not in CITIES:
        raise ValueError("Unknown clock time zone")
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=path.parent) as directory:
        temporary = Path(directory) / path.name
        temporary.write_text(zone + "\n", encoding="utf-8")
        temporary.replace(path)


def local_clock(instant, zone):
    now = instant.astimezone(ZoneInfo(zone))
    return {
        "text": (f"{now:%a, %d. %b}   <span foreground='#f6edf8' weight='semibold' "
                 f"font_features='tnum'>{now:%H:%M:%S}</span>"),
        "alt": now.date().isoformat(),
        "tooltip": f"{now:%A, %d.%m.%Y} ({zone})",
    }


def zone_menu(path):
    current = read_zone(path)
    instant = datetime.now(timezone.utc)
    root, choices = menu()
    for zone, city in CITIES.items():
        local_time = instant.astimezone(ZoneInfo(zone))
        mark = "✓  " if zone == current else "     "
        item(choices, f"{mark}{city}   {local_time:%H:%M}", zone)
    show_menu(root)


def stream(path, render=local_clock):
    from inotify_simple import INotify, flags

    # Match the previous clock's date formatting, including LC_ALL precedence.
    try:
        locale.setlocale(locale.LC_TIME, os.environ.get("LC_ALL") or "de_DE.UTF-8")
    except locale.Error:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    with INotify() as watcher:
        watcher.add_watch(path.parent, flags.MOVED_TO | flags.CLOSE_WRITE | flags.DELETE)
        zone = read_zone(path)
        while True:
            instant = datetime.now(timezone.utc)
            print(json.dumps(render(instant, zone)), flush=True)
            events = watcher.read(timeout=1000 - instant.microsecond // 1000)
            if any(e.name == path.name or e.mask & flags.Q_OVERFLOW for e in events):
                zone = read_zone(path)


if __name__ == "__main__":
    path = state_file()
    match sys.argv[1:]:
        case []:
            stream(path)
        case ["menu"]:
            zone_menu(path)
        case ["apply", value]:
            save_zone(path, json.loads(value))
        case _:
            sys.exit("Usage: dotfiles-clock [menu | apply ZONE_JSON]")
