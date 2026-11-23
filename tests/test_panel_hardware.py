from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "modules/quickshell"), str(ROOT / "modules/hypr")]
from hardware import battery_info
import night_light


class BatteryTests(unittest.TestCase):
    def test_adapter_is_independent_of_charge_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, kind in [("ADP0", "Mains"), ("BAT0", "Battery"), ("mouse", "Battery")]:
                (root / name).mkdir()
                (root / name / "type").write_text(kind)
                (root / name / "online").write_text("1")
            for status, online, expected in [("Full", "1", "Plugged"), ("Charging", "1", "Plugged · Charging"),
                                             ("Discharging", "0", "On battery")]:
                (root / "BAT0/uevent").write_text(f"POWER_SUPPLY_CAPACITY=98\nPOWER_SUPPLY_STATUS={status}\n")
                (root / "ADP0/online").write_text(online)
                info = battery_info(root)
                self.assertEqual((info["plugged"], info["label"]), (online == "1", expected))
            (root / "ADP0/online").unlink()
            self.assertFalse(battery_info(root)["plugged"])
            (root / "BAT0/uevent").write_text("POWER_SUPPLY_CAPACITY=98\nPOWER_SUPPLY_STATUS=Full\n")
            self.assertIsNone(battery_info(root)["plugged"])


class NightLightTests(unittest.TestCase):
    def setUp(self):
        self.profiles = json.loads((ROOT / "modules/hypr/night-light.json").read_text())
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "override.json"
        self.actual = 6500

    def run_action(self, when, action):
        def temperature(value=None):
            if value is not None:
                self.actual = value
            return self.actual
        with patch.object(night_light, "temperature", temperature):
            return night_light.handle(self.profiles, self.path, action, datetime.fromisoformat(when))

    def test_evening_pause_survives_intermediate_steps_midnight_and_restart(self):
        self.run_action("2026-11-23T18:00", "apply")
        self.assertEqual(self.actual, 5625)
        self.assertEqual(self.run_action("2026-11-23T18:30", "toggle")["until"], "06:00")
        for when in ["2026-11-23T19:00", "2026-11-23T21:25", "2026-11-24T03:00"]:
            self.assertEqual(self.run_action(when, "apply")["kelvin"], 6500)
        self.assertFalse(self.run_action("2026-11-24T06:00", "apply")["manual"])
        self.assertFalse(self.path.exists())

    def test_day_override_expires_at_dusk_and_resume_uses_current_step(self):
        self.assertEqual(self.run_action("2026-11-23T12:00", "toggle")["until"], "18:00")
        self.assertEqual(self.run_action("2026-11-23T15:00", "3400")["kelvin"], 3400)
        self.assertEqual(self.run_action("2026-11-23T18:00", "apply")["kelvin"], 5625)
        self.run_action("2026-11-23T18:20", "3750")
        self.assertEqual(self.run_action("2026-11-23T19:00", "apply")["kelvin"], 3750)
        self.assertEqual(self.run_action("2026-11-23T19:10", "resume")["kelvin"], 4750)
        self.assertFalse(self.path.exists())

    def test_custom_overnight_hours_and_short_ramp(self):
        state = self.run_action("2026-11-23T23:30", "schedule 23:00 01:00")
        self.assertEqual((state["kelvin"], state["next"]), (4750, "00:00"))
        self.assertEqual(self.run_action("2026-11-24T00:30", "apply")["kelvin"], 3000)
        self.assertEqual(self.run_action("2026-11-24T01:00", "apply")["kelvin"], 6500)
        with self.assertRaises(ValueError):
            self.run_action("2026-11-24T01:00", "schedule 08:00 08:00")
        self.assertEqual(self.run_action("2026-11-24T01:00", "defaults")["start"], "18:00")

    def test_dst_skipped_and_repeated_hours(self):
        profiles = night_light.custom_profiles(self.profiles, "02:15", "06:00")
        berlin = ZoneInfo("Europe/Berlin")
        before = datetime(2027, 3, 28, 1, 55, tzinfo=berlin)
        self.assertEqual(night_light.scheduled(profiles, before)[1].hour, 3)
        repeated = datetime(2027, 10, 31, 2, 5, tzinfo=berlin, fold=1)
        self.assertEqual(night_light.scheduled(profiles, repeated)[0], 5625)

    def test_existing_hours_and_custom_range(self):
        settings = self.path.with_name("hours.json")
        settings.write_text('["20:00","05:00"]')
        state = self.run_action("2026-11-23T12:00", "status")
        self.assertEqual((state["start"], state["end"], state["daytime"], state["nighttime"]),
                         ("20:00", "05:00", 6500, 3000))
        self.run_action("2026-11-23T12:00", "schedule 20:00 05:00 6000 4000")
        for hour, expected in [(19, 6000), (20, 5500), (21, 5000), (22, 4500), (23, 4000)]:
            state = self.run_action(f"2026-11-23T{hour}:00", "apply")
            self.assertEqual((state["kelvin"], state["powered"]), (expected, hour >= 20))
        paused = self.run_action("2026-11-24T00:30", "toggle")
        self.assertEqual((paused["kelvin"], paused["powered"], paused["until"]), (6000, False, "05:00"))
        self.assertEqual(self.run_action("2026-11-24T01:00", "toggle")["kelvin"], 4000)
        self.assertEqual(self.run_action("2026-11-24T06:00", "schedule 21:00 07:00")["daytime"], 6000)
        for temperatures in ["5500 5500", "5000 6000", "6700 3000", "6000 2000", "hot cold"]:
            with self.assertRaises(ValueError):
                self.run_action("2026-11-24T06:00", "schedule 21:00 07:00 " + temperatures)
        self.assertEqual(json.loads(settings.read_text())["nighttime"], 4000)
        restored = self.run_action("2026-11-24T12:00", "defaults")
        self.assertEqual((restored["start"], restored["end"], restored["daytime"], restored["nighttime"]),
                         ("18:00", "06:00", 6500, 3000))

    def test_rounding_does_not_shift_the_night_boundary(self):
        state = self.run_action("2026-11-23T20:00", "schedule 20:00 05:00 4001 4000")
        self.assertEqual((state["kelvin"], state["boundary"], state["powered"]), (4001, "05:00", True))
