import itertools
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules/quickshell"))
import airplane


class AirplaneTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(self.enterContext(tempfile.TemporaryDirectory())) / "radios.json"
        self.soft = {"wlan": False, "bluetooth": False}
        self.hard = set()
        self.wifi = self.bt = True
        self.failed_command = None
        self.enterContext(patch.object(airplane, "state_file", return_value=self.path))
        self.enterContext(patch.object(airplane, "switches", side_effect=self.switches))
        self.enterContext(patch.object(airplane, "wifi_enabled", side_effect=lambda: self.wifi))
        self.enterContext(patch.object(airplane, "adapters", side_effect=lambda: {"adapter": ("/controller", self.bt)}))
        self.enterContext(patch.object(airplane, "run", side_effect=self.command))
        self.enterContext(patch.object(airplane.time, "sleep"))

    def switches(self):
        return {str(i): (kind, kind, soft, kind in self.hard) for i, (kind, soft) in enumerate(self.soft.items())}

    def command(self, program, *args):
        if program == "rfkill":
            action, kind = args
            if (action, kind) == self.failed_command:
                raise RuntimeError("Radio unavailable")
            self.soft[kind] = action == "block"
            # Emulate BlueZ auto-powering its controller after an unblock.
            if kind == "bluetooth":
                self.bt = action == "unblock"
        elif program == "busctl" and "set-property" in args:
            self.bt = args[-1] == "true"
        else:
            self.fail((program, args))

    def test_round_trip_for_all_preferences_and_panel_restart(self):
        for wifi, bt in itertools.product((True, False), repeat=2):
            with self.subTest(wifi=wifi, bt=bt):
                self.soft.update(wlan=not wifi, bluetooth=False)
                self.wifi, self.bt = wifi, bt
                airplane.change("on", self.path)
                self.assertTrue(all(self.soft.values()))
                self.assertTrue(airplane.status()["on"])
                airplane.change("on", self.path)  # repeated request preserves the snapshot
                airplane.change("off", self.path)
                self.assertEqual((self.wifi, self.bt), (wifi, bt))
                self.assertEqual(self.soft, {"wlan": not wifi, "bluetooth": False})
                self.assertFalse(airplane.status()["restore"])

    def test_partial_failure_rolls_back_first_radio(self):
        self.failed_command = ("block", "bluetooth")
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            airplane.change("on", self.path)
        self.assertFalse(any(self.soft.values()))
        self.assertFalse(self.path.exists())

    def test_restore_can_be_retried_and_respects_hardware_block(self):
        airplane.change("on", self.path)
        self.failed_command = ("unblock", "bluetooth")
        with self.assertRaises(RuntimeError):
            airplane.change("off", self.path)
        self.assertTrue(self.path.exists())
        self.assertFalse(airplane.status()["on"])
        self.failed_command = None
        self.hard.add("bluetooth")
        airplane.change("off", self.path)
        self.assertFalse(self.path.exists())
        self.assertIn("bluetooth", self.hard)
