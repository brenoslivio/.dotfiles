"""Coordinate-based Open-Meteo forecasts for the panel."""
from datetime import datetime, timezone
import json
from pathlib import Path
import stat
from tempfile import NamedTemporaryFile
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo


REFRESH = 30 * 60
RETRY = 5 * 60

# The two original clocks also work before a first successful forecast.
STARTER_ZONES = {(-23.5505, -46.6333): "America/Sao_Paulo", (52.52, 13.405): "Europe/Berlin"}


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", delete=False) as tmp:
        temp = Path(tmp.name)
        try:
            tmp.write(text)
            tmp.flush()
            if path.exists():
                temp.chmod(stat.S_IMODE(path.stat().st_mode))
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)


def condition(code, day):
    if code == 0:
        return ("Clear sky", "󰖙" if day else "󰖔")
    if code in (1, 2):
        return ("Mainly clear" if code == 1 else "Partly cloudy", "󰖕" if day else "󰼱")
    if code == 3:
        return ("Overcast", "󰖐")
    if code in (45, 48):
        return ("Fog", "󰖑")
    if code in (51, 53, 55, 56, 57):
        return ("Drizzle", "󰖗")
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return ("Rain", "󰖖")
    if code in (71, 73, 75, 77, 85, 86):
        return ("Snow", "󰖘")
    if code in (95, 96, 99):
        return ("Thunderstorms", "󰖓")
    return ("Weather", "󰖐")


def fetch(coords):
    params = urlencode({
        "latitude": coords[0], "longitude": coords[1], "timezone": "auto",
        "current": "temperature_2m,apparent_temperature,is_day,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "forecast_days": 1,
    })
    with urlopen("https://api.open-meteo.com/v1/forecast?" + params, timeout=10) as response:
        data = json.load(response)
    zone = data["timezone"]
    ZoneInfo(zone)
    current, daily = data["current"], data["daily"]
    description, icon = condition(current["weather_code"], current["is_day"])
    return {
        "zone": zone, "updated": int(datetime.now(timezone.utc).timestamp()),
        "description": description, "icon": icon, "temperature": round(current["temperature_2m"]),
        "feels": round(current["apparent_temperature"]), "high": round(daily["temperature_2m_max"][0]),
        "low": round(daily["temperature_2m_min"][0]), "rain": daily["precipitation_probability_max"][0],
        "day": daily["time"][0],
    }


def cache_file(directory, coords):
    return directory / f"{coords[0]},{coords[1]}.json"


def cached(directory, coords):
    try:
        data = json.loads(cache_file(directory, coords).read_text())
        ZoneInfo(data["zone"])
        if all(key in data for key in ("temperature", "icon", "feels", "description", "high", "low", "day", "rain")):
            if isinstance(data["updated"], int):
                return data
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return {}
