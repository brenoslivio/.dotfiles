import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("update", Path(__file__).resolve().parents[1] / "scripts/update.py")
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)
SHA = "a" * 40
SYSTEM = "/nix/store/" + "a" * 32 + "-nixos-system-ahimsa"
HOME = "/nix/store/" + "b" * 32 + "-home-manager-generation"
RUN = {"id": 21, "run_attempt": 2, "workflow_id": 10, "path": ".github/workflows/ci.yml",
       "head_sha": SHA, "head_branch": "main", "event": "push", "status": "completed",
       "conclusion": "success", "repository": {"full_name": u.REPOSITORY},
       "head_repository": {"full_name": u.REPOSITORY}}
MANIFEST = {"schema": 1, "repository": u.REPOSITORY, "sha": SHA, "host": "ahimsa",
            "system": "x86_64-linux", "user": "brenoslivio", "event": "push",
            "run_id": "21", "run_attempt": "2", "system_path": SYSTEM, "home_path": HOME}


class VerificationTests(unittest.TestCase):
    def test_exact_run_passes(self):
        u.validate_run({"id": 10}, RUN, SHA)
        u.validate_manifest(MANIFEST, SHA, RUN)

    def test_untrusted_or_incomplete_runs_rejected(self):
        for key, value in [("workflow_id", 11), ("path", ".github/workflows/other.yml"),
                           ("head_sha", "b" * 40), ("event", "pull_request"),
                           ("event", "workflow_dispatch"), ("head_branch", "proposal"),
                           ("status", "in_progress"), ("conclusion", "failure"),
                           ("conclusion", "cancelled"), ("repository", {"full_name": "other/repo"})]:
            with self.subTest(key=key, value=value), self.assertRaises(u.UpdateError):
                u.validate_run({"id": 10}, {**RUN, key: value}, SHA)

    def test_wrong_manifest_rejected(self):
        for key, value in [("sha", "b" * 40), ("host", "other"), ("run_attempt", "1"),
                           ("run_id", "20"), ("system_path", "/tmp/evil"),
                           ("home_path", SYSTEM + "/activate"), ("user", "root")]:
            with self.subTest(key=key), self.assertRaises(u.UpdateError):
                u.validate_manifest({**MANIFEST, key: value}, SHA, RUN)

    def test_all_jobs_must_run_and_succeed(self):
        jobs = [{"name": name, "status": "completed", "conclusion": "success"} for name in u.REQUIRED_JOBS]
        u.validate_jobs(jobs)
        for conclusion in ("skipped", "neutral", "cancelled", "failure", None):
            with self.subTest(conclusion=conclusion), self.assertRaises(u.UpdateError):
                u.validate_jobs([{**jobs[0], "conclusion": conclusion}, jobs[1]])
        for invalid in (jobs[:1], jobs + [jobs[0]], []):
            with self.assertRaises(u.UpdateError):
                u.validate_jobs(invalid)

    def test_missing_ci_rejected(self):
        with patch.object(u, "api_json", return_value={"id": 10}), patch.object(u, "pages", return_value=[]):
            with self.assertRaises(u.UpdateError):
                u.evidence(SHA)

    def test_latest_pending_run_blocks_older_success(self):
        candidates = [RUN, {**RUN, "id": 22, "status": "in_progress", "conclusion": None}]
        with patch.object(u, "api_json", return_value={"id": 10}), patch.object(u, "pages", return_value=candidates):
            with self.assertRaises(u.UpdateError):
                u.evidence(SHA)

    def test_expired_artifact_rejected(self):
        jobs = [{"name": name, "status": "completed", "conclusion": "success"} for name in u.REQUIRED_JOBS]
        artifacts = [{"name": f"ahimsa-{SHA}-2", "expired": True}]
        with patch.object(u, "api_json", return_value={"id": 10}), patch.object(u, "pages", side_effect=[[RUN], jobs, artifacts]):
            with self.assertRaises(u.UpdateError):
                u.evidence(SHA)

    def test_build_path_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(u, "run", return_value=json.dumps([{"outputs": {"out": HOME}}])) as command:
            with self.assertRaises(u.UpdateError):
                u.build_candidate(Path(tmp), SHA, MANIFEST, Path(tmp), False)
            args = command.call_args.args
            self.assertIn("--no-update-lock-file", args)
            self.assertIn(f"git+file://{tmp}?rev={SHA}#nixosConfigurations.ahimsa.config.system.build.toplevel", args)


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "initial")
        self.git("remote", "add", "origin", f"https://github.com/{u.REPOSITORY}.git")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True, stderr=subprocess.DEVNULL)

    def test_clean_checkout_accepted(self):
        u.clean_checkout(self.repo)

    def test_untracked_file_rejected(self):
        (self.repo / "local.txt").write_text("work")
        with self.assertRaises(u.UpdateError):
            u.clean_checkout(self.repo)

    def test_wrong_branch_rejected(self):
        self.git("switch", "-c", "work")
        with self.assertRaises(u.UpdateError):
            u.clean_checkout(self.repo)

    def test_wrong_origin_rejected(self):
        self.git("remote", "set-url", "origin", "https://github.com/other/repo.git")
        with self.assertRaises(u.UpdateError):
            u.clean_checkout(self.repo)

    def test_unfinished_operation_rejected(self):
        (self.repo / ".git/MERGE_HEAD").write_text(self.git("rev-parse", "HEAD"))
        with self.assertRaises(u.UpdateError):
            u.clean_checkout(self.repo)


class ActivationTests(unittest.TestCase):
    def perform(self, choice, *, home=False, fail=False, prior=None, active=None, boot="old"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        if prior:
            u.atomic_json(directory / "state.json", prior)
        commands = []
        def command(*args, **kwargs):
            commands.append(args)
            if fail and "nixos-rebuild" in args:
                raise subprocess.CalledProcessError(1, args)
            return ""
        def git(repo, *args):
            return SHA if args[0] == "rev-parse" else ""
        with patch.object(u, "clean_checkout"), patch.object(u, "git", side_effect=git), \
                patch.object(u, "evidence", return_value={**MANIFEST, "ci_url": "https://example.invalid/ci"}), \
                patch.object(u, "build_candidate", return_value=HOME if home else SYSTEM), \
                patch.object(u, "system_status", return_value={"active": active, "boot_default": boot, "known_good": "protected"}), \
                patch.object(u, "activation_choice", return_value=choice), patch.object(u, "run", side_effect=command):
            if fail:
                with self.assertRaises(subprocess.CalledProcessError):
                    u.update(directory, directory, home)
            else:
                u.update(directory, directory, home)
        return commands, u.read_state(directory)

    def test_later_preserves_boot_default_and_pending_candidate(self):
        commands, state = self.perform("later")
        self.assertFalse(any("nixos-rebuild" in args for args in commands))
        self.assertEqual(state["pending_system"]["sha"], SHA)

    def test_repeat_after_later_still_offers_activation(self):
        _, prior = self.perform("later")
        commands, state = self.perform("boot", prior=prior)
        self.assertIn(("sudo", "nixos-rebuild", "boot", "--store-path", SYSTEM), commands)
        self.assertEqual(state["last_system_action"]["choice"], "boot")

    def test_switch_uses_built_store_path(self):
        commands, state = self.perform("switch")
        self.assertIn(("sudo", "nixos-rebuild", "switch", "--store-path", SYSTEM), commands)
        self.assertNotIn("activation_intent", state)

    def test_failed_activation_retains_intent(self):
        _, state = self.perform("switch", fail=True)
        self.assertEqual(state["activation_intent"]["path"], SYSTEM)
        self.assertNotIn("last_system_action", state)

    def test_partial_activation_is_retried_even_if_system_links_changed(self):
        _, prior = self.perform("switch", fail=True)
        commands, state = self.perform("switch", prior=prior, active=SYSTEM, boot=SYSTEM)
        self.assertIn(("sudo", "nixos-rebuild", "switch", "--store-path", SYSTEM), commands)
        self.assertNotIn("activation_intent", state)

    def test_already_active_system_needs_no_activation(self):
        commands, _ = self.perform("switch", active=SYSTEM, boot=SYSTEM)
        self.assertFalse(any("nixos-rebuild" in args for args in commands))

    def test_home_activation_is_separate(self):
        commands, state = self.perform("switch", home=True)
        self.assertIn((f"{HOME}/activate",), commands)
        self.assertFalse(any("nixos-rebuild" in args for args in commands))
        self.assertEqual(state["applied_home"]["sha"], SHA)

    def test_unknown_or_empty_choice_defers(self):
        for answer in ("", "bad", "4"):
            with patch("builtins.input", return_value=answer):
                self.assertEqual(u.activation_choice(), "later")


class FailureBoundaryTests(unittest.TestCase):
    def test_api_failure_prevents_merge_and_build(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(u, "clean_checkout"), \
                patch.object(u, "git", return_value=SHA) as git, \
                patch.object(u, "evidence", side_effect=subprocess.CalledProcessError(1, "gh")), \
                patch.object(u, "build_candidate") as build:
            with self.assertRaises(subprocess.CalledProcessError):
                u.update(Path(tmp), Path(tmp))
            self.assertFalse(any(call.args[1] == "merge" for call in git.call_args_list))
            build.assert_not_called()

    def test_diverged_history_prevents_merge_and_build(self):
        def git(repo, *args):
            if args[0] == "merge-base":
                raise subprocess.CalledProcessError(1, args)
            return SHA
        with tempfile.TemporaryDirectory() as tmp, patch.object(u, "clean_checkout"), \
                patch.object(u, "git", side_effect=git) as calls, \
                patch.object(u, "evidence", return_value=MANIFEST), \
                patch.object(u, "build_candidate") as build:
            with self.assertRaises(u.UpdateError):
                u.update(Path(tmp), Path(tmp))
            self.assertFalse(any(call.args[1] == "merge" for call in calls.call_args_list))
            build.assert_not_called()

    def test_successful_build_roots_before_dropping_staging_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            staging = directory / "building-system"
            staging.symlink_to(SYSTEM)
            def command(*args, **kwargs):
                self.assertTrue(staging.is_symlink())
                if args[0] == "nix":
                    return json.dumps([{"outputs": {"out": SYSTEM}}])
                self.assertEqual(args, ("nix-store", "--add-root", str(directory / "pending-system"), "--indirect", "--realise", SYSTEM))
                return SYSTEM
            with patch.object(u, "run", side_effect=command):
                self.assertEqual(u.build_candidate(directory, SHA, MANIFEST, directory, False), SYSTEM)
            self.assertFalse(staging.is_symlink())

    def test_mismatched_build_preserves_previous_pending_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            pending = directory / "pending-system"
            pending.symlink_to(SYSTEM)
            with patch.object(u, "run", return_value=json.dumps([{"outputs": {"out": HOME}}])):
                with self.assertRaises(u.UpdateError):
                    u.build_candidate(directory, SHA, MANIFEST, directory, False)
            self.assertEqual(str(pending.readlink()), SYSTEM)

    def test_notification_deduplicates_and_distinguishes_scheduled(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(u, "api_json", return_value={"object": {"sha": SHA}}), \
                patch.object(u, "evidence", return_value=MANIFEST), \
                patch.object(u, "system_status", return_value={"active": "old", "boot_default": SYSTEM}), \
                patch.object(u, "run") as command:
            u.notify(Path(tmp))
            u.notify(Path(tmp))
            command.assert_called_once()
            self.assertIn("scheduled for next boot", command.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
