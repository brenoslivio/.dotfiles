from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules/quickshell"))
from clock import change_place, coords, frame, read_places, selected_id
import weather


class ClockTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name) / "quickshell"
        self.path = Path(temp.name) / "places.json"
        self.places = [
            dict(id="sao-paulo", name="Home", latitude=-23.5505, longitude=-46.6333),
            dict(id="berlin", name="Work", latitude=52.52, longitude=13.405),
        ]
        self.path.write_text(json.dumps(self.places))
        self.enterContext(patch("clock.system_zone", return_value="America/Sao_Paulo"))
        self.set_zone = self.enterContext(patch("clock.set_zone"))

    def test_selection_requires_confirmed_system_change(self):
        self.change("select", id="berlin")
        self.set_zone.assert_called_with("Europe/Berlin")
        self.set_zone.side_effect = ValueError("Access denied")
        with self.assertRaisesRegex(ValueError, "Access denied"):
            self.change("select", id="sao-paulo")
        self.assertEqual(selected_id(self.directory), "berlin")

    def test_calendar_uses_the_date_on_the_selected_clock(self):
        instant = datetime(2027, 1, 31, 23, 30, tzinfo=timezone.utc)
        for place, date, time in [("sao-paulo", "2027-01-31", "20:30:00"), ("berlin", "2027-02-01", "00:30:00")]:
            value = frame(instant, self.places, place, {}, {})
            self.assertEqual(value["date"], date)
            self.assertIn(time, value["label"])

    def test_berlin_spring_clock_change(self):
        for hour, expected, offset in [(0, "01:30:00", "+01:00"), (1, "03:30:00", "+02:00")]:
            instant = datetime(2027, 3, 28, hour, 30, tzinfo=timezone.utc)
            value = frame(instant, self.places, "berlin", {}, {})
            self.assertIn(expected, value["label"])
            self.assertEqual(value["utcOffset"], offset)
            self.assertEqual(value["places"][1]["time"], f"{expected[:5]} ({offset})")
            self.assertTrue(value["places"][0]["time"].endswith(" (-03:00)"))

    def change(self, action, **payload):
        change_place(self.path, self.directory, action, payload)

    def test_old_preference_and_selection_dont_edit_dotfiles(self):
        old = self.directory.parent / "waybar/clock_timezone"
        old.parent.mkdir()
        old.write_text("Europe/Berlin\n")
        self.assertEqual(selected_id(self.directory), "berlin")
        original = self.path.read_bytes()
        self.change("select", id="sao-paulo")
        self.assertEqual(selected_id(self.directory), "sao-paulo")
        self.assertEqual(self.path.read_bytes(), original)

    def test_edit_same_place_and_remove_selection(self):
        self.enterContext(patch.object(weather, "fetch", return_value={"zone": "America/Los_Angeles"}))
        self.change("add", name="Studio", coordinates=" 34, -118 ")
        studio = read_places(self.path)[-1]
        self.assertEqual(selected_id(self.directory), studio["id"])
        self.change("edit", id=studio["id"], original=studio, name="Office", coordinates="35, -117")
        with self.assertRaises(ValueError):
            self.change("remove", id=studio["id"], original=studio)
        updated = read_places(self.path)[-1]
        self.assertEqual(coords(updated), (35, -117))
        self.change("remove", id=studio["id"], original=updated)
        self.assertEqual(selected_id(self.directory), "sao-paulo")
        self.assertEqual(read_places(self.path), self.places)

    def test_invalid_coordinates_leave_places_intact(self):
        for bad in ("nan, 0", "1, 181", "banana", "92, 0", "10,20,30"):
            with self.assertRaises(ValueError):
                self.change("add", name="Broken", coordinates=bad)
        self.assertEqual(read_places(self.path), self.places)

    def test_cache_follows_coordinates_even_when_place_is_edited(self):
        instant = datetime(2027, 3, 28, tzinfo=timezone.utc)
        key = coords(self.places[1])
        forecast = {"zone": "Europe/Berlin", "updated": int(instant.timestamp()), "temperature": 8}
        value = frame(instant, self.places, "berlin", {key: forecast}, {key: 1})
        self.assertTrue(value["offline"])
        self.assertEqual(value["weather"]["temperature"], 8)
        self.places[1]["latitude"] += 1
        value = frame(instant, self.places, "berlin", {key: forecast}, {})
        self.assertEqual(value["weather"], {})
        self.assertFalse(value["zone"])
        self.assertFalse(value["date"])
        self.assertEqual(value["utcOffset"], "")
        self.assertEqual(value["places"][1]["time"], "…")

    def test_weather_presentation(self):
        self.assertNotEqual(weather.condition(0, 1)[1], weather.condition(0, 0)[1])
        self.assertEqual(weather.condition(95, 1)[0], "Thunderstorms")

    def test_week_switches_places_at_local_midnight_even_offline(self):
        instant = datetime(2027, 1, 31, 23, 30, tzinfo=timezone.utc)
        week = [{"date": "2027-01-31"}, {"date": "2027-02-01"}]
        forecasts = {coords(p): {"zone": weather.STARTER_ZONES[coords(p)], "updated": 0, "week": week}
                     for p in self.places}
        for place, expected in [("berlin", week[1:]), ("sao-paulo", week)]:
            value = frame(instant, self.places, place, forecasts, set(forecasts))
            self.assertTrue(value["offline"])
            self.assertEqual(value["week"], expected)

    def test_fetch_week_preserves_missing_values_and_current_conditions(self):
        daily = {"time": [f"2027-02-{day:02d}" for day in range(1, 8)], "weather_code": [0] * 6 + [65],
                 "temperature_2m_max": [20.8] * 7, "temperature_2m_min": [3] * 6 + [None],
                 "precipitation_probability_max": [0] * 6 + [None]}
        data = {"timezone": "Europe/Berlin", "daily": daily,
                "current": {"temperature_2m": 12, "apparent_temperature": 10, "weather_code": 3, "is_day": 1}}
        with patch.object(weather, "urlopen", return_value=BytesIO(json.dumps(data).encode())) as request:
            result = weather.fetch(coords(self.places[1]))
        self.assertIn("forecast_days=7", request.call_args.args[0])
        self.assertEqual(result["description"], "Overcast")
        self.assertEqual(len(result["week"]), 7)
        first, last = result["week"][0], result["week"][-1]
        self.assertEqual((first["high"], first["rain"], last["description"]), (21, 0, "Rain"))
        self.assertIsNone(last["low"])
        self.assertIsNone(last["rain"])
        del result["week"]
        self.directory.mkdir()
        weather.atomic_write(weather.cache_file(self.directory, coords(self.places[1])), json.dumps(result))
        self.assertEqual(weather.cached(self.directory, coords(self.places[1])), result)
