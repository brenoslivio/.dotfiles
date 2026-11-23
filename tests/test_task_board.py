import os
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import panel_tasks
import task_board
import task_focus as focus


class BoardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.note, self.history, self.state = root / "note", root / "task-history.json", root / "state"
        self.initial = (b"Intro\r\n## Tasks\r\n- Design ^design\r\n\t- Sketch ^sketch\r\n"
                        b"\t  description\r\n\r\n\t\t- Layout ^layout\r\n"
                        b"Keep this paragraph.\r\n- Ship ^ship\r\n  - Check ^check\r\n## Notes\r\nTail")
        self.note.write_bytes(self.initial)

    def rows(self):
        return task_board.tree(panel_tasks.read_lines(self.note))

    def item(self, key):
        return next(row.display() for row in self.rows() if row.key == key)

    def run_action(self, action, key=None, now=100, **fields):
        req = {"action": action, **fields}
        if key:
            req["target"] = self.item(key)
        return focus.apply(self.note, self.state, self.history, req, now)

    def test_repeated_add_and_scoped_rename_preserve_other_edit(self):
        new = self.run_action("project", title="Work")["key"]
        a = self.run_action("add", new, title="Write")["key"]
        b = self.run_action("add", new, title="Write")["key"]
        self.assertNotEqual(a, b)
        old = self.item(a)
        self.note.write_bytes(self.note.read_bytes().replace(b"Check ^check", b"Checked externally ^check"))
        self.run_action("rename", target=old, title="Publish")
        with self.assertRaisesRegex(ValueError, "Publish"):
            self.run_action("rename", target=old, title="My draft")
        self.assertEqual(self.item(b)["title"], "Write")
        self.assertIn(b"Checked externally", self.note.read_bytes())
        self.assertTrue(self.note.read_bytes().endswith(b"## Notes\r\nTail"))

    def test_nested_move_reindents_descriptions_and_keeps_prose(self):
        self.run_action("move", "sketch", destination=self.item("ship"))
        data = self.note.read_bytes()
        self.assertIn(b"- Design ^design\r\nKeep this paragraph.\r\n- Ship", data)
        self.assertIn(b"  - Sketch ^sketch\r\n    description\r\n\r\n  \t- Layout ^layout", data)
        self.assertEqual(self.item("layout")["parent"], "sketch")
        self.assertEqual(self.item("sketch")["project"], "ship")
        self.run_action("move", "sketch", newProject="Later")
        self.assertEqual(self.item(self.item("sketch")["project"])["title"], "Later")

    def test_transfer_project_preserves_descendant_deadlines_and_history(self):
        for key in ("design", "layout"):
            self.run_action("deadline", key, date="2026-12-02", time="23:30", zone="America/Sao_Paulo")
        self.run_action("start", "layout", duration="37m")
        self.run_action("transfer", "design", newProject="Archive")
        h = focus.read_history(self.history)
        self.assertEqual(set(h["deadlines"][focus.source_name(self.note)]), {"layout"})
        self.assertEqual(focus.active_session(h)["task"], "layout")
        view = focus.view(self.note, h, ZoneInfo("Europe/Berlin"), 101)
        self.assertEqual(view["deadlines"]["layout"]["date"], "2026-12-03")
        self.assertEqual(self.item("layout")["depth"], 2)
        self.run_action("toggle", "layout", now=130)
        h = focus.read_history(self.history)
        self.assertIsNone(focus.active_session(h))
        self.assertEqual(h["sessions"][0]["focused_seconds"], 30)
        self.assertFalse(focus.view(self.note, h, None, 130)["deadlines"])
        self.run_action("toggle", "layout")
        self.assertIn("layout", focus.view(self.note, h, None, 130)["deadlines"])

    def test_delete_detects_added_descendant_and_keeps_time_after_recovery(self):
        self.run_action("start", "layout", duration="1m")
        self.run_action("deadline", "design", date="2026-11-22", time="")
        old = self.item("design")
        self.run_action("add", "design", title="New decision")
        with self.assertRaisesRegex(ValueError, "nested items"):
            self.run_action("delete", target=old)
        with patch.object(focus, "write_history", side_effect=OSError("disk full")), self.assertRaises(OSError):
            self.run_action("delete", "design", now=125)
        self.assertIn("Keep this paragraph.", self.note.read_text())
        self.run_action("tick", now=500)
        h = focus.read_history(self.history)
        self.assertEqual((h["sessions"][0]["focused_seconds"], h["sessions"][0]["ended_at"]), (25,125))
        self.assertEqual(h["deadlines"][focus.source_name(self.note)], {})

    def test_legacy_collision_and_first_project(self):
        self.note.write_text("Intro")
        self.assertEqual(self.rows(), [])
        self.run_action("project", title="Work")
        self.assertTrue(self.note.read_text().startswith("Intro\n\n## Tasks\n- Work ^"))
        self.note.write_text("## Tasks\n- Work\n  - Same\n  - Same")
        first, second = self.rows()[1:]
        self.assertNotEqual(first.key, second.key)
        self.run_action("delete", target=first.display())
        with self.assertRaises(ValueError):
            self.run_action("delete", target=first.display())
        self.assertTrue(self.note.read_text().endswith("  - Same"))
        self.assertFalse(self.note.read_text().endswith("\n"))

    def test_project_deadline_and_stale_deadline_edit(self):
        self.run_action("deadline", "design", date="2026-12-06", time="", expectedDue=None)
        h = focus.read_history(self.history)
        current = focus.view(self.note, h, None, 120)["deadlines"]["design"]
        with self.assertRaisesRegex(ValueError, "deadline changed"):
            self.run_action("clearDeadline", "design", expectedDue=None)
        self.run_action("clearDeadline", "design", expectedDue=current)
        with self.assertRaises(ValueError):
            self.run_action("start", "design", duration="5m")

    def test_retry_after_creating_task_only_inserts_once(self):
        self.note.write_text("## Tasks\n- Legacy project")
        parent = self.rows()[0].display()
        req = {"title": "Repeated request", "operation": "same-submit", "target": parent}
        first = self.run_action("add", **req)
        second = self.run_action("add", **req)
        self.assertEqual((first["key"], first["parent"]), (second["key"], second["parent"]))
        self.assertEqual(len(self.rows()), 2)

    def test_project_order_preserves_nested_work_and_rejects_stale_drag(self):
        self.run_action("start", "layout", duration="12m")
        self.run_action("deadline", "design", date="2026-12-01")
        history = self.history.read_bytes()
        self.run_action("reorder", "ship", destination=self.item("design"), after=False, order=["design", "ship"])
        self.assertEqual([n.key for n in self.rows()], ["ship", "check", "design", "sketch", "layout"])
        self.assertEqual(self.item("layout")["parent"], "sketch")
        self.assertIn(b"\t  description\r\n\r\n\t\t- Layout ^layout", self.note.read_bytes())
        self.assertIn(b"Keep this paragraph.", self.note.read_bytes())
        self.assertEqual(self.history.read_bytes(), history)
        with self.assertRaisesRegex(ValueError, "order changed"):
            self.run_action("reorder", "design", destination=self.item("ship"), after=False, order=["design", "ship"])
        self.run_action("reorder", "ship", destination=self.item("design"), after=True, order=["ship", "design"])
        self.assertEqual(self.note.read_bytes(), self.initial)

    def test_badge_names_and_clock_date_rollover(self):
        zone = ZoneInfo("Asia/Tokyo")
        midnight = int(datetime(2026, 12, 3, tzinfo=zone).timestamp())
        def urgency(now):
            return focus.view(self.note, focus.read_history(self.history), zone, now)["urgency"]
        self.run_action("deadline", "sketch", date="2026-12-01")
        self.run_action("deadline", "check", date="2026-12-03")
        self.run_action("deadline", "ship", date="2026-12-05")
        hint = urgency(midnight)
        self.assertEqual(hint["level"], "urgent")
        self.assertIn("Overdue\nSketch · Design · 2 days late", hint["text"])
        self.assertIn("Due today\nCheck · Ship", hint["text"])
        self.assertIn("Ship · Project", hint["text"])
        self.run_action("toggle", "sketch")
        self.assertEqual(urgency(midnight - 1)["level"], "soon")
        self.run_action("toggle", "check")
        self.assertEqual(urgency(midnight)["level"], "soon")
        self.assertEqual(urgency(midnight - 1), {"level": "", "text": ""})

    def test_picking_a_day_replaces_only_the_selected_timed_deadline(self):
        for key in ["check", "sketch"]:
            self.run_action("deadline", key, date="2026-12-03", time="23:00", zone="America/Sao_Paulo")
        before = focus.read_history(self.history)["deadlines"][focus.source_name(self.note)]
        self.run_action("deadline", "check", date="2026-12-07")
        after = focus.read_history(self.history)["deadlines"][focus.source_name(self.note)]
        self.assertEqual(after["sketch"], before["sketch"])
        self.assertEqual(after["check"], {"date": "2026-12-07", "title": "Check"})

    def test_external_completion_uses_note_timestamp_after_restart(self):
        self.run_action("start", "sketch", duration="37m")
        session = focus.active_session(focus.read_history(self.history))["id"]
        self.note.write_bytes(self.note.read_bytes().replace(b"Sketch ^sketch", b"[x] Sketch ^sketch"))
        os.utime(self.note, (125, 125))
        self.run_action("syncCompletion", session=session, now=500)
        recorded = focus.read_history(self.history)["sessions"][0]
        self.assertEqual((recorded["status"], recorded["focused_seconds"]), ("finished", 25))

    def test_old_draft_is_recoverable_after_row_edit(self):
        base = panel_tasks.section_body(panel_tasks.read_lines(self.note))[1]
        panel_tasks.notepad(self.note, self.state, {"action": "draft", "base": base, "text": base + "\n- Draft", "cursor": 3})
        self.run_action("rename", "design", title="Studio")
        saved = panel_tasks.notepad(self.note, self.state, {"action": "open"})
        self.assertTrue(saved["text"].endswith("- Draft"))
        self.assertIn("Studio ^design", saved["conflict"])
