"""Plain clock and city data for the Quickshell panel, using the desktop's saved zone."""
from zoneinfo import ZoneInfo

from waybar_clock import CITIES, state_file, stream


def frame(instant, zone):
    now = instant.astimezone(ZoneInfo(zone))
    return {
        "label": f"{now:%a, %d. %b}   {now:%H:%M:%S}",
        "date": now.date().isoformat(),
        "zone": zone,
        "cities": [{"id": key, "name": name, "time": instant.astimezone(ZoneInfo(key)).strftime("%H:%M")}
                   for key, name in CITIES.items()],
    }


if __name__ == "__main__":
    stream(state_file(), frame)
