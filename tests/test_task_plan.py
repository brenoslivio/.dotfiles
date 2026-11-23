from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import task_focus as focus


class DailyPlanTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.history = root / "task-history.json"
        self.plan = root / "task-plan.json"
        self.state = root / "state"
        self.note = root / "work.md"
        self.note.write_text("## Tasks\n- Work ^work\n  - Read\n  - Draft ^draft\n"
                             "  - Review ^review\n- Home ^home\n  - File ^file\n")
        self.now = datetime(2026, 11, 20, 23, 59, 50)

    def view(self):
        return focus.view(self.note, focus.read_history(self.history), ZoneInfo("Pacific/Kiritimati"),
                          int(self.now.timestamp()), self.plan)

    def act(self, action, target_key=None, **extra):
        req = {"action": action, "day": self.now.date().isoformat(), **extra}
        if target_key is not None:
            req["target"] = next(n for n in self.view()["items"] if n["key"] == target_key)
        return focus.apply(self.note, self.state, self.history, req, int(self.now.timestamp()))

    def test_identity_deadline_order_completion_and_midnight_focus(self):
        ref = next(n for n in self.view()["items"] if n["title"] == "Read")
        anchored = self.act("planAdd", target=ref)["key"]
        self.assertIn("^" + anchored, self.note.read_text())
        self.act("planAdd", anchored)
        self.act("planAdd", "draft")
        self.act("deadline", anchored, date="2026-11-21")
        self.act("move", anchored, destination=self.view()["items"][-2])
        self.act("rename", anchored, title="Read proofs")
        note = self.note.read_bytes()
        self.act("planOrder", before=[anchored, "draft"], order=["draft", anchored])
        self.assertEqual(note, self.note.read_bytes())
        self.assertEqual(self.view()["plan"]["tasks"], ["draft", anchored])
        self.assertEqual(self.view()["deadlines"][anchored]["title"], "Read proofs")
        self.act("start", anchored, duration="37m")
        self.now += timedelta(seconds=20)
        view = self.view()
        self.assertEqual(view["plan"], {"tasks": [], "carry": ["draft", anchored]})
        self.assertEqual(view["active"]["task"], anchored)
        self.act("planCarry", keys=[anchored])
        self.act("toggle", anchored)
        self.assertEqual(self.view()["plan"], {"tasks": [anchored], "carry": ["draft"]})
        self.assertIsNone(self.view()["active"])
        self.assertEqual(self.view()["todaySeconds"], 10)
        self.assertEqual(self.view()["totals"][anchored], 20)
        self.act("toggle", anchored)
        self.assertFalse(next(n for n in self.view()["items"] if n["key"] == anchored)["done"])

    def test_carry_across_skipped_days_dismiss_remove_replan_and_deleted_tasks(self):
        for k in ["review", "file", "draft"]:
            self.act("planAdd", k)
        self.now += timedelta(days=4)
        self.act("planDismiss", keys=["file"])
        self.act("planCarry", keys=["draft", "review", "file"])
        self.assertEqual(self.view()["plan"], {"tasks": ["review", "draft"], "carry": []})
        self.act("planRemove", key="draft")
        self.now += timedelta(days=2)
        self.assertEqual(self.view()["plan"], {"tasks": [], "carry": ["review"]})
        self.act("planAdd", "file")
        self.act("delete", "review")
        self.now += timedelta(days=1)
        self.assertEqual(self.view()["plan"]["carry"], ["file"])

    def test_source_isolation_stale_changes_and_invalid_plan(self):
        day = self.now.date().isoformat()
        self.act("planAdd", "draft")
        with self.assertRaisesRegex(ValueError, "plan changed"):
            self.act("planOrder", before=[], order=[])
        self.act("toggle", "draft")
        with self.assertRaisesRegex(ValueError, "open task"):
            self.act("planAdd", "draft")
        with self.assertRaisesRegex(ValueError, "open task"):
            self.act("planAdd", "work")
        other = self.note.with_name("other.md")
        other.write_text(self.note.read_text())
        self.note = other
        self.assertFalse(self.view()["plan"]["tasks"])
        self.act("planAdd", "review")
        self.now += timedelta(days=2)
        self.assertEqual(self.view()["plan"]["carry"], ["review"])
        with self.assertRaisesRegex(ValueError, "new day"):
            self.act("planCarry", day=day, keys=["review"])
        self.plan.write_text("broken")
        self.assertIn("task-plan.json", self.view()["plan"]["error"])
        self.assertTrue(self.view()["items"])
        with self.assertRaises(ValueError):
            self.act("planAdd", "review")
        self.assertEqual(self.plan.read_text(), "broken")
