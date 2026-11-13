import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ci_vps_deploy as ci
import update as u
import vps_update as vps

SHA = 'd' * 40
SYSTEM = '/nix/store/' + 'a' * 32 + '-nixos-system-ahimsa-vps-test'
MANIFEST = {'sha': SHA, 'system_path': SYSTEM, 'run_id': '123', 'run_attempt': '1', 'ci_url': 'ci'}
PENDING = {'sha': SHA, 'path': SYSTEM, 'token': 'test-token'}


class AutomaticDeploymentTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'workflow_run', 'GITHUB_REPOSITORY': u.REPOSITORY,
            'CI_SHA': SHA, 'CI_RUN_ID': '123', 'CI_RUN_ATTEMPT': '1',
            'GITHUB_RUN_ID': '456', 'GITHUB_RUN_ATTEMPT': '2', 'PATH': os.environ['PATH']}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_untrusted_event_does_not_query_evidence(self):
        with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'pull_request'}), patch.object(u, 'evidence') as evidence:
            with self.assertRaises(u.UpdateError):
                ci.verified_manifest()
            evidence.assert_not_called()

    def test_superseded_main_is_skipped_without_build_or_ssh(self):
        with patch.object(ci, 'current_main', return_value=False), patch.object(u, 'evidence') as evidence:
            self.assertIsNone(ci.verified_manifest())
            evidence.assert_not_called()

    def test_wrong_attempt_or_checkout_is_rejected(self):
        with patch.object(ci, 'current_main', return_value=True), patch.object(u, 'evidence', return_value=MANIFEST), \
                patch.object(u, 'git', return_value=SHA):
            self.assertEqual(ci.verified_manifest(), MANIFEST)
            with patch.dict(os.environ, {'CI_RUN_ATTEMPT': '2'}), self.assertRaises(u.UpdateError):
                ci.verified_manifest()
            with patch.object(u, 'git', return_value='e' * 40), self.assertRaises(u.UpdateError):
                ci.verified_manifest()

    def test_requires_uploaded_backup_from_this_run(self):
        valid = {'name': 'vps-backup-456-2', 'expired': False, 'workflow_run': {'id': 456}, 'size_in_bytes': 100}
        with patch.object(u, 'api_json', return_value=valid):
            ci.verify_backup_upload('789')
        for invalid in [{**valid, 'expired': True}, {**valid, 'workflow_run': {'id': 455}},
                        {**valid, 'name': 'plaintext-backup'}, {**valid, 'size_in_bytes': 0}]:
            with patch.object(u, 'api_json', return_value=invalid), self.assertRaises(u.UpdateError):
                ci.verify_backup_upload('789')
        with patch.object(u, 'api_json') as api, self.assertRaises(u.UpdateError):
            ci.verify_backup_upload('')
        api.assert_not_called()

    def test_preparation_encrypts_before_signalling_ready_without_ack(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            backup = root / 'backup.tar.gz'
            backup.write_bytes(b'private state')
            status = {**PENDING, 'phase': 'prepared'}
            with patch.object(u, 'build_candidate', return_value=SYSTEM), \
                    patch.object(ci, 'current_main', return_value=True), \
                    patch.object(vps, 'prepare_deployment', return_value=PENDING), \
                    patch.object(vps, 'remote', return_value=status), \
                    patch.object(vps, 'offsite_backup', return_value=backup) as download, \
                    patch.object(ci.subprocess, 'run') as encrypt, patch.object(ci, 'output') as output:
                ci.prepare(root, MANIFEST)
                self.assertFalse(download.call_args.kwargs['acknowledge'])
                self.assertEqual(encrypt.call_args.args[0][0], 'age')
                output.assert_called_once_with('prepared', 'true')
                output.reset_mock()
                encrypt.side_effect = subprocess.CalledProcessError(1, 'age')
                with self.assertRaises(subprocess.CalledProcessError):
                    ci.prepare(root, MANIFEST)
                output.assert_not_called()

    def test_missing_artifact_never_acknowledges_or_activates(self):
        with patch.object(u, 'read_state', return_value={'pending_system': PENDING}), \
                patch.object(vps, 'remote') as remote, patch.object(vps, 'activate_prepared') as activate:
            with self.assertRaises(u.UpdateError):
                ci.activate(Path('/tmp'), MANIFEST)
            remote.assert_not_called()
            activate.assert_not_called()

    def test_main_advancing_after_backup_prevents_activation(self):
        with patch.object(u, 'read_state', return_value={'pending_system': PENDING}), \
                patch.object(ci, 'verify_backup_upload'), patch.object(ci, 'current_main', return_value=False), \
                patch.object(vps, 'offsite_backup') as acknowledge, patch.object(vps, 'activate_prepared') as activate:
            ci.activate(Path('/tmp'), MANIFEST)
            acknowledge.assert_not_called()
            activate.assert_not_called()

    def test_changed_remote_transaction_prevents_activation(self):
        with patch.object(u, 'read_state', return_value={'pending_system': PENDING}), \
                patch.object(ci, 'verify_backup_upload'), patch.object(ci, 'current_main', return_value=True), \
                patch.object(vps, 'remote', return_value={**PENDING, 'token': 'another'}), \
                patch.object(vps, 'offsite_backup') as acknowledge, patch.object(vps, 'activate_prepared') as activate:
            with self.assertRaises(u.UpdateError):
                ci.activate(Path('/tmp'), MANIFEST)
            acknowledge.assert_not_called()
            activate.assert_not_called()

    def test_encrypted_backup_round_trip(self):
        # Exercise the actual encryption format with a disposable key, never a real credential.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            key = root / 'identity'
            subprocess.run(['age-keygen', '-o', str(key)], check=True, capture_output=True)
            recipient = subprocess.check_output(['age-keygen', '-y', str(key)], text=True).strip()
            plaintext = b'test-only backup contents\x00\xff'
            encrypted = subprocess.check_output(['age', '-r', recipient], input=plaintext)
            self.assertNotIn(plaintext, encrypted)
            self.assertEqual(subprocess.check_output(['age', '-d', '-i', str(key)], input=encrypted), plaintext)
