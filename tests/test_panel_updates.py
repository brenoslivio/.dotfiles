from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import panel_updates as w
import update

SHA = "a" * 40
PR = {"head": {"sha": SHA}, "number": 16}
RUN = {"id": 33, "run_attempt": 1, "conclusion": "success", "status": "completed"}
JOBS = [{"name": name, "conclusion": "success", "status": "completed"} for name in update.REQUIRED_JOBS]
MANIFEST = {"run_id": "33", "run_attempt": "1", "system_path": "/tested", "expires_at": "2099-12-01T00:00:00Z"}


class IndicatorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state = Path(tmp.name)
        for name, path in (("STATE", state), ("RUNTIME", state / "run"), ("CACHE", state / "cache")):
            self.enterContext(patch.object(w, name, path))

    def test_pr_filter_and_required_jobs(self):
        with patch.object(update, "api_json", return_value=[PR]) as api, patch.object(w, "latest", return_value=RUN), \
                patch.object(update, "pages", return_value=JOBS) as jobs:
            ready = w.proposal({})
            self.assertTrue(ready["attention"])
            self.assertIn("ready for review", ready["text"])
            self.assertEqual(api.call_args.kwargs["head"], "brenoslivio:automation/flake-update")
            self.assertEqual(w.proposal(ready), ready)
            jobs.assert_called_once()
            jobs.return_value = JOBS[1:]
            self.assertIn("failed", w.proposal({})["text"])

    def test_pr_pending_and_approval(self):
        with patch.object(update, "api_json", return_value=[PR]), patch.object(w, "latest", return_value=None), \
                patch.object(update, "pages", return_value=[]) as suites:
            self.assertFalse(w.proposal({})["attention"])
            suites.return_value = [{"app": {"slug": "github-actions"}, "conclusion": "action_required"}]
            self.assertTrue(w.proposal({})["attention"])

    def test_failed_proposal_without_pr_links_to_actions(self):
        with patch.object(update, "api_json", return_value=[]), patch.object(w, "latest", return_value={**RUN, "conclusion": "failure"}):
            proposal = w.proposal({})
            self.assertTrue(proposal["attention"])
            self.assertEqual(w.links({"proposal": proposal}), {"View proposal CI run": w.WEB + "/actions/runs/33"})

    def test_verified_attempt_cached_but_local_activation_rechecked(self):
        with patch.object(update, "api_json", return_value={"object": {"sha": SHA}}), \
                patch.object(w, "latest", return_value=RUN) as latest, \
                patch.object(update, "evidence", return_value=MANIFEST) as evidence, \
                patch.object(update, "system_status", return_value={}) as local:
            available = w.system({})
            self.assertTrue(available["attention"])
            local.return_value = {"boot_default": "/tested"}
            self.assertIn("next boot", w.system(available)["text"])
            local.return_value = {"active": "/tested"}
            self.assertFalse(w.system(available)["attention"])
            evidence.assert_called_once_with(SHA)
            latest.return_value = {**RUN, "run_attempt": 2, "conclusion": None, "status": "in_progress"}
            self.assertIn("running", w.system(available)["text"])
            latest.return_value = {**RUN, "run_attempt": 2}
            evidence.return_value = {**MANIFEST, "run_attempt": "2"}
            w.system(available)
            self.assertEqual(evidence.call_count, 2)
            w.system({**available, "expires": 0})
            self.assertEqual(evidence.call_count, 3)

    def test_offline_preserves_badge_and_last_check_then_recovers(self):
        update.atomic_json(w.CACHE, {"checked": 42, "proposal": {"attention": True}})
        with patch.object(w, "proposal", side_effect=OSError("offline")), patch.object(w, "system", return_value={}):
            w.main(["check"])
            w.main(["finish"])
        data = w.cached()
        self.assertEqual(data["checked"], 42)
        self.assertTrue(data["error"])
        self.assertIn("attention", w.view(data, False, False)["class"])
        with patch.object(w, "proposal", return_value={}), patch.object(w, "system", return_value={}):
            w.main(["check"])
        self.assertFalse(w.cached()["error"])
        self.assertGreater(w.cached()["checked"], 42)

    def test_backoff_obeys_github_headers_across_clicks(self):
        r = subprocess.CompletedProcess([], 1, b"HTTP/2.0 403 Forbidden\nX-RateLimit-Remaining: 0\r\nX-RateLimit-Reset: 9999999999\r\n\r\n{}", b"API rate limit")
        with patch.object(subprocess, "run", return_value=r) as api:
            for _ in range(2):
                w.main(["check"])
                w.main(["finish"])
            api.assert_called_once()
        self.assertEqual(w.cached()["retry_after"], 9999999999)

    def test_manual_feedback_promotes_running_check_and_finish_clears(self):
        w.RUNTIME.mkdir()
        (w.RUNTIME / "checking").touch()
        with patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as start:
            w.main(["manual"])
            self.assertTrue((w.RUNTIME / "manual").exists())
            start.assert_called_once_with(["systemctl", "--user", "start", "--no-block", w.UNIT])
        for manual, expected in [(True, "manual"), (False, "checking")]:
            self.assertEqual(w.view({"system": {"attention": True}}, True, manual)["class"], [expected, "attention"])
        with patch.dict(w.os.environ, SERVICE_RESULT="timeout"):
            w.main(["finish"])
        self.assertFalse(list(w.RUNTIME.iterdir()))
        self.assertIn("interrupted", w.cached()["error"])

    def test_unrelated_or_stale_menu_target_is_ignored(self):
        update.atomic_json(w.CACHE, {"proposal": {"pr": 16}})
        with patch.object(subprocess, "Popen") as op:
            for url in (w.WEB + "/pull/15", "https://example.invalid/", w.WEB + "/pull/16"):
                w.main(["apply", json.dumps(url)])
            op.assert_called_once_with(["xdg-open", w.WEB + "/pull/16"])


if __name__ == "__main__":
    unittest.main()
