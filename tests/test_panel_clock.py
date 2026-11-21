from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules/quickshell"))
from clock import DEFAULT_ZONE, frame, read_zone, save_zone


class ClockTests(unittest.TestCase):
    def test_calendar_uses_the_date_on_the_selected_clock(self):
        instant = datetime(2027, 1, 31, 23, 30, tzinfo=timezone.utc)
        for zone, date, time in [(DEFAULT_ZONE, "2027-01-31", "20:30:00"),
                                 ("Europe/Berlin", "2027-02-01", "00:30:00")]:
            with self.subTest(zone=zone):
                value = frame(instant, zone)
                self.assertEqual(value["date"], date)
                self.assertIn(time, value["label"])
                self.assertEqual(value["zone"], zone)

    def test_berlin_spring_clock_change(self):
        for hour, expected in [(0, "01:30:00"), (1, "03:30:00")]:
            instant = datetime(2027, 3, 28, hour, 30, tzinfo=timezone.utc)
            self.assertIn(expected, frame(instant, "Europe/Berlin")["label"])

    def test_existing_preference_and_explicit_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quickshell/clock_timezone"
            self.assertEqual(read_zone(path), DEFAULT_ZONE)
            old = Path(directory) / "waybar/clock_timezone"
            old.parent.mkdir()
            old.write_text("Europe/Berlin\n")
            self.assertEqual(read_zone(path), "Europe/Berlin")
            save_zone(path, DEFAULT_ZONE)
            self.assertEqual(read_zone(path), DEFAULT_ZONE)
            with self.assertRaises(ValueError):
                save_zone(path, "invalid")
            self.assertEqual(path.read_text(), DEFAULT_ZONE + "\n")
            path.write_text("invalid\n")
            self.assertEqual(read_zone(path), DEFAULT_ZONE)
