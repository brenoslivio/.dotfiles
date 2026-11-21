from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from waybar_clock import DEFAULT_ZONE, local_clock, read_zone, save_zone


class ClockTests(unittest.TestCase):
    def test_calendar_uses_the_date_on_the_selected_clock(self):
        instant = datetime(2027, 1, 31, 23, 30, tzinfo=timezone.utc)
        for zone, date, time in [(DEFAULT_ZONE, "2027-01-31", "20:30:00"),
                                 ("Europe/Berlin", "2027-02-01", "00:30:00")]:
            with self.subTest(zone=zone):
                frame = local_clock(instant, zone)
                self.assertEqual(frame["alt"], date)
                self.assertIn(time, frame["text"])
                self.assertIn(zone, frame["tooltip"])

    def test_berlin_spring_clock_change(self):
        for hour, expected in [(0, "01:30:00"), (1, "03:30:00")]:
            instant = datetime(2027, 3, 28, hour, 30, tzinfo=timezone.utc)
            self.assertIn(expected, local_clock(instant, "Europe/Berlin")["text"])

    def test_existing_preference_and_explicit_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "waybar/clock_timezone"
            self.assertEqual(read_zone(path), DEFAULT_ZONE)
            path.parent.mkdir()
            path.write_text("Europe/Berlin\n")
            self.assertEqual(read_zone(path), "Europe/Berlin")
            save_zone(path, DEFAULT_ZONE)
            self.assertEqual(read_zone(path), DEFAULT_ZONE)
            with self.assertRaises(ValueError):
                save_zone(path, "invalid")
            self.assertEqual(path.read_text(), DEFAULT_ZONE + "\n")
            path.write_text("invalid\n")
            self.assertEqual(read_zone(path), DEFAULT_ZONE)
