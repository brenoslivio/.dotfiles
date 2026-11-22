"""Look up street coordinates for the Quickshell place editor."""
from http.client import HTTPException
import json
import math
import sys
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def matches(features):
    results = []
    seen = {}
    for feature in features:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        if geometry.get("type") != "Point" or props.get("type") not in ("street", "house"):
            continue
        try:
            lon, lat = map(float, geometry["coordinates"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        street = props.get("street") or props.get("name")
        if not street:
            continue
        number = props.get("housenumber")
        title = f"{street} {number}" if number else street
        parts = [props.get(field) for field in ("district", "city", "state", "country")]
        area = ", ".join(dict.fromkeys(part for part in parts if part))
        # A street often has several OSM segments with different postcodes.
        # Group nearby segments in the same locality, keeping the best-ranked point.
        key = (title.casefold(), area.casefold(), bool(number))
        points = seen.setdefault(key, [])
        if any(math.hypot(lat - y, (lon - x) * math.cos(math.radians(lat))) < 0.01 for y, x in points):
            continue
        points.append((lat, lon))
        results.append({"title": title, "area": area, "approximate": not number,
                        "latitude": lat, "longitude": lon})
        if len(results) == 5:
            break
    return results


def search(query):
    params = urlencode({"q": query, "layer": ["street", "house"], "limit": 30}, doseq=True)
    request = Request("https://photon.komoot.io/api/?" + params,
                      headers={"User-Agent": "Quickshell-Places/1.0", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=8) as response:
            return {"results": matches(json.load(response)["features"])}
    except HTTPError as exc:
        if exc.code == 429:
            return {"error": "Too many searches. Try again shortly."}
    except (OSError, HTTPException, ValueError, KeyError, TypeError, AttributeError):
        pass
    return {"error": "Street search is unavailable. Try again or enter coordinates manually."}


if __name__ == "__main__":
    print(json.dumps(search(sys.argv[1])))
