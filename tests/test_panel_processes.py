from pathlib import Path
import signal
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import panel_resources as resources


class ForceQuitTests(unittest.TestCase):
    def test_frozen_group_excludes_later_members_and_refuses_stale_identities(self):
        with subprocess.Popen(["sleep", "60"]) as first, subprocess.Popen(["sleep", "60"]) as second:
            try:
                (pid, start), name, _, _ = resources.process_info(Path("/proc") / str(first.pid))
                self.assertEqual(resources.force_quit(name, [(pid, start - 1)]), {"gone": 1})
                self.assertEqual(resources.force_quit("wrong name", [(pid, start)]), {"gone": 1})
                self.assertEqual(resources.force_quit(name, [(pid, start)]), {"signalled": 1})
                self.assertEqual(first.wait(timeout=2), -signal.SIGKILL)
                self.assertIsNone(second.poll())
                (pid2, start2), _, _, _ = resources.process_info(Path("/proc") / str(second.pid))
                self.assertEqual(resources.force_quit(name, [(pid, start), (pid2, start2)]), {"gone": 1, "signalled": 1})
                self.assertEqual(second.wait(timeout=2), -signal.SIGKILL)
            finally:
                first.kill()
                second.kill()
