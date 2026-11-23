from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import panel_tasks
import task_focus as focus


class FocusTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.note = self.root / "note.md"
        self.path = self.root / "task-history.json"
        self.state = self.root / "state"
        self.note.write_bytes(b"Intro\r\n## Tasks\r\n- A\r\n  - One\r\n  - One\r\n- B\r\n## Other\r\nElse")

    def action(self, action, now=1000, row=1, **fields):
        _, body = panel_tasks.section_body(panel_tasks.read_lines(self.note))
        active = focus.active_session(focus.read_history(self.path))
        return focus.apply(self.note, self.state, self.path,
                           {"action": action, "base": body, "line": row,
                            "session": active and active["id"], **fields}, now)

    def test_pause_restart_switch_rename_and_early_finish(self):
        block = self.action("start", duration="45m")["task"]
        self.action("pause", now=1720)
        first = focus.read_history(self.path)["sessions"][0]
        self.assertEqual(first["focused_seconds"], 720)
        self.note.write_text(self.note.read_text().replace("  - One ^" + block + "\n", "")
                             .replace("- B\n", "- B\n  - Renamed ^" + block + "\n"))
        self.assertEqual(focus.view(self.note, focus.read_history(self.path), None, 5000)["active"]["title"], "Renamed")
        self.action("resume", now=5000)
        second = self.action("start", now=5480, duration="")["task"]
        self.assertNotEqual(second, block)
        self.action("finish", now=5511)
        first, last = focus.read_history(self.path)["sessions"]
        self.assertEqual((first["focused_seconds"], last["focused_seconds"]), (1200, 31))
        self.assertEqual((first["title"], first["ended_at"], first["planned_seconds"]), ("One", 5480, 2700))
        self.assertEqual(first["intervals"], [[1000, 1720], [5000, 5480]])
        self.assertIsNone(last["planned_seconds"])

    def test_expiry_while_shell_closed_and_extension(self):
        self.action("start", duration="1m")
        self.action("tick", now=10000)
        session = focus.read_history(self.path)["sessions"][0]
        self.assertEqual((session["status"], session["focused_seconds"], session["ended_at"]), ("expired", 60, 1060))
        self.assertIsNone(self.action("tick", now=10000)["expired"])
        self.action("extend", now=10000, duration="2m", expiry=1060)
        with self.assertRaises(ValueError):
            self.action("finish", now=10001, expiry=1060)
        self.action("tick", now=99999)
        self.action("finish", now=99999)
        finished = focus.read_history(self.path)["sessions"][0]
        self.assertEqual((finished["focused_seconds"], finished["ended_at"]), (180, 10120))

    def test_notification_inhibitor_tracks_saved_session_and_wall_clock(self):
        def check(now, operation, next_change=None):
            with patch.object(focus.time, "time", return_value=now), patch.object(focus.subprocess, "run") as run:
                self.assertEqual(focus.sync_notifications(self.path), next_change)
                self.assertEqual(run.call_args.args[0], ["swaync-client", "--skip-wait", operation, "Task focus"])

        check(999, "-Ir")
        self.action("start", duration="1m")
        check(1001, "-Ia", 1060)
        self.action("pause", now=1010)
        check(1010, "-Ir")
        self.action("resume", now=1020)
        check(1020, "-Ia", 1070)
        check(1070, "-Ir")  # Timer elapsed with the panel closed.
        self.action("tick", now=1071)
        self.action("extend", now=1080, duration="2m")
        check(1080, "-Ia", 1200)
        self.action("start", now=1100, duration="")
        check(1150, "-Ia")
        self.action("finish", now=1150)
        check(1150, "-Ir")

    def test_deadline_projection_and_legacy_edit(self):
        block = self.action("deadline", date="2026-12-02", time="23:30", zone="America/Sao_Paulo")["task"]
        all_day = self.action("deadline", row=2, date="2026-12-02", time="")["task"]
        self.assertNotEqual(block, all_day)
        self.assertIn(b"\r\n## Other\r\nElse", self.note.read_bytes())
        target = panel_tasks.edit_choices(panel_tasks.read_lines(self.note), "A")[0][1]
        panel_tasks.save_task(self.note, "A", "Revised", target)
        self.assertIn("Revised ^" + block, self.note.read_text())
        deadlines = focus.view(self.note, focus.read_history(self.path), ZoneInfo("Europe/Berlin"), 1000)["deadlines"]
        self.assertEqual(deadlines[block], {"date": "2026-12-03", "time": "03:30", "title": "Revised"})
        self.assertEqual(deadlines[all_day]["date"], "2026-12-02")
        self.action("deadline", date="2027-01-07", time="")
        self.action("clearDeadline")
        self.assertEqual(list(focus.view(self.note, focus.read_history(self.path), None, 1000)["deadlines"]), [all_day])

    def test_invalid_selection_duration_deadline_and_stale_note(self):
        original = self.note.read_bytes()
        for action, fields in [
            ("start", {"row": 0, "duration": "37m"}), ("start", {"duration": "0"}),
            ("start", {"base": "stale", "duration": "37m"}), ("deadline", {"date": "2027-02-29", "time": ""}),
            ("deadline", {"date": "2026-03-29", "time": "02:30", "zone": "Europe/Berlin"}),
        ]:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.action(action, **fields)
        self.assertEqual(self.note.read_bytes(), original)
        self.assertFalse(self.path.exists())
        self.note.write_bytes(original.replace(b"One", b"One ^same"))
        with self.assertRaisesRegex(ValueError, "twice"):
            self.action("start", duration="5")

    def test_exact_end_time_and_local_midnight_split(self):
        self.assertEqual(focus.duration("1h 15m", 0), 4500)
        zone = ZoneInfo("America/Sao_Paulo")
        now = int(datetime(2026, 12, 2, 23, 55, 30, tzinfo=zone).timestamp())
        self.assertEqual(focus.duration("00:05", now, zone), 570)
        midnight = int(datetime(2026, 12, 2).timestamp())
        block = self.action("start", now=midnight-100, duration="")["task"]
        self.action("finish", now=midnight+80)
        view = focus.view(self.note, focus.read_history(self.path), None, midnight+100)
        self.assertEqual((view["today"][block], view["totals"][block]), (80, 180))

    def test_write_failure_returns_anchored_note_and_corruption_is_preserved(self):
        with patch.object(focus, "write_history", side_effect=OSError("disk full")):
            result = self.action("start", duration="5m")
        self.assertIn("disk full", result["error"])
        self.assertIn("^" + result["task"], result["body"])
        self.assertEqual(self.action("start", duration="5m")["task"], result["task"])
        self.path.write_text("{")
        with self.assertRaises(json.JSONDecodeError):
            self.action("tick")
        self.assertEqual(self.path.read_text(), "{")

    def test_daily_history_pause_midnight_delete_and_undo(self):
        midnight = int(datetime(2026, 12, 2).timestamp())
        self.action("start", now=midnight-90, duration="")
        at_midnight = self.action("historyDay", now=midnight, day="2026-12-02")
        self.assertEqual(at_midnight["records"][0]["seconds"], 0)
        self.action("pause", now=midnight+30)
        self.action("resume", now=midnight+60)
        self.action("finish", now=midnight+75)
        original = focus.read_history(self.path)["sessions"][0]
        self.action("start", now=midnight+80, duration="2m")
        active = focus.read_history(self.path)["sessions"][-1]
        def today():
            return self.action("historyDay", now=midnight+90, day="2026-12-02")
        self.assertEqual([r["seconds"] for r in today()["records"]], [10,45])
        self.assertEqual(today()["records"][1]["total"], 135)
        self.assertEqual(today()["earlier"], "2026-12-01")
        yesterday = self.action("historyDay", now=midnight+90, day=today()["earlier"])
        self.assertEqual((yesterday["records"][0]["seconds"], yesterday["later"]), (90, "2026-12-02"))
        with self.assertRaisesRegex(ValueError, "Finish"):
            self.action("deleteRecord", now=midnight+90, recordId=active["id"])
        receipt = self.action("deleteRecord", now=midnight+90, recordId=original["id"])["undo"]
        h = focus.read_history(self.path)
        self.assertEqual(focus.view(self.note, h, None, midnight+90)["todaySeconds"], 0)
        self.assertEqual([s["id"] for s in today()["records"]], [active["id"]])
        for _ in range(2):
            self.action("undoDelete", now=midnight+90, undo=receipt)
        h = focus.read_history(self.path)
        self.assertEqual(h["sessions"], [original, active])
        self.assertEqual(focus.view(self.note, h, None, midnight+90)["todaySeconds"], 45)

    def test_concurrent_starts_from_same_panel_state(self):
        def start(_):
            try:
                self.action("start", duration="5m", session="")
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(start, range(2))), [False, True])
        self.assertEqual(len(focus.read_history(self.path)["sessions"]), 1)
