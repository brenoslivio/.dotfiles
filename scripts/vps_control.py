#!/usr/bin/env python3
"""Root-side, durable VPS deployment transactions. Never reboots or restores databases."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid

STORE = re.compile(r"/nix/store/[0-9a-df-np-sv-z]{32}-nixos-system-ahimsa-vps-[^/\s]+")
SHA = re.compile(r"[0-9a-f]{40}")
PENDING = {"applying", "awaiting_confirmation", "scheduling", "boot_pending", "committing"}
STATE = Path('/var/lib/dotfiles-vps')
PROFILE = '/nix/var/nix/profiles/system'
BACKUPS = Path('/var/backups/media-stack')
MEDIA_DIRS = ['jellyfin', 'seerr', 'radarr', 'sonarr', 'prowlarr', 'qBittorrent', 'bazarr', 'lidarr', 'media-stack']


def run(*args, timeout=120):
    return subprocess.check_output(args, text=True, timeout=timeout).strip()


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
        temp = stream.name
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def link(path):
    return str(Path(path).resolve()) if Path(path).exists() else None


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Controller:
    def __init__(self, config, executable):
        self.config, self.executable = config, executable
        self.file = STATE / 'state.json'

    def read(self):
        return json.loads(self.file.read_text()) if self.file.exists() else {}

    def save(self, data):
        atomic(self.file, data)

    def boot_id(self):
        return Path('/proc/sys/kernel/random/boot_id').read_text().strip()

    def status(self):
        return {**self.read(), 'host': socket.gethostname(), 'active': link('/run/current-system'),
                'boot_default': link(PROFILE), 'boot_id_now': self.boot_id()}

    def transaction(self, token):
        state = self.read()
        if not token or state.get('token') != token:
            raise RuntimeError('Deployment transaction changed; refresh VPS status.')
        return state

    def candidate(self, path):
        if not STORE.fullmatch(path):
            raise RuntimeError('Invalid VPS system path.')
        if Path(path, 'etc/hostname').read_text().strip() != self.config['host']:
            raise RuntimeError('Candidate belongs to another host.')
        if not Path(path, 'sw/bin/dotfiles-vps-control').is_file():
            raise RuntimeError('Candidate lacks the recovery helper.')
        return path

    def protect(self, name, path):
        run('nix-env', '--profile', '/nix/var/nix/profiles/dotfiles-vps-' + name, '--set', path)

    def stage(self, path, sha):
        current = self.read()
        if current.get('phase') in PENDING | {'rolling_back', 'rollback_failed'}:
            raise RuntimeError('A VPS activation is pending; confirm or roll it back first.')
        self.candidate(path)
        if not SHA.fullmatch(sha):
            raise RuntimeError('Invalid revision.')
        self.protect('pending', path)
        state = {'token': uuid.uuid4().hex, 'path': path, 'sha': sha, 'phase': 'prepared'}
        self.save(state)
        return state

    def health(self):
        for service in self.config['services']:
            run('systemctl', 'is-active', '--quiet', service)
        with urllib.request.urlopen(f"http://127.0.0.1:{self.config['jellyfinPort']}/System/Info/Public", timeout=10) as response:
            info = json.load(response)
        if not info.get('StartupWizardCompleted') or not info.get('Id'):
            raise RuntimeError('Jellyfin account setup is incomplete.')
        return {'server_id': info['Id'], 'url': self.config['url']}

    def backup_record(self, path):
        path = Path(path)
        if path.is_symlink() or path.resolve().parent != BACKUPS.resolve() or not path.is_file():
            raise RuntimeError('Unexpected backup location.')
        return {'path': str(path), 'sha256': digest(path), 'size': path.stat().st_size}

    def backup(self, token, cold=False):
        state = self.transaction(token)
        if state['phase'] not in ({'boot_pending'} if cold else {'prepared'}):
            raise RuntimeError('Backup is not allowed during this deployment phase.')
        if cold:
            # Runs before media-stack-prepare and therefore before any media database opens.
            BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True)
            path = BACKUPS / (time.strftime('%Y%m%d-%H%M%S') + '-boot-' + uuid.uuid4().hex + '.tar.gz')
            partial = path.with_suffix('.partial')
            try:
                with partial.open('xb') as stream:
                    os.chmod(partial, 0o600)
                    with tarfile.open(fileobj=stream, mode='w:gz', dereference=True) as archive:
                        for source in [Path('/var/lib') / n for n in MEDIA_DIRS] + [Path('/etc/media-stack.json')]:
                            if source.exists():
                                archive.add(source, arcname=str(source).lstrip('/'))
                os.replace(partial, path)
            finally:
                partial.unlink(missing_ok=True)
            record = self.backup_record(path)
        elif Path('/etc/media-stack.json').exists():
            helper = Path('/run/current-system/sw/bin/media-stack')
            if not helper.exists():
                raise RuntimeError('Current media state exists but its backup command is unavailable.')
            # The service continues and restarts the stack even if the SSH client disconnects.
            run('systemd-run', '--quiet', '--wait', '--collect', '--unit=dotfiles-vps-backup',
                '--property=Type=oneshot', '--property=TimeoutStartSec=30min', str(helper), 'backup', timeout=1900)
            choices = list(BACKUPS.glob('*.tar.gz'))
            if not choices:
                raise RuntimeError('Backup did not produce an archive.')
            record = self.backup_record(max(choices, key=lambda p: p.stat().st_mtime_ns))
        else:
            if any((Path('/var/lib') / n).exists() for n in MEDIA_DIRS):
                raise RuntimeError('Existing media state needs a reviewed backup before bootstrap.')
            record = None
        state['backup'] = record
        state['backup_ack'] = record is None
        self.save(state)
        return record

    def ack(self, token, checksum):
        state = self.transaction(token)
        record = state.get('backup')
        if record is None or record['sha256'] != checksum or digest(record['path']) != checksum:
            raise RuntimeError('Backup acknowledgement does not match the server archive.')
        state['backup_ack'] = True
        self.save(state)

    def watchdog(self, token):
        # Bootstrap protection also works before the new NixOS timer is installed.
        run('systemd-run', '--quiet', '--unit=dotfiles-vps-watch-' + token,
            '--on-active=30s', '--on-unit-active=30s', self.executable, 'recover')

    def begin(self, token, choice):
        state = self.transaction(token)
        if state['phase'] != 'prepared' or not state.get('backup_ack'):
            raise RuntimeError('Prepare and download a verified backup before activation.')
        status = self.status()
        for name in ('active', 'boot_default'):
            if not status[name] or not Path(status[name], 'bin/switch-to-configuration').is_file():
                raise RuntimeError('Cannot identify the previous VPS system.')
        self.protect('previous-active', status['active'])
        self.protect('previous-boot', status['boot_default'])
        self.watchdog(token)
        state.update(previous_active=status['active'], previous_boot=status['boot_default'],
                     boot_id=self.boot_id(), deadline=time.time() + 900,
                     phase='applying' if choice == 'switch' else 'scheduling', choice=choice)
        self.save(state)
        # Activation survives a dropped SSH session and has a bounded runtime.
        run('systemd-run', '--quiet', '--collect', '--unit=dotfiles-vps-apply',
            '--property=RuntimeMaxSec=600', self.executable, 'activate', token)

    def activate(self, token):
        # Deliberately does not hold the state lock while running activation.
        state = self.transaction(token)
        if state['phase'] not in {'applying', 'scheduling'}:
            raise RuntimeError('No activation is armed.')
        try:
            if state['choice'] == 'boot':
                run('nix-env', '--profile', PROFILE, '--set', state['path'])
            run(state['path'] + '/bin/switch-to-configuration',
                'test' if state['choice'] == 'switch' else 'boot', timeout=550)
            with state_lock():
                current = self.transaction(token)
                if current['phase'] != state['phase']:
                    raise RuntimeError('Activation was superseded by recovery.')
                current['phase'] = 'awaiting_confirmation' if state['choice'] == 'switch' else 'boot_pending'
                self.save(current)
        except Exception:
            with state_lock():
                current = self.transaction(token)
                if current['phase'] in {'applying', 'scheduling'}:
                    current['deadline'] = 0
                    self.save(current)
            raise

    def boot_prepare(self):
        state = self.read()
        if state.get('phase') != 'boot_pending' or state['boot_id'] == self.boot_id():
            return
        if link('/run/current-system') != state['path']:
            self.request_rollback(state['token'])
            raise RuntimeError('Unexpected booted system; recovery requested before media startup.')
        self.backup(state['token'], cold=True)
        state = self.read()
        state.update(phase='awaiting_confirmation', deadline=time.time() + 900, boot_id=self.boot_id())
        self.save(state)

    def confirm(self, token):
        state = self.transaction(token)
        if state['phase'] != 'awaiting_confirmation' or time.time() >= state['deadline']:
            raise RuntimeError('No unexpired deployment is awaiting confirmation.')
        if link('/run/current-system') != state['path'] or not state.get('backup_ack'):
            raise RuntimeError('Candidate must be active and its backup copied off the VPS.')
        self.health()
        state['phase'] = 'committing'
        self.save(state)
        run('nix-env', '--profile', PROFILE, '--set', state['path'])
        run(state['path'] + '/bin/switch-to-configuration', 'boot', timeout=120)
        if link(PROFILE) != state['path'] or link('/run/current-system') != state['path']:
            raise RuntimeError('Actual VPS system links changed during confirmation.')
        self.protect('known-good', state['path'])
        state['phase'] = 'confirmed'
        self.save(state)
        atomic(STATE / 'last-deployment.json', state)
        self.stop_watchdog(token)

    def stop_watchdog(self, token):
        subprocess.run(['systemctl', 'stop', 'dotfiles-vps-watch-' + token + '.timer'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

    def request_rollback(self, token):
        self.rollback_state(token)
        active = subprocess.run(['systemctl', 'is-active', '--quiet', 'dotfiles-vps-rollback.service'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if active.returncode == 0:
            return
        # A transient worker survives removal of the new NixOS recovery unit,
        # including rollback to the original VPS that has no updater installed.
        run('systemd-run', '--quiet', '--collect', '--unit=dotfiles-vps-rollback',
            '--property=RuntimeMaxSec=600', self.executable, 'rollback-worker', token)

    def rollback_state(self, token):
        state = self.transaction(token)
        if state.get('phase') == 'prepared' and (STATE / 'last-deployment.json').exists():
            previous = json.loads((STATE / 'last-deployment.json').read_text())
            if link('/run/current-system') != previous['path']:
                raise RuntimeError('Active system differs from the last confirmed deployment.')
            state = {**previous, 'token': token}
        if state.get('phase') not in PENDING | {'confirmed', 'rolling_back', 'rollback_failed'}:
            raise RuntimeError('No deployed transaction is available to roll back.')
        return state

    def rollback(self, token):
        with state_lock():
            state = self.rollback_state(token)
            state['phase'] = 'rolling_back'
            self.save(state)
        # Activation can restart units that inspect deployment state. Do not hold
        # the mutation lock while waiting for those units or the apply worker.
        subprocess.run(['systemctl', 'stop', 'dotfiles-vps-apply.service'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        try:
            run('nix-env', '--profile', PROFILE, '--set', state['previous_boot'])
            run(state['previous_active'] + '/bin/switch-to-configuration', 'test', timeout=120)
            run(state['previous_boot'] + '/bin/switch-to-configuration', 'boot', timeout=120)
            state['phase'] = 'rolled_back'
            state['note'] = 'Software restored; databases were not restored. Retained backup may be needed. No reboot requested.'
        except Exception:
            state['phase'] = 'rollback_failed'
            raise
        finally:
            with state_lock():
                self.transaction(token)
                self.save(state)
        self.stop_watchdog(token)

    def recover(self):
        state = self.read()
        phase = state.get('phase')
        if phase == 'boot_pending':
            if state['boot_id'] != self.boot_id():
                # The boot-preparation unit normally handles this first.
                if link('/run/current-system') != state['path']:
                    self.request_rollback(state['token'])
                elif time.time() >= state.get('deadline', 0):
                    self.request_rollback(state['token'])
        elif phase in PENDING | {'rolling_back', 'rollback_failed'} and time.time() >= state.get('deadline', 0):
            self.request_rollback(state['token'])


def state_lock():
    import contextlib
    @contextlib.contextmanager
    def locked():
        STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (STATE / 'lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield
    return locked()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('action', choices=['status', 'stage', 'backup', 'ack', 'begin', 'activate', 'health', 'confirm', 'rollback', 'rollback-worker', 'recover', 'boot-prepare', 'preview'])
    parser.add_argument('token', nargs='?')
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    if os.geteuid() != 0 or socket.gethostname() != config['host']:
        raise RuntimeError('Run this helper as root on the configured VPS only.')
    controller = Controller(config, os.environ['DOTFILES_VPS_CONTROL'])
    if args.action == 'activate':
        controller.activate(args.token)
        return
    if args.action == 'rollback-worker':
        controller.rollback(args.token)
        return
    if args.action == 'status':
        # Atomic state reads stay available while a long backup owns the mutation lock.
        print(json.dumps(controller.status()))
        return
    payload = {} if args.action in {'status', 'health', 'recover', 'boot-prepare'} else json.loads(sys.stdin.read(16385))
    with state_lock():
        action = args.action
        token = payload.get('token')
        result = None
        if action == 'status': result = controller.status()
        elif action == 'health': result = controller.health()
        elif action == 'stage': result = controller.stage(payload['path'], payload['sha'])
        elif action == 'backup': result = controller.backup(token)
        elif action == 'ack': controller.ack(token, payload['sha256'])
        elif action == 'begin':
            if payload['choice'] not in {'switch', 'boot'}: raise RuntimeError('Invalid activation choice.')
            controller.begin(token, payload['choice'])
        elif action == 'confirm': controller.confirm(token)
        elif action == 'rollback': controller.request_rollback(token)
        elif action == 'recover': controller.recover()
        elif action == 'boot-prepare': controller.boot_prepare()
        elif action == 'preview':
            path = controller.candidate(payload['path'])
            result = {'diff': run('nix', 'store', 'diff-closures', link('/run/current-system'), path),
                      'activation': run(path + '/bin/switch-to-configuration', 'dry-activate')}
        print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        sys.exit(f'VPS operation stopped: {error}')
