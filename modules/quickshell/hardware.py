"""Stream backlight level and BAT0 charge, health and runtime from Linux sysfs."""
import json
from pathlib import Path
import time


def external_power(directory):
    online = []
    for supply in directory.iterdir():
        try:
            kind = (supply / "type").read_text().strip()
            if kind not in {"Mains", "Wireless"} and not kind.startswith("USB"):
                continue
            scope = supply / "scope"
            if scope.exists() and scope.read_text().strip() == "Device":
                continue
            online.append(int((supply / "online").read_text()) != 0)
        except (OSError, ValueError):
            continue
    return any(online) if online else None


def battery_info(directory):
    try:
        props = dict(line.split("=", 1) for line in (directory / "BAT0/uevent").read_text().splitlines())
        capacity = int(props["POWER_SUPPLY_CAPACITY"])
        status = props["POWER_SUPPLY_STATUS"]
    except (OSError, KeyError, ValueError):
        return None

    def number(key):
        return int(props.get("POWER_SUPPLY_" + key, "0"))

    full, now, design = (number("ENERGY_" + key) for key in ("FULL", "NOW", "FULL_DESIGN"))
    watts = number("POWER_NOW") / 1e6
    if not watts:
        watts = number("CURRENT_NOW") * number("VOLTAGE_NOW") / 1e12
    rate = watts * 1e6
    if not full:
        full, now, design = (number("CHARGE_" + key) for key in ("FULL", "NOW", "FULL_DESIGN"))
        rate = number("CURRENT_NOW")

    plugged = external_power(directory)
    if plugged is None and status in {"Charging", "Discharging"}:
        plugged = status == "Charging"
    label = status
    if plugged:
        label = "Plugged · Charging" if status == "Charging" else "Plugged"
    elif plugged is False:
        label = "On battery"
    lines = [f"{capacity}% · {label}"]
    if status in {"Charging", "Discharging"} and rate > 0 and full > 0:
        remaining = now if status == "Discharging" else max(0, full - now)
        minutes = round(60 * remaining / rate)
        end = "remaining" if status == "Discharging" else "until full"
        lines.append(f"{watts:.1f} W · {minutes // 60}h {minutes % 60:02d}m {end}")
    if design:
        lines.append(f"Battery health · {full / design:.0%} of design capacity")
    return {"level": capacity, "status": status, "plugged": plugged, "label": label, "tooltip": "\n".join(lines)}


def brightness():
    for path in sorted(Path("/sys/class/backlight").glob("*")):
        try:
            maximum = int((path / "max_brightness").read_text())
            return round(100 * int((path / "brightness").read_text()) / maximum)
        except (OSError, ValueError, ZeroDivisionError):
            continue
    return None


if __name__ == "__main__":
    previous = None
    while True:
        current = {"brightness": brightness(), "battery": battery_info(Path("/sys/class/power_supply"))}
        if current != previous:
            print(json.dumps(current), flush=True)
            previous = current
        time.sleep(1)
