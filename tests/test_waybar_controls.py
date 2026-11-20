from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import waybar_audio as audio
import waybar_tasks as tasks


class TaskTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.note = self.root / "note.md"
        self.state = self.root / "drafts"
        self.original = "Intro\r\n## Tasks\r\n- Work\r\n\t- Parent\r\n\t\t- Child\r\n\r\n- Home\r\n\r\n## More\r\n- Elsewhere"
        self.note.write_bytes(self.original.encode())
        self.note.chmod(0o640)

    def test_preserves_format_metadata_and_symlink(self):
        link = self.root / "link"
        link.symlink_to(self.note)
        tasks.save_task(link, "Work", "Buy <x> & y")
        self.assertEqual(self.note.read_bytes(), self.original.replace("Child\r\n", "Child\r\n\t- Buy <x> & y\r\n").encode())
        self.assertTrue(link.is_symlink())
        self.assertEqual(self.note.stat().st_mode & 0o777, 0o640)
        self.assertEqual(tasks.status(link)["text"], "3")
        self.assertIn("Buy &lt;x&gt; &amp; y", tasks.status(link)["tooltip"])

    def test_concurrent_change_during_commit_is_retained(self):
        copystat = tasks.shutil.copystat
        def edit(*args):
            if self.note.read_bytes().startswith(b"Intro"):
                self.note.write_bytes(self.note.read_bytes().replace(b"Intro", b"New intro"))
            return copystat(*args)
        with patch.object(tasks.shutil, "copystat", side_effect=edit):
            tasks.save_task(self.note, "Home", "New task")
        self.assertTrue(self.note.read_bytes().startswith(b"New intro"))
        self.assertIn(b"- Home\r\n\t- New task\r\n\r\n## More", self.note.read_bytes())

    def test_empty_project_and_missing_final_newline(self):
        self.note.write_text("## Tasks\n- Home")
        tasks.save_task(self.note, "Home", "One")
        self.assertEqual(self.note.read_text(), "## Tasks\n- Home\n  - One")

    def test_duplicate_or_removed_project_preserves_original(self):
        for projects in ["- Other", "- Work\n- Work"]:
            original = "## Tasks\n" + projects
            self.note.write_text(original)
            with self.assertRaises(ValueError):
                tasks.save_task(self.note, "Work", "test")
            self.assertEqual(self.note.read_text(), original)

    def test_offline_draft_restored_and_cleared_after_save(self):
        self.note.unlink()
        with patch.object(tasks, "notify"), patch.object(tasks, "dialog", return_value="Keep me"):
            tasks.capture(self.note, self.state)
        self.assertEqual(len(list(self.state.glob("*.json"))), 1)
        self.note.write_text("## Tasks\n- Work\n")
        with patch.object(tasks, "notify"), patch.object(tasks, "dialog", side_effect=[0, "Keep me"]) as dialog:
            tasks.capture(self.note, self.state)
            self.assertEqual(dialog.call_args.kwargs["initial"], "Keep me")
        self.assertEqual(list(self.state.glob("*.json")), [])
        self.assertEqual(self.note.read_text(), "## Tasks\n- Work\n  - Keep me\n")

    def test_cancel_does_not_write(self):
        with patch.object(tasks, "dialog", side_effect=[0, None]):
            tasks.capture(self.note, self.state)
        self.assertEqual(self.note.read_bytes(), self.original.encode())
        self.assertFalse(list(self.state.glob("*.json")))


class AudioTests(unittest.TestCase):
    def test_hardware_ports_and_monitor_filter(self):
        device = {"name": "analog", "description": "Laptop", "active_port": "mic",
                  "ports": [{"name": "mic", "description": "Internal mic", "availability": "availability unknown"},
                            {"name": "jack", "description": "Jack", "availability": "not available"}]}
        buds = {"name": "bluetooth", "description": "Galaxy Buds", "ports": []}
        results = audio.routes("source", [device, {**device, "name": "sink.monitor"}, buds], "analog")
        self.assertEqual([(r.device, r.current) for r in results], [("analog", True), ("bluetooth", False)])

    def test_select_by_stable_name_and_handle_disconnect(self):
        route = audio.Route("sink", "stable-output", "speaker", "Speakers", False)
        for connected in (True, False):
            with patch.object(audio, "available", side_effect=[[route], [], [route] if connected else []]), \
                    patch.object(audio, "dialog", return_value=1), patch.object(audio, "notify") as notify, \
                    patch.object(audio, "pactl") as pactl:
                audio.picker()
                if connected:
                    self.assertEqual([call.args for call in pactl.call_args_list],
                                     [("set-sink-port", "stable-output", "speaker"), ("set-default-sink", "stable-output")])
                else:
                    pactl.assert_not_called()
                    notify.assert_called_once()

    def test_mic_feedback_reports_result(self):
        for state, label in [("yes", "Microphone muted"), ("no", "Microphone on")]:
            with patch.object(audio, "pactl", side_effect=["source", "", "Mute: " + state]), \
                    patch.object(subprocess, "run") as run:
                audio.mic_mute()
                self.assertEqual(run.call_args.args[0][-1], label)
