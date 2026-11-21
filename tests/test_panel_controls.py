from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import panel_audio as audio
import panel_tasks as tasks


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

    def pad(self, action, **values):
        return tasks.notepad(self.note, self.state, {"action": action, **values})

    def test_notepad_restores_draft_and_updates_only_section(self):
        base = self.pad("open")["text"]
        text = base.replace("Parent", "Revised").replace("Child", "First\n\t\t- Second")
        self.pad("draft", base=base, text=text, cursor=8)
        self.assertEqual((self.pad("open")["text"], self.pad("open")["cursor"]), (text, 8))
        self.note.write_bytes(self.note.read_bytes().replace(b"Intro", b"Changed intro"))
        self.pad("save", base=base, text=text, cursor=8)
        expected = self.original.replace("Intro", "Changed intro").replace("Parent", "Revised").replace("Child", "First\r\n\t\t- Second")
        self.assertEqual(self.note.read_bytes(), expected.encode())
        self.assertFalse(self.pad("open")["draft"])
        self.assertEqual(tasks.status(self.note)["text"], "3")

    def test_notepad_review_rechecks_concurrent_changes(self):
        base = self.pad("open")["text"]
        self.note.write_bytes(self.note.read_bytes().replace(b"Parent", b"External"))
        result = self.pad("save", base=base, text="- My draft", cursor=2)
        self.assertIn("External", result["conflict"])
        self.assertEqual(self.pad("open")["text"], "- My draft")
        self.note.write_bytes(self.note.read_bytes().replace(b"External", b"Newer"))
        result = self.pad("save", base=result["conflict"], text="- My draft", cursor=2)
        self.assertIn("Newer", result["conflict"])
        self.pad("save", base=result["conflict"], text="- Merged", cursor=2)
        self.assertEqual(self.pad("open")["text"], "- Merged")

    def test_notepad_unavailable_and_empty_sections(self):
        self.note.unlink()
        self.assertIsNone(self.pad("open")["base"])
        self.pad("draft", base=None, text="- Offline", cursor=3)
        self.note.write_text("## Tasks\n## Other\nContent")
        self.assertEqual(self.pad("save", base=None, text="- Offline", cursor=3)["conflict"], "")
        self.pad("save", base="", text="- Offline", cursor=3)
        self.assertEqual(self.note.read_text(), "## Tasks\n- Offline\n## Other\nContent")
        self.pad("save", base="- Offline", text="", cursor=0)
        self.assertEqual(self.note.read_text(), "## Tasks\n## Other\nContent")
        with self.assertRaises(ValueError):
            self.pad("save", base="", text="## Outside", cursor=0)
        self.assertEqual(self.pad("open")["text"], "## Outside")

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

    def test_edit_preserves_nested_children_spacing_and_other_edits(self):
        target = tasks.edit_choices(tasks.read_lines(self.note), "Work")[0][1]
        self.note.write_bytes(self.note.read_bytes().replace(b"- Parent", b"-   Parent  ").replace(b"Intro", b"Else"))
        before = self.note.read_bytes()
        tasks.save_task(self.note, "Work", "Revised", target)
        self.assertEqual(self.note.read_bytes(), before.replace(b"Parent", b"Revised"))
        self.assertEqual(tasks.status(self.note)["text"], "2")

    def test_panel_menu_edits_nested_task_using_its_original_target(self):
        add, edit = tasks.task_choices(self.note, self.state)
        self.assertEqual(add["children"][0]["target"], {"action": "add", "project": "Work"})
        work, empty = edit["children"]
        self.assertNotIn("target", empty)
        child = work["children"][1]
        with patch.object(tasks, "notify"), patch.object(tasks, "dialog", return_value="Revised"):
            tasks.capture(self.note, self.state, child["target"])
        self.assertEqual(self.note.read_bytes(), self.original.replace("Child", "Revised").encode())

    def test_duplicate_siblings_and_parent_context(self):
        self.note.write_text("## Tasks\n- Work\n  - A\n    - Duplicate\n  - B\n    - Duplicate\n    - Duplicate\n")
        picks = tasks.edit_choices(tasks.read_lines(self.note), "Work")
        self.assertIn("A › Duplicate", picks[1][0])
        self.assertIn("line 7", picks[-1][0])
        target = picks[-1][1]
        self.note.write_text(self.note.read_text().replace("  - A", "  - Renamed"))
        with self.assertRaises(ValueError):
            tasks.save_task(self.note, "Work", "Unsafe", target)
        target = tasks.edit_choices(tasks.read_lines(self.note), "Work")[-1][1]
        tasks.save_task(self.note, "Work", "Last sibling", target)
        self.assertTrue(self.note.read_text().endswith("    - Duplicate\n    - Last sibling\n"))

    def test_conflict_retains_edit_draft_and_recovers_explicitly(self):
        target = tasks.edit_choices(tasks.read_lines(self.note), "Work")[0][1]
        def rename(*args, **kwargs):
            self.note.write_bytes(self.note.read_bytes().replace(b"Parent", b"Updated elsewhere"))
            self.assertEqual(kwargs["initial"], "Parent")
            return "My revision"
        with patch.object(tasks, "notify"), patch.object(tasks, "dialog", side_effect=rename):
            tasks.capture(self.note, self.state, {"action": "edit", "target": target})
        draft, = self.state.glob("*.edit-*.json")
        self.assertIn(b"Updated elsewhere", self.note.read_bytes())
        with patch.object(tasks, "notify"), patch.object(tasks, "dialog", side_effect=[0, "My revision"]):
            tasks.capture(self.note, self.state, {"action": "resume", "draft": draft.name})
        self.assertIn(b"My revision", self.note.read_bytes())
        self.assertFalse(draft.exists())
        self.assertEqual(tasks.status(self.note)["text"], "2")


class AudioTests(unittest.TestCase):
    def test_menu_identifies_the_selected_output_and_missing_microphone(self):
        route = audio.Route("sink", "device_1", "speaker", "Speakers", True)
        with patch.object(audio, "available", side_effect=[[route], []]), patch.object(audio, "pactl", return_value="[]"):
            rows = audio.audio_choices()
        expected = {"action": "route", "kind": "sink", "device": "device_1", "port": "speaker"}
        self.assertEqual(rows, [{"heading": "Output"}, {"label": "Speakers", "current": True, "target": expected},
                                {"heading": "Microphone"}, {"label": "No active devices"}])

    def test_plugged_headphones_leave_laptop_speakers_selectable(self):
        speaker, phones = "analog-output-speaker", "analog-output-headphones"
        device = {"name": "analog", "description": "Laptop", "active_port": phones,
                  "ports": [{"name": speaker, "description": "Speakers", "availability": "not available"},
                            {"name": phones, "description": "Headphones", "availability": "available"},
                            {"name": "hdmi-output-0", "description": "HDMI", "availability": "not available"}]}
        for selected in (phones, speaker):
            device["active_port"] = selected
            routes = audio.routes("sink", [device], "analog")
            self.assertEqual([r.port for r in routes], [speaker, phones])
            self.assertEqual([r.port for r in routes if r.current], [selected])
        device["ports"][0]["availability"] = "availability unknown"
        device["ports"][1]["availability"] = "not available"
        self.assertEqual([r.port for r in audio.routes("sink", [device], "analog")], [speaker])

    def test_hardware_ports_and_monitor_filter(self):
        device = {"name": "analog", "description": "Laptop", "active_port": "mic",
                  "ports": [{"name": "mic", "description": "Internal mic", "availability": "availability unknown"},
                            {"name": "jack", "description": "Jack", "availability": "not available"}]}
        buds = {"name": "bluetooth", "description": "Galaxy Buds", "ports": []}
        results = audio.routes("source", [device, {**device, "name": "sink.monitor"}, buds], "analog")
        self.assertEqual([(r.device, r.current) for r in results], [("analog", True), ("bluetooth", False)])

    def test_select_by_stable_name_and_confirm_actual_port(self):
        old = audio.Route("source", "input", "mic", "Microphone", False)
        new = audio.Route("source", "input", "mic", "Microphone", True)
        with patch.object(audio, "available", side_effect=[[old], [old], [new]]), \
                patch.object(audio, "pactl") as pactl:
            audio.select_route("source", "input", "mic")
            self.assertEqual([c.args for c in pactl.call_args_list],
                             [("set-source-port", "input", "mic"), ("set-default-source", "input")])
        with patch.object(audio, "available", return_value=[]), patch.object(audio, "pactl") as pactl:
            with self.assertRaises(ValueError):
                audio.select_route("source", "input", "mic")
            pactl.assert_not_called()

    def test_bluetooth_profile_requires_capture_and_confirmation(self):
        card = {"name": "bluez_card.AB", "active_profile": "a2dp",
                "profiles": {"a2dp": {"sources": 0}, "voice": {"sources": 1, "available": True},
                             "unavailable": {"sources": 1, "available": False, "priority": 99}}}
        self.assertEqual(list(audio.headset_profiles([card])), [(card, "voice")])
        with patch.object(audio, "pactl", return_value=json.dumps([card])) as pactl, \
                patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 1)):
            audio.switch_headset({"card": card["name"], "profile": "voice"})
            pactl.assert_called_once_with("-f", "json", "list", "cards")

    def test_headset_waits_for_its_own_microphone_and_restores_on_failure(self):
        for expose_mic in (True, False):
            card = {"name": "bluez_card.test", "index": 51, "active_profile": "music",
                    "profiles": {"music": {"sources": 0}, "voice": {"sources": 1}}}
            def server(*args):
                if args[-1] == "cards":
                    return json.dumps([card])
                if args[-1] == "sources":
                    sources = [{"name": "built-in", "properties": {"device.id": "99"}}]
                    if expose_mic:
                        sources.append({"name": "headset", "properties": {"device.id": "51"}})
                    return json.dumps(sources)
                self.assertEqual(args[:2], ("set-card-profile", card["name"]))
                card["active_profile"] = args[-1]
                return ""
            with patch.object(audio, "pactl", side_effect=server), patch.object(audio, "select_route") as select, \
                    patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), \
                    patch.object(audio.time, "sleep"):
                action = {"card": card["name"], "profile": "voice"}
                if expose_mic:
                    audio.switch_headset(action)
                    select.assert_called_once_with("source", "headset", "")
                else:
                    with self.assertRaises(ValueError):
                        audio.switch_headset(action)
                    self.assertEqual(card["active_profile"], "music")
                    select.assert_not_called()

    def test_mic_feedback_reports_result(self):
        for state, label in [("yes", "Microphone muted"), ("no", "Microphone on")]:
            with patch.object(audio, "pactl", side_effect=["source", "", "Mute: " + state]), \
                    patch.object(subprocess, "run") as run:
                audio.mic_mute()
                self.assertEqual(run.call_args.args[0][-1], label)
