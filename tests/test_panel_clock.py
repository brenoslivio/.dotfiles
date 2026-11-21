from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

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

    def test_calendar_uses_the_date_on_the_selected_clock(self):
        instant = datetime(2027, 1, 31, 23, 30, tzinfo=timezone.utc)
        for place, date, time in [("sao-paulo", "2027-01-31", "20:30:00"), ("berlin", "2027-02-01", "00:30:00")]:
            value = frame(instant, self.places, place, {}, {})
            self.assertEqual(value["date"], date)
            self.assertIn(time, value["label"])

    def test_berlin_spring_clock_change(self):
        for hour, expected in [(0, "01:30:00"), (1, "03:30:00")]:
            instant = datetime(2027, 3, 28, hour, 30, tzinfo=timezone.utc)
            self.assertIn(expected, frame(instant, self.places, "berlin", {}, {})["label"])

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

    def test_weather_presentation(self):
        self.assertNotEqual(weather.condition(0, 1)[1], weather.condition(0, 0)[1])
        self.assertEqual(weather.condition(95, 1)[0], "Thunderstorms")
