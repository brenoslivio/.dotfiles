"""Stream local times and forecasts for user-named places in the dotfiles checkout."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
from http.client import HTTPException
import json
import locale
import os
from pathlib import Path
import sys
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

import weather


def places_file():
    repo = Path(os.environ.get("DOTFILES_REPO", Path.home() / ".dotfiles"))
    return repo / "config/quickshell/places.json"


def state_dir():
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "quickshell"


def coordinates(latitude, longitude):
    lat, lon = float(latitude), float(longitude)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Latitude must be within ±90 and longitude within ±180.")
    return lat, lon


def read_places(path):
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("places.json must contain a list of places.")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] or row["id"] in seen:
            raise ValueError("Each place needs a unique ID.")
        if not isinstance(row.get("name"), str) or not row["name"].strip():
            raise ValueError("Each place needs a name.")
        row["latitude"], row["longitude"] = coordinates(row["latitude"], row["longitude"])
        seen.add(row["id"])
    return rows


def selected_id(directory):
    try:
        return (directory / "selected-place").read_text().strip()
    except (FileNotFoundError, UnicodeDecodeError):
        for parent in (directory, directory.parent / "waybar"):
            try:
                zone = (parent / "clock_timezone").read_text().strip()
                return "berlin" if zone == "Europe/Berlin" else "sao-paulo"
            except (FileNotFoundError, UnicodeDecodeError):
                continue
    return "sao-paulo"


def change_place(path, directory, action, data):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "places.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        places = read_places(path)
        target = None if action == "add" else next((p for p in places if p["id"] == data.get("id")), None)
        if action != "add" and not target:
            raise ValueError("This place no longer exists.")
        if action == "select":
            weather.atomic_write(directory / "selected-place", target["id"])
            return
        if action in ("edit", "remove") and data.get("original") != target:
            raise ValueError("This place has changed. Reopen it to edit the current version.")
        if action == "remove":
            places.remove(target)
        elif action in ("add", "edit"):
            name = data["name"].strip()
            if not name:
                raise ValueError("Enter a name for this place.")
            try:
                lat, lon = coordinates(*data["coordinates"].split(","))
            except (TypeError, ValueError):
                raise ValueError("Enter latitude, longitude (for example, -23.5505, -46.6333).") from None
            if target is None:
                target = {"id": uuid4().hex}
                places.append(target)
            target.update(name=name, latitude=lat, longitude=lon)
        else:
            raise ValueError("Unknown place action.")
        weather.atomic_write(path, json.dumps(places, ensure_ascii=False, indent=2) + "\n")
        if action == "add":
            weather.atomic_write(directory / "selected-place", target["id"])
        elif action == "remove" and selected_id(directory) == target["id"]:
            weather.atomic_write(directory / "selected-place", places[0]["id"] if places else "")


def coords(place):
    return place["latitude"], place["longitude"]


def frame(instant, places, selection, forecasts, failed):
    place = next((p for p in places if p["id"] == selection), places[0] if places else None)
    rows = []
    for p in places:
        key = coords(p)
        zone = forecasts.get(key, {}).get("zone") or weather.STARTER_ZONES.get(key)
        local = instant.astimezone(ZoneInfo(zone)) if zone else None
        rows.append({"id": p["id"], "name": p["name"], "latitude": key[0], "longitude": key[1],
                     "time": local.strftime("%H:%M (%:z)") if local else "…"})
    key = coords(place) if place else None
    forecast = forecasts.get(key, {})
    zone = forecast.get("zone") or weather.STARTER_ZONES.get(key)
    now = instant.astimezone(ZoneInfo(zone)) if zone else instant.astimezone()
    label = f"{now:%a, %d. %b}  󰥔  {now:%H:%M:%S}"
    if place and not zone:
        label = "Time zone unavailable" if key in failed else "Finding time zone…"
    local_date = now.date().isoformat() if zone or not place else ""
    return {
        "label": label, "utcOffset": now.strftime("%:z") if zone or not place else "",
        "date": local_date,
        "week": [day for day in forecast.get("week", []) if day["date"] >= local_date],
        "zone": zone or "", "places": rows, "place": place, "weather": forecast,
        "offline": key in failed,
        "updated": datetime.fromtimestamp(forecast["updated"], ZoneInfo(zone)).strftime("%d %b %H:%M") if forecast else "",
    }


def stream(path, directory):
    try:
        locale.setlocale(locale.LC_TIME, os.environ.get("LC_ALL") or "de_DE.UTF-8")
    except locale.Error:
        pass
    cache = directory / "weather"
    places, forecasts, retries = [], {}, {}
    signature = pending = None
    with ThreadPoolExecutor(max_workers=1) as executor:
        while True:
            instant = datetime.now(timezone.utc)
            timestamp = instant.timestamp()
            error = ""
            try:
                stat = path.stat()
                version = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
                if version != signature:
                    places = read_places(path)
                    signature = version
            except (OSError, ValueError, TypeError, KeyError) as exc:
                error = f"Check places.json: {exc}"
            selection = selected_id(directory)
            keys = list(dict.fromkeys(coords(p) for p in places))
            for key in keys:
                if key not in forecasts:
                    forecasts[key] = weather.cached(cache, key)
            if pending and pending.done():
                try:
                    result = pending.result()
                    forecasts[requested] = result
                    weather.atomic_write(weather.cache_file(cache, requested), json.dumps(result))
                    retries.pop(requested, None)
                except (OSError, HTTPException, ValueError, KeyError, IndexError, TypeError, ArithmeticError) as exc:
                    print(f"Weather refresh failed: {exc}", file=sys.stderr, flush=True)
                    retries[requested] = timestamp + weather.RETRY
                pending = None
            value = frame(instant, places, selection, forecasts, retries)
            value["error"] = error
            print(json.dumps(value), flush=True)
            if not pending and value["place"]:
                active = coords(value["place"])
                # Resolve other saved clocks once. Only the active forecast needs periodic refreshes.
                candidates = [active] + [key for key in keys if key != active and not forecasts[key]]
                for key in candidates:
                    if timestamp < retries.get(key, 0):
                        continue
                    forecast = forecasts[key]
                    new_local_day = key == active and forecast and (
                        datetime.fromtimestamp(forecast["updated"], ZoneInfo(forecast["zone"])).date().isoformat() != value["date"])
                    if "week" not in forecast or new_local_day or timestamp - forecast["updated"] >= weather.REFRESH:
                        requested = key
                        pending = executor.submit(weather.fetch, key)
                        break
            time.sleep(max(0.02, 1 - time.time() % 1))


if __name__ == "__main__":
    if len(sys.argv) == 1:
        stream(places_file(), state_dir())
    else:
        try:
            change_place(places_file(), state_dir(), sys.argv[1], json.loads(sys.argv[2]))
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            print(str(exc))
            sys.exit(1)
