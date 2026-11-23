"""Apply the Hyprsunset schedule and temporary overrides from the panel."""
from datetime import datetime, time, timedelta
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time as clock
from zoneinfo import ZoneInfo


NEUTRAL = 6500


def scheduled(profiles, now):
    events = []
    for offset in (-1, 0, 1, 2):
        for p in sorted(profiles, key=lambda p: p["time"]):
            wall = datetime.combine(now.date() + timedelta(days=offset), time.fromisoformat(p["time"]), now.tzinfo)
            # First occurrence in a repeated hour, first valid minute in a skipped hour.
            while datetime.fromtimestamp(wall.timestamp(), now.tzinfo).replace(tzinfo=None) != wall.replace(tzinfo=None):
                wall += timedelta(minutes=1)
            events.append((wall.timestamp(), p["temperature"], p["night"]))
    _, current, night = next(event for event in reversed(events) if event[0] <= now.timestamp())
    future = [event for event in events if event[0] > now.timestamp()]
    boundary = next(stamp for stamp, _, warm in future if warm != night)
    return current, datetime.fromtimestamp(boundary, now.tzinfo), datetime.fromtimestamp(future[0][0], now.tzinfo), night


def custom_profiles(defaults, start, end, daytime=NEUTRAL, nighttime=3000):
    def minute(value):
        t = time.fromisoformat(value)
        if value != t.strftime("%H:%M"):
            raise ValueError("Use 24-hour times in HH:MM format.")
        return t.hour * 60 + t.minute

    first, last = minute(start), minute(end)
    duration = (last - first) % 1440
    if not duration:
        raise ValueError("Choose different start and end times.")
    if not 2500 <= nighttime < daytime <= 6500:
        raise ValueError("Choose temperatures from 2500 to 6500 K, with a warmer (lower) night setting.")
    warm = [p for p in defaults if p["temperature"] < NEUTRAL]
    steps = {last: (daytime, False)}
    for i in range(len(warm)):
        stamp = (first + min(i * 60, i * duration // len(warm))) % 1440
        steps[stamp] = (round(daytime + (nighttime - daytime) * (i + 1) / len(warm)), True)
    return [{"time": f"{m // 60:02}:{m % 60:02}", "temperature": temp, "night": night}
            for m, (temp, night) in sorted(steps.items())]


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value))
    temporary.replace(path)


def temperature(value=None):
    command = ["hyprctl", "hyprsunset", "temperature"]
    if value is not None:
        command.append(str(value))
    result = subprocess.run(command, text=True, capture_output=True, timeout=2, check=True).stdout.strip()
    if value is None:
        return int(result)
    if result != "ok":
        raise ValueError("Hyprsunset did not accept the temperature")


def handle(defaults, path, action, now):
    hours_file = path.with_name("hours.json")
    default_start = next(p["time"] for p in defaults if p["temperature"] < NEUTRAL)
    default_end = next(p["time"] for p in defaults if p["temperature"] == NEUTRAL)
    daytime, nighttime = NEUTRAL, min(p["temperature"] for p in defaults)
    try:
        saved = json.loads(hours_file.read_text())
        if isinstance(saved, list):  # Existing hours-only preference.
            start, end = saved
        else:
            start, end = saved["start"], saved["end"]
            daytime, nighttime = saved["daytime"], saved["nighttime"]
    except FileNotFoundError:
        start, end = default_start, default_end
    saving = action.startswith("schedule ") or action == "defaults"
    if saving:
        if action == "defaults":
            start, end = default_start, default_end
            daytime, nighttime = NEUTRAL, min(p["temperature"] for p in defaults)
        else:
            _, start, end, *temperatures = action.split()
            if temperatures:
                daytime, nighttime = map(int, temperatures)
    profiles = custom_profiles(defaults, start, end, daytime, nighttime)
    target, boundary, upcoming, night = scheduled(profiles, now)
    zone = str(now.tzinfo or "")
    try:
        override = json.loads(path.read_text())
        if override["until"] <= now.timestamp() or override.get("zone", zone) != zone:
            override = None
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        override = None

    active = temperature()
    powered = (active < daytime) if override else night
    if action == "toggle":
        action = str(daytime if powered else target if night and target < daytime else nighttime)
    if action == "resume" or saving:
        override = None
    elif action not in {"apply", "status"}:
        kelvin = int(action)
        if not 2500 <= kelvin <= NEUTRAL:
            raise ValueError("Temperature outside slider range")
        override = {"temperature": kelvin, "until": boundary.timestamp(), "zone": zone}

    if action != "status":
        desired = override["temperature"] if override else target
        if active != desired:
            temperature(desired)
        active = desired
        if override:
            write_json(path, override)
        else:
            path.unlink(missing_ok=True)
        if saving:
            write_json(hours_file, {"start": start, "end": end, "daytime": daytime, "nighttime": nighttime})

    return {"available": True, "kelvin": active, "manual": bool(override),
            "daytime": daytime, "nighttime": nighttime, "powered": active < daytime if override else night,
            "until": datetime.fromtimestamp(override["until"], now.tzinfo).strftime("%H:%M") if override else "",
            "start": start, "end": end, "zone": zone, "next": upcoming.strftime("%H:%M"),
            "boundary": boundary.strftime("%H:%M"), "schedule": profiles}


def main():
    profiles = json.loads(Path(sys.argv[1]).read_text())
    directory = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "dotfiles-night-light"
    directory.mkdir(parents=True, exist_ok=True)
    action = sys.argv[2]
    for attempt in range(20 if action == "startup" else 1):
        try:
            with (directory / "lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                state = handle(profiles, directory / "override.json", "apply" if action == "startup" else action,
                               datetime.now(local_zone()))
            print(json.dumps(state), flush=True)
            return
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            if action == "status":
                print(json.dumps({"available": False, "schedule": profiles}))
                return
            if action != "startup" or attempt == 19:
                sys.exit(f"Night Light unavailable: {error}")
            clock.sleep(0.15)


def local_zone():
    try:
        with open("/etc/localtime", "rb") as f:
            key = os.path.realpath(f.name).partition("/zoneinfo/")[2] or "Local"
            return ZoneInfo.from_file(f, key=key)
    except FileNotFoundError:
        return ZoneInfo("UTC")


if __name__ == "__main__":
    main()
