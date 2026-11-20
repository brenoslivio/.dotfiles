from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import weekly_update as w

FRIDAY = datetime(2026, 11, 20, 21, tzinfo=w.ZONE)
PR = {"number": 42, "head": {"sha": "a" * 40}}
RUN = {"id": 11, "run_attempt": 2, "status": "completed", "conclusion": "success"}
READY = w.Notice("pr:42:abc:ready", "Friday update is ready for review", "PR #42 · Package checks passed.",
                 "Open pull request", f"{w.WEB}/pull/42")
ACTIVE = w.Notice("abc:active", "Friday check complete", "Your laptop is up to date.")
AVAILABLE = w.Notice("abc:available; run up to review", "NixOS update ready", "Run up to review it.")


class WeeklyMonitorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)
        self.show = self.mock("show")
        self.workflow = self.mock("scheduled_workflow", return_value=RUN)
        self.proposal = self.mock("proposal_status", return_value=w.Proposal("waiting"))
        self.system = self.mock("tested_system", return_value=ACTIVE)

    def mock(self, name, **kwargs):
        obj = patch.object(w, name, **kwargs)
        self.addCleanup(obj.stop)
        return obj.start()

    def tick(self, minutes=0):
        w.monitor(self.directory, FRIDAY + timedelta(minutes=minutes))

    def test_start_weekend_wakeup_and_cutoff(self):
        self.tick(-1440)
        self.tick(-1)
        self.workflow.assert_not_called()
        self.tick(600)
        self.workflow.assert_called_once_with(FRIDAY)
        self.tick(48 * 60)
        self.tick(49 * 60)
        self.show.assert_called_once()
        self.assertEqual(self.show.call_args.args[0].key, "cutoff")

    def test_pending_then_approval_failure_recovery_and_dismissal(self):
        self.tick()
        for status in ("approval", "failed", "ready"):
            notice = w.Notice(f"pr:42:abc:{status}", status, status, READY.button, READY.url)
            self.proposal.return_value = w.Proposal(status, notice, 42)
            self.tick(5)
            self.tick(10)
        self.tick(48 * 60)
        self.assertEqual([c.args[0].title for c in self.show.call_args_list], ["approval", "failed", "ready"])
        self.assertEqual(self.show.call_args.args[0].url, READY.url)

    def test_separate_install_with_open_pr_and_no_daily_repeat(self):
        self.proposal.return_value = w.Proposal("ready", READY, 42)
        self.system.return_value = AVAILABLE
        self.tick()
        self.tick(5)
        notice = self.show.call_args.args[0]
        self.assertIn(AVAILABLE.body, notice.body)
        self.assertEqual(notice.url, READY.url)
        self.assertEqual(w.update.read_state(self.directory)["notified"], AVAILABLE.key)
        self.proposal.return_value = w.Proposal("merged", number=42)
        self.tick(10)
        self.show.assert_called_once()
        self.assertTrue(w.update.read_state(self.directory)["friday"]["done"])

    def test_merge_pending_then_ready_and_daily_deduplication(self):
        self.proposal.return_value = w.Proposal("merged", number=42)
        self.system.side_effect = [w.update.UpdateError("CI pending"), AVAILABLE]
        self.tick()
        self.show.assert_not_called()
        self.tick(5)
        self.tick(10)
        self.show.assert_called_once()
        with patch.object(w.update, "api_json", return_value={"object": {"sha": "abc"}}), \
                patch.object(w.update, "evidence", return_value={"system_path": "/tested"}), \
                patch.object(w.update, "system_status", return_value={}), patch.object(w.update, "run") as send:
            w.update.notify(self.directory)
            send.assert_not_called()

    def test_delivery_failure_retries_and_quiet_week_finishes_once(self):
        self.proposal.return_value = w.Proposal("unchanged")
        self.show.side_effect = [OSError("no desktop"), None]
        with self.assertRaises(OSError):
            self.tick()
        self.tick(5)
        self.tick(10)
        self.assertIn("No dependency changes", self.show.call_args.args[0].body)
        self.assertEqual(self.show.call_count, 2)

    def test_weekend_daily_delivery_suppresses_duplicate_install_report(self):
        self.proposal.return_value = w.Proposal("merged", number=42)
        self.system.return_value = AVAILABLE
        w.update.atomic_json(self.directory / "state.json", {
            "notified": AVAILABLE.key, "daily_notice": {"key": AVAILABLE.key, "at": FRIDAY.timestamp() + 3600},
        })
        self.tick(65)
        self.show.assert_not_called()
        self.assertTrue(w.update.read_state(self.directory)["friday"]["done"])

    def test_offline_and_weekend_missed_cutoff(self):
        self.workflow.side_effect = subprocess.CalledProcessError(1, "gh")
        with self.assertRaises(subprocess.CalledProcessError):
            self.tick()
        self.show.assert_not_called()
        self.tick(3 * 24 * 60)
        self.assertEqual(self.show.call_args.args[0].key, "cutoff")

    def test_failed_proposal_workflow_has_exact_url_and_can_recover(self):
        self.workflow.return_value = {**RUN, "conclusion": "failure"}
        self.proposal.return_value = w.Proposal("workflow-failed")
        self.tick()
        self.tick(5)
        self.assertEqual(self.show.call_args.args[0].url, f"{w.WEB}/actions/runs/11")
        self.workflow.return_value = RUN
        self.proposal.return_value = w.Proposal("unchanged")
        self.tick(10)
        self.assertEqual(self.show.call_count, 2)


class GitHubResultsTests(unittest.TestCase):
    def test_only_exact_proposal_ci_with_passing_required_jobs_is_ready(self):
        jobs = [{"name": name, "status": "completed", "conclusion": "success"} for name in w.update.REQUIRED_JOBS]
        with patch.object(w, "latest_run", return_value=RUN) as runs, patch.object(w.update, "pages", return_value=jobs):
            result = w.open_proposal(PR)
            runs.assert_called_once_with("ci.yml", event="pull_request", head_sha=PR["head"]["sha"], branch=w.BRANCH)
            self.assertEqual(result.status, "ready")
            self.assertEqual(result.notice.url, f"{w.WEB}/pull/42")
            jobs.pop()
            self.assertEqual(w.open_proposal(PR).status, "failed")

    def test_approval_requires_positive_evidence(self):
        with patch.object(w, "latest_run", return_value=None), patch.object(w.update, "pages", return_value=[]) as suites:
            self.assertEqual(w.open_proposal(PR).status, "pending")
            suites.return_value = [{"app": {"slug": "github-actions"}, "conclusion": "action_required"}]
            self.assertEqual(w.open_proposal(PR).status, "approval")

    def test_older_open_proposal_and_already_merged_proposal(self):
        with patch.object(w.update, "api_json", return_value=[PR]), patch.object(w, "open_proposal") as check:
            w.proposal_status(FRIDAY, None)
            check.assert_called_once_with(PR)
        merged = {**PR, "merged_at": "2026-11-20T19:00:00Z", "closed_at": "2026-11-20T19:00:00Z",
                  "merge_commit_sha": "b" * 40}
        with patch.object(w.update, "api_json", side_effect=[[], [merged], [], [], []]):
            self.assertEqual(w.proposal_status(FRIDAY, RUN).merge_sha, merged["merge_commit_sha"])
            self.assertEqual(w.proposal_status(FRIDAY, RUN).status, "unchanged")
            self.assertEqual(w.proposal_status(FRIDAY, None).status, "waiting")

    def test_main_must_contain_merge_before_evidence_is_accepted(self):
        proposal = w.Proposal("merged", number=42, merge_sha="b" * 40)
        with patch.object(w.update, "api_json", side_effect=[{"object": {"sha": "a" * 40}}, {"status": "behind"}]), \
                patch.object(w.update, "evidence") as evidence:
            with self.assertRaises(w.update.UpdateError):
                w.tested_system(proposal, {})
            evidence.assert_not_called()
