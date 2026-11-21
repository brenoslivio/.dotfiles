"""Stream the panel clock and remember its selected time zone."""
from datetime import datetime, timezone
import json
import locale
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo


DEFAULT_ZONE = "America/Sao_Paulo"
CITIES = {DEFAULT_ZONE: "São Paulo", "Europe/Berlin": "Berlin"}


def state_file():
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state"
    return Path(base) / "quickshell/clock_timezone"


def read_zone(path):
    # Existing installations may still have their choice in the original state directory.
    for candidate in (path, path.parent.parent / "waybar/clock_timezone"):
        try:
            zone = candidate.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            continue
        except UnicodeDecodeError:
            return DEFAULT_ZONE
        return zone if zone in CITIES else DEFAULT_ZONE
    return DEFAULT_ZONE


def save_zone(path, zone):
    if zone not in CITIES:
        raise ValueError("Unknown clock time zone")
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=path.parent) as directory:
        temporary = Path(directory) / path.name
        temporary.write_text(zone + "\n", encoding="utf-8")
        temporary.replace(path)


def frame(instant, zone):
    now = instant.astimezone(ZoneInfo(zone))
    return {
        "label": f"{now:%a, %d. %b}   {now:%H:%M:%S}",
        "date": now.date().isoformat(),
        "zone": zone,
        "cities": [{"id": key, "name": name, "time": instant.astimezone(ZoneInfo(key)).strftime("%H:%M")}
                   for key, name in CITIES.items()],
    }


def stream(path):
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
            print(json.dumps(frame(instant, zone)), flush=True)
            events = watcher.read(timeout=1000 - instant.microsecond // 1000)
            if any(e.name == path.name or e.mask & flags.Q_OVERFLOW for e in events):
                zone = read_zone(path)


if __name__ == "__main__":
    path = state_file()
    match sys.argv[1:]:
        case []:
            stream(path)
        case ["apply", value]:
            save_zone(path, json.loads(value))
        case _:
            sys.exit("Usage: dotfiles-clock [apply ZONE_JSON]")
