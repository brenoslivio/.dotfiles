import copy
from contextlib import nullcontext
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import update as u
import vps_control as control
import vps_update as client

NEW = '/nix/store/' + 'a' * 32 + '-nixos-system-ahimsa-vps-new'
OLD = '/nix/store/' + 'b' * 32 + '-nixos-system-ahimsa-vps-old'
BOOT = '/nix/store/' + 'c' * 32 + '-nixos-system-ahimsa-vps-boot'
SHA = 'd' * 40
TOKEN = 'e' * 32


class EvidenceTests(unittest.TestCase):
    def test_host_evidence_is_not_interchangeable(self):
        manifest = {'schema': 1, 'repository': u.REPOSITORY, 'sha': SHA, 'host': 'ahimsa-vps',
                    'system': 'x86_64-linux', 'user': 'root', 'event': 'push',
                    'run_id': '1', 'run_attempt': '2', 'system_path': NEW}
        run = {'id': 1, 'run_attempt': 2}
        self.assertEqual(u.validate_manifest(manifest, SHA, run, 'ahimsa-vps'), manifest)
        with self.assertRaises(u.UpdateError):
            u.validate_manifest(manifest, SHA, run)
        for key, value in [('sha', 'f' * 40), ('user', 'brenoslivio'), ('run_attempt', '1'), ('system_path', '/tmp/result')]:
            with self.subTest(key=key), self.assertRaises(u.UpdateError):
                u.validate_manifest({**manifest, key: value}, SHA, run, 'ahimsa-vps')

    def test_desktop_jobs_do_not_authorize_vps(self):
        jobs = [{'name': name, 'status': 'completed', 'conclusion': 'success'} for name in u.REQUIRED_JOBS]
        with self.assertRaises(u.UpdateError):
            u.validate_jobs(jobs, 'ahimsa-vps')
        jobs = [{'name': name, 'status': 'completed', 'conclusion': 'success'} for name in u.HOSTS['ahimsa-vps']['jobs']]
        u.validate_jobs(jobs, 'ahimsa-vps')
        with self.assertRaises(u.UpdateError):
            u.validate_jobs(jobs + [jobs[0]], 'ahimsa-vps')

    def test_vps_build_uses_vps_attribute_and_rejects_mismatch(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(u, 'run', return_value=json.dumps([{'outputs': {'out': OLD}}])) as run:
            with self.assertRaises(u.UpdateError):
                u.build_candidate(Path(temp), SHA, {'system_path': NEW}, Path(temp), False, 'ahimsa-vps')
            self.assertIn('#nixosConfigurations.ahimsa-vps.config.system.build.toplevel', run.call_args.args[-1])


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.patch(control, 'STATE', new=self.directory)
        def command(*args, **kwargs):
            if args[:3] == ('nix-env', '--profile', control.PROFILE):
                self.boot = args[-1]
            return ''
        self.commands = self.patch(control, 'run', side_effect=command)
        self.patch(control.subprocess, 'run')
        self.clock = self.patch(control.time, 'time', return_value=1000)
        self.active = OLD
        self.boot = BOOT
        self.patch(control, 'link', side_effect=lambda p: self.active if p == '/run/current-system' else self.boot)
        self.c = control.Controller({'host': 'ahimsa-vps', 'services': [], 'url': 'https://media.breno.science', 'jellyfinPort': 8096}, NEW + '/sw/bin/dotfiles-vps-control')
        self.patch(self.c, 'boot_id', return_value='boot-one')
        self.patch(self.c, 'candidate', return_value=NEW)
        self.patch(self.c, 'health', return_value={'server_id': 'server'})
        self.c.save({'token': TOKEN, 'path': NEW, 'sha': SHA, 'phase': 'prepared'})

    def patch(self, obj, name, **kwargs):
        p = patch.object(obj, name, **kwargs)
        result = p.start()
        self.addCleanup(p.stop)
        return result

    def armed(self, phase='awaiting_confirmation', **changes):
        state = {**self.c.read(), 'phase': phase, 'deadline': 1500, 'choice': 'switch',
                 'previous_active': OLD, 'previous_boot': BOOT, 'backup_ack': True,
                 'boot_id': 'boot-one', **changes}
        self.c.save(state)
        return state

    def test_stage_cannot_replace_pending_activation(self):
        self.armed()
        with self.assertRaises(RuntimeError):
            self.c.stage(NEW, SHA)
        self.commands.assert_not_called()

    def test_begin_requires_offsite_backup_acknowledgement(self):
        with self.assertRaises(RuntimeError):
            self.c.begin(TOKEN, 'switch')
        self.commands.assert_not_called()

    def test_begin_arms_watchdog_before_detached_activation(self):
        self.c.save({**self.c.read(), 'backup_ack': True})
        with patch.object(Path, 'is_file', return_value=True):
            self.c.begin(TOKEN, 'switch')
        calls = [call.args for call in self.commands.call_args_list]
        watchdog = next(i for i, args in enumerate(calls) if '--on-active=30s' in args)
        activation = next(i for i, args in enumerate(calls) if '--unit=dotfiles-vps-apply' in args)
        self.assertLess(watchdog, activation)
        state = self.c.read()
        self.assertEqual(state['previous_active'], OLD)
        self.assertEqual(state['previous_boot'], BOOT)
        self.assertEqual(state['phase'], 'applying')
        self.assertGreater(state['deadline'], 1000)

    def test_temporary_activation_does_not_change_boot_profile(self):
        self.armed('applying')
        self.c.activate(TOKEN)
        self.commands.assert_called_once_with(NEW + '/bin/switch-to-configuration', 'test', timeout=550)
        self.assertEqual(self.c.read()['phase'], 'awaiting_confirmation')

    def test_failed_activation_becomes_immediately_recoverable(self):
        self.armed('applying')
        self.commands.side_effect = subprocess.CalledProcessError(1, 'activation')
        with self.assertRaises(subprocess.CalledProcessError):
            self.c.activate(TOKEN)
        self.assertEqual(self.c.read()['deadline'], 0)

    def test_disconnect_causes_expired_transaction_to_rollback(self):
        self.armed(deadline=999)
        with patch.object(self.c, 'request_rollback', side_effect=self.c.rollback):
            self.c.recover()
        calls = [call.args for call in self.commands.call_args_list]
        self.assertIn(('nix-env', '--profile', control.PROFILE, '--set', BOOT), calls)
        self.assertIn((OLD + '/bin/switch-to-configuration', 'test'), calls)
        self.assertIn((BOOT + '/bin/switch-to-configuration', 'boot'), calls)
        self.assertEqual(self.c.read()['phase'], 'rolled_back')
        self.assertFalse(any('reboot' in args for args in calls))

    def test_unexpired_transaction_is_not_rolled_back(self):
        self.armed()
        self.c.recover()
        self.commands.assert_not_called()

    def test_confirmation_requires_actual_candidate_and_healthy_services(self):
        self.armed()
        with self.assertRaises(RuntimeError):
            self.c.confirm(TOKEN)
        self.active = NEW
        self.c.health.side_effect = RuntimeError('unhealthy')
        with self.assertRaises(RuntimeError):
            self.c.confirm(TOKEN)
        self.commands.assert_not_called()
        self.assertEqual(self.c.read()['phase'], 'awaiting_confirmation')

    def test_confirmation_commits_only_after_health_check(self):
        self.armed()
        self.active = NEW
        self.c.confirm(TOKEN)
        self.c.health.assert_called_once()
        self.assertEqual(self.c.read()['phase'], 'confirmed')
        self.commands.assert_any_call('nix-env', '--profile', control.PROFILE, '--set', NEW)

    def test_late_confirmation_rejected(self):
        self.armed(deadline=999)
        self.active = NEW
        with self.assertRaises(RuntimeError):
            self.c.confirm(TOKEN)
        self.commands.assert_not_called()

    def test_preparing_later_does_not_lose_previous_rollback(self):
        self.armed()
        self.active = NEW
        self.c.confirm(TOKEN)
        state = self.c.stage(NEW, SHA)
        self.c.rollback(state['token'])
        self.assertEqual(self.c.read()['phase'], 'rolled_back')
        self.assertEqual(self.c.read()['previous_active'], OLD)

    def test_old_client_cannot_confirm_a_different_transaction(self):
        self.armed()
        with self.assertRaises(RuntimeError):
            self.c.confirm('f' * 32)
        self.commands.assert_not_called()

    def test_scheduled_boot_does_not_expire_before_reboot(self):
        self.armed('boot_pending', deadline=1)
        self.c.recover()
        self.commands.assert_not_called()

    def test_next_boot_requires_new_backup_and_confirmation(self):
        self.armed('boot_pending')
        self.active = NEW
        self.c.boot_id.return_value = 'boot-two'
        def cold_backup(token, cold):
            self.assertTrue(cold)
            self.c.save({**self.c.read(), 'backup_ack': False, 'backup': {'path': 'new-backup'}})
        backup = self.patch(self.c, 'backup', side_effect=cold_backup)
        self.c.boot_prepare()
        backup.assert_called_once_with(TOKEN, cold=True)
        state = self.c.read()
        self.assertEqual(state['phase'], 'awaiting_confirmation')
        self.assertEqual(state['boot_id'], 'boot-two')
        self.assertFalse(state['backup_ack'])
        with self.assertRaises(RuntimeError):
            self.c.confirm(TOKEN)

    def test_failed_rollback_is_retried(self):
        self.armed(deadline=0)
        self.commands.side_effect = subprocess.CalledProcessError(1, 'rollback')
        with patch.object(self.c, 'request_rollback', side_effect=self.c.rollback):
            with self.assertRaises(subprocess.CalledProcessError):
                self.c.recover()
        self.assertEqual(self.c.read()['phase'], 'rollback_failed')
        self.commands.side_effect = None
        with patch.object(self.c, 'request_rollback', side_effect=self.c.rollback):
            self.c.recover()
        self.assertEqual(self.c.read()['phase'], 'rolled_back')

    def test_recovery_uses_worker_outside_the_replaced_system_units(self):
        self.armed(deadline=999)
        with patch.object(control.subprocess, 'run', return_value=subprocess.CompletedProcess([], 3)):
            self.c.recover()
        self.commands.assert_called_once_with('systemd-run', '--quiet', '--collect',
            '--unit=dotfiles-vps-rollback', '--property=RuntimeMaxSec=600',
            self.c.executable, 'rollback-worker', TOKEN)

    def test_rollback_without_previous_deployment_fails_before_worker(self):
        with self.assertRaises(RuntimeError):
            self.c.request_rollback(TOKEN)
        self.commands.assert_not_called()

    def test_invalid_candidate_path_is_rejected_before_any_execution(self):
        real = control.Controller(self.c.config, 'helper')
        for path in ['/tmp/system', NEW + '/bin', NEW + ';reboot']:
            with self.assertRaises((RuntimeError, FileNotFoundError)):
                real.candidate(path)
        self.commands.assert_not_called()


class ClientTests(unittest.TestCase):
    def test_later_prepares_without_backup_or_activation(self):
        actions = []
        def remote(action, *args, **kwargs):
            actions.append(action)
            if action == 'status':
                return {'host': 'ahimsa-vps', 'active': OLD, 'boot_default': BOOT}
            if action == 'preview': return {'diff': 'diff', 'activation': 'preview'}
            if action == 'stage': return {'token': TOKEN}
            raise AssertionError(action)
        with tempfile.TemporaryDirectory() as temp, patch.object(u, 'clean_checkout'), \
                patch.object(u, 'git', side_effect=lambda repo, *args: SHA if args[0] == 'rev-parse' else ''), \
                patch.object(u, 'evidence', return_value={'system_path': NEW, 'ci_url': 'ci'}), \
                patch.object(u, 'build_candidate', return_value=NEW), patch.object(u, 'activation_choice', return_value='later'), \
                patch.object(client, 'ssh_session', return_value=nullcontext()), \
                patch.object(client.subprocess, 'run') as run, patch.object(client, 'remote', side_effect=remote):
            client.update(Path(temp), Path(temp))
            self.assertEqual(actions, ['status', 'preview', 'stage'])
            self.assertEqual(u.read_state(Path(temp))['pending_system']['token'], TOKEN)
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0],
                             ['nix', 'copy', '--no-check-sigs', '--to', 'ssh-ng://root@95.217.8.248', NEW])
            self.assertIn('StrictHostKeyChecking=yes', run.call_args.kwargs['env']['NIX_SSHOPTS'])

    def test_unverified_revision_never_contacts_vps(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(u, 'clean_checkout'), \
                patch.object(u, 'git', return_value=SHA), patch.object(u, 'evidence', side_effect=u.UpdateError('CI failed')), \
                patch.object(client, 'remote') as remote, patch.object(client.subprocess, 'check_output') as ssh:
            with self.assertRaises(u.UpdateError):
                client.update(Path(temp), Path(temp))
            remote.assert_not_called()
            ssh.assert_not_called()

    def test_remote_ssh_is_fresh_and_checks_host_keys(self):
        with patch.object(client.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '{}')) as command:
            client.remote('status')
        args = command.call_args.args[0]
        self.assertIn('StrictHostKeyChecking=yes', args)
        self.assertIn('ControlPath=none', args)
        self.assertIn('BatchMode=yes', args)
        self.assertIn('root@95.217.8.248', args)

    def test_public_health_rejects_wrong_server(self):
        health = {'server_id': 'expected', 'url': 'https://media.breno.science'}
        response = io.BytesIO(json.dumps({'Id': 'another', 'StartupWizardCompleted': True}).encode())
        response.url = 'https://media.breno.science/System/Info/Public'
        with patch.object(client, 'remote', return_value=health), patch.object(client.urllib.request, 'urlopen', return_value=response):
            with self.assertRaises(u.UpdateError):
                client.public_health('helper')

    def test_corrupt_backup_is_not_acknowledged(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / 'backups').mkdir()
            (directory / 'backups/test.tar.gz').write_bytes(b'corrupted')
            state = {'token': TOKEN, 'backup': {'path': '/var/backups/media-stack/test.tar.gz', 'sha256': hashlib.sha256(b'good').hexdigest(), 'size': 4}}
            with patch.object(client, 'remote') as remote:
                with self.assertRaises(u.UpdateError):
                    client.offsite_backup(directory, state, 'helper')
                remote.assert_not_called()

    def test_failed_public_health_cannot_confirm(self):
        status = {'host': 'ahimsa-vps', 'phase': 'awaiting_confirmation', 'sha': SHA, 'path': NEW, 'token': TOKEN}
        with tempfile.TemporaryDirectory() as temp, patch.object(client, 'remote', return_value=status) as remote, \
                patch.object(client, 'offsite_backup'), patch.object(client, 'public_health', side_effect=OSError('TLS failure')):
            with self.assertRaises(OSError):
                client.confirm(Path(temp), verify=False)
            self.assertEqual([c.args[0] for c in remote.call_args_list], ['status'])

    def test_confirmation_cannot_ack_another_transaction(self):
        status = {'host': 'ahimsa-vps', 'phase': 'awaiting_confirmation', 'sha': SHA, 'path': NEW, 'token': 'f' * 32}
        with tempfile.TemporaryDirectory() as temp, patch.object(client, 'remote', return_value=status), \
                patch.object(client, 'offsite_backup') as backup:
            with self.assertRaises(u.UpdateError):
                client.confirm(Path(temp), verify=False, expected={'token': TOKEN, 'path': NEW, 'sha': SHA})
            backup.assert_not_called()


class SSHSessionTests(unittest.TestCase):
    def setUp(self):
        self.original = client.SSH_OPTIONS[:]
        self.addCleanup(lambda: client.SSH_OPTIONS.__setitem__(slice(None), self.original))

    def test_unlocked_key_reuses_existing_authentication(self):
        success = subprocess.CompletedProcess([], 0, 'ahimsa-vps\n', '')
        with patch.object(client.subprocess, 'run', return_value=success), \
                patch.object(client.subprocess, 'Popen') as agent:
            with client.ssh_session():
                self.assertEqual(client.SSH_OPTIONS, self.original)
            agent.assert_not_called()

    def test_network_and_host_key_failures_do_not_prompt(self):
        for message in ['Connection timed out', 'Host key verification failed.']:
            with self.subTest(message=message), \
                    patch.object(client.subprocess, 'run', return_value=subprocess.CompletedProcess([], 255, '', message)), \
                    patch.object(client.subprocess, 'Popen') as agent:
                with self.assertRaises(u.UpdateError), client.ssh_session():
                    self.fail('Unavailable server must not allow deployment')
                agent.assert_not_called()

    def test_wrong_host_stops_before_deployment(self):
        with patch.object(client.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'another-host', '')):
            with self.assertRaises(u.UpdateError), client.ssh_session():
                self.fail('Wrong host must not allow deployment')

    def test_noninteractive_locked_key_fails_without_prompt(self):
        denied = subprocess.CompletedProcess([], 255, '', 'Permission denied (publickey).')
        with patch.object(client.subprocess, 'run', return_value=denied), \
                patch.object(client.sys.stdin, 'isatty', return_value=False), \
                patch.object(client.subprocess, 'Popen') as agent:
            with self.assertRaisesRegex(u.UpdateError, 'terminal'), client.ssh_session():
                self.fail('Locked key must not allow unattended deployment')
            agent.assert_not_called()

    def test_unlock_is_reused_by_fresh_connections_and_agent_is_cleaned_up(self):
        denied = subprocess.CompletedProcess([], 255, '', 'Permission denied (publickey).')
        with patch.object(client.subprocess, 'run', side_effect=[denied, subprocess.CompletedProcess([], 0, '{}')]) as run, \
                patch.object(client.sys.stdin, 'isatty', return_value=True), \
                patch.object(client.Path, 'is_socket', return_value=True), \
                patch.object(client.subprocess, 'Popen') as agent, \
                patch.object(client.subprocess, 'check_output', return_value='ahimsa-vps\n') as login:
            with client.ssh_session():
                identity = next(option for option in client.SSH_OPTIONS if option.startswith('IdentityAgent='))
                client.remote('status')
                self.assertIn(identity, run.call_args.args[0])
                self.assertIn('BatchMode=yes', run.call_args.args[0])
                self.assertIn('ControlPath=none', run.call_args.args[0])
            interactive, unattended = [call.args[0] for call in login.call_args_list]
            self.assertLess(interactive.index('BatchMode=no'), interactive.index('BatchMode=yes'))
            self.assertIn('AddKeysToAgent=yes', interactive)
            self.assertIn('PreferredAuthentications=publickey', interactive)
            self.assertIn('StrictHostKeyChecking=yes', interactive)
            self.assertNotIn('BatchMode=no', unattended)
            agent.return_value.terminate.assert_called_once()
            agent.return_value.wait.assert_called_once_with(timeout=5)
            self.assertFalse(Path(identity.split('=', 1)[1]).parent.exists())
        self.assertEqual(client.SSH_OPTIONS, self.original)

    def test_cancelled_or_rejected_unlock_cleans_up_before_deployment(self):
        for error in [KeyboardInterrupt(), subprocess.CalledProcessError(255, 'ssh')]:
            with self.subTest(error=type(error).__name__), \
                    patch.object(client.subprocess, 'run', return_value=subprocess.CompletedProcess([], 255, '', 'Permission denied (publickey).')), \
                    patch.object(client.sys.stdin, 'isatty', return_value=True), \
                    patch.object(client.Path, 'is_socket', return_value=True), \
                    patch.object(client.subprocess, 'Popen') as agent, \
                    patch.object(client.subprocess, 'check_output', side_effect=error):
                with self.assertRaises(type(error)), client.ssh_session():
                    self.fail('Failed authentication must not allow deployment')
                agent.return_value.terminate.assert_called_once()
                self.assertEqual(client.SSH_OPTIONS, self.original)


if __name__ == '__main__':
    unittest.main()
