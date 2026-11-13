"""Local client for exact-commit VPS deployments over authenticated SSH."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.parse

import update as u

HOST = 'ahimsa-vps'
TARGET = 'root@95.217.8.248'
SSH_OPTIONS = ['-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
               '-o', 'PreferredAuthentications=publickey', '-o', 'ForwardAgent=no',
               '-o', 'ConnectTimeout=15', '-o', 'ControlMaster=no', '-o', 'ControlPath=none',
               '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3']


@contextmanager
def ssh_session():
    """Unlock through OpenSSH once; keep subsequent recovery connections unattended."""
    probe = subprocess.run(['ssh', *SSH_OPTIONS, TARGET, 'hostname'],
                           text=True, capture_output=True, timeout=60)
    if probe.returncode == 0:
        assert_host({'host': probe.stdout.strip()})
        yield
        return
    if 'permission denied (publickey' not in probe.stderr.lower():
        raise u.UpdateError(f'Cannot connect to VPS: {probe.stderr.strip()}')
    if not sys.stdin.isatty():
        raise u.UpdateError('SSH key is locked or unavailable. Run this command in a terminal to unlock it.')
    print('Unlock your SSH key to connect to the VPS. OpenSSH will ask for its passphrase.', flush=True)
    # A foreground child avoids evaluating ssh-agent shell output or leaving an
    # unlocked agent behind. Its private socket exists only for this operation.
    with tempfile.TemporaryDirectory(prefix='dotfiles-vps-ssh-') as directory:
        socket = Path(directory) / 'agent'
        agent = subprocess.Popen(['ssh-agent', '-D', '-a', str(socket)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        original = SSH_OPTIONS[:]
        try:
            deadline = time.monotonic() + 5
            while not socket.is_socket():
                if agent.poll() is not None or time.monotonic() >= deadline:
                    raise u.UpdateError('Could not start the temporary SSH agent.')
                time.sleep(0.05)
            SSH_OPTIONS[:] = ['-o', f'IdentityAgent={socket}', *original]
            hostname = subprocess.check_output(
                ['ssh', '-o', 'BatchMode=no', '-o', 'AddKeysToAgent=yes',
                 *SSH_OPTIONS, TARGET, 'hostname'], text=True).strip()
            assert_host({'host': hostname})
            # Check that fresh connections work without another prompt before
            # copying anything or arming an activation/recovery transaction.
            hostname = subprocess.check_output(['ssh', *SSH_OPTIONS, TARGET, 'hostname'], text=True).strip()
            assert_host({'host': hostname})
            yield
        finally:
            SSH_OPTIONS[:] = original
            agent.terminate()
            try:
                agent.wait(timeout=5)
            except subprocess.TimeoutExpired:
                agent.kill()
                agent.wait(timeout=5)


def remote(action, payload=None, helper='/run/current-system/sw/bin/dotfiles-vps-control', timeout=120):
    result = subprocess.run(['ssh', *SSH_OPTIONS, TARGET, shlex.join([helper, action])],
                            input=json.dumps(payload or {}), text=True, stdout=subprocess.PIPE,
                            check=True, timeout=timeout)
    return json.loads(result.stdout)


def assert_host(status):
    if status.get('host') != HOST:
        raise u.UpdateError('SSH target is not ahimsa-vps.')


def offsite_backup(directory, status, helper):
    record = status.get('backup')
    if record is None:
        if not status.get('backup_ack'):
            raise u.UpdateError('Server backup is missing.')
        return
    path = Path(record['path'])
    if path.parent != Path('/var/backups/media-stack') or not path.name.endswith('.tar.gz') or not all(c.isalnum() or c in '-.' for c in path.name):
        raise u.UpdateError('Unexpected remote backup path.')
    backups = directory / 'backups'
    backups.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = backups / path.name
    if not destination.exists():
        if shutil.disk_usage(backups).free < record['size'] + 1024**3:
            raise u.UpdateError('Not enough local space for the VPS state backup.')
        fd, temporary = tempfile.mkstemp(dir=backups, prefix='.backup-')
        os.close(fd)
        try:
            subprocess.run(['scp', *SSH_OPTIONS, f'{TARGET}:{path}', temporary], check=True, timeout=1800)
            os.chmod(temporary, 0o600)
            with open(temporary, 'rb') as stream:
                checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
            if checksum != record['sha256'] or Path(temporary).stat().st_size != record['size']:
                raise u.UpdateError('Downloaded backup failed verification.')
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
    with destination.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != record['sha256']:
            raise u.UpdateError('Local backup checksum differs; activation refused.')
    remote('ack', {'token': status['token'], 'sha256': record['sha256']}, helper)
    print(f'Private backup saved locally: {destination}', flush=True)


def public_health(helper):
    # This request also establishes a fresh, non-multiplexed SSH connection.
    health = remote('health', helper=helper)
    if health['url'] != 'https://media.breno.science':
        raise u.UpdateError('Unexpected public media endpoint.')
    with urllib.request.urlopen(health['url'] + '/System/Info/Public', timeout=20) as response:
        public = json.load(response)
        endpoint = urllib.parse.urlsplit(response.url)
        if endpoint.scheme != 'https' or endpoint.netloc != 'media.breno.science':
            raise u.UpdateError('Public health request redirected to another host.')
    if not public.get('StartupWizardCompleted') or public.get('Id') != health['server_id']:
        raise u.UpdateError('HTTPS is not serving this VPS’s initialized Jellyfin instance.')


def confirm(directory, helper='/run/current-system/sw/bin/dotfiles-vps-control', verify=True, expected=None):
    status = remote('status', helper=helper)
    assert_host(status)
    if status.get('phase') != 'awaiting_confirmation':
        raise u.UpdateError('The VPS is not awaiting confirmation.')
    if expected is not None and any(status.get(key) != expected[key] for key in ('token', 'path', 'sha')):
        raise u.UpdateError('VPS transaction changed before confirmation.')
    if verify:
        manifest = u.evidence(status['sha'], HOST)
        if manifest['system_path'] != status['path']:
            raise u.UpdateError('The pending VPS system does not match CI.')
    offsite_backup(directory, status, helper)
    public_health(helper)
    remote('confirm', {'token': status['token']}, helper, timeout=180)
    state = u.read_state(directory)
    state['last_confirmed'] = {'sha': status['sha'], 'path': status['path']}
    state.pop('activation_intent', None)
    u.atomic_json(directory / 'state.json', state)
    print('VPS healthy and selected for next boot. No reboot requested.')


def update(repo, directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    u.clean_checkout(repo)
    u.git(repo, 'fetch', 'origin', '+refs/heads/main:refs/remotes/origin/main')
    sha = u.git(repo, 'rev-parse', 'refs/remotes/origin/main')
    manifest = u.evidence(sha, HOST)
    u.clean_checkout(repo)
    try:
        u.git(repo, 'merge-base', '--is-ancestor', 'HEAD', sha)
    except subprocess.CalledProcessError as exc:
        raise u.UpdateError('Local main is ahead or diverged; resolve it before updating.') from exc
    print(f"Verified VPS revision {sha}\n{manifest['ci_url']}", flush=True)
    u.git(repo, 'merge', '--ff-only', sha)
    u.clean_checkout(repo)
    if u.git(repo, 'rev-parse', 'HEAD') != sha:
        raise u.UpdateError('Checkout changed during VPS preparation.')
    path = u.build_candidate(repo, sha, manifest, directory, False, HOST)
    with ssh_session():
        deploy(path, sha, manifest, directory)


def deploy(path, sha, manifest, directory):
    env = dict(os.environ, NIX_SSHOPTS=shlex.join(SSH_OPTIONS))
    # Local module outputs are unsigned. This authenticated root SSH transfer
    # follows CI/output verification; leave normal cache signature checks intact.
    subprocess.run(['nix', 'copy', '--no-check-sigs', '--to', f'ssh-ng://{TARGET}', path], env=env, check=True)
    helper = path + '/sw/bin/dotfiles-vps-control'
    status = remote('status', helper=helper)
    assert_host(status)
    if status.get('phase') in {'applying', 'scheduling', 'boot_pending', 'awaiting_confirmation', 'committing', 'rolling_back', 'rollback_failed'}:
        raise u.UpdateError('VPS deployment already pending. Use up-vps-status, up-vps-confirm, or rollback-vps.')
    if status['active'] == path and status['boot_default'] == path:
        print('VPS is already active and selected for next boot.')
        return
    preview = remote('preview', {'path': path}, helper)
    print(preview['diff'])
    print(preview['activation'])
    transaction = remote('stage', {'path': path, 'sha': sha}, helper)
    state = u.read_state(directory)
    state['pending_system'] = {'sha': sha, 'path': path, 'ci_url': manifest['ci_url'], 'token': transaction['token']}
    u.atomic_json(directory / 'state.json', state)
    choice = u.activation_choice()
    if choice == 'later':
        print('VPS candidate retained; active system and boot default are unchanged.')
        return
    print('Backing up VPS application state before activation…', flush=True)
    remote('backup', {'token': transaction['token']}, helper, timeout=1950)
    offsite_backup(directory, remote('status', helper=helper), helper)
    state['activation_intent'] = {**state['pending_system'], 'choice': choice}
    u.atomic_json(directory / 'state.json', state)
    remote('begin', {'token': transaction['token'], 'choice': choice}, helper)
    print('Server-side recovery armed. Waiting for activation…', flush=True)
    deadline = time.monotonic() + 650
    while time.monotonic() < deadline:
        status = remote('status', helper=helper)
        if status.get('token') != transaction['token']:
            raise u.UpdateError('VPS transaction changed during activation.')
        if status.get('phase') == 'boot_pending':
            print('Scheduled for next boot. After reboot, run up-vps-confirm within 15 minutes. No reboot requested.')
            return
        if status.get('phase') == 'awaiting_confirmation':
            break
        if status.get('phase') in {'rolled_back', 'rollback_failed', 'rolling_back'}:
            raise u.UpdateError('VPS activation failed; inspect up-vps-status and its retained backup.')
        time.sleep(3)
    else:
        raise u.UpdateError('Activation did not finish; the VPS recovery timer remains armed.')
    # Allow services and certificate issuance to settle; failures never disarm recovery.
    last_error = None
    for _ in range(20):
        try:
            public_health(helper)
            confirm(directory, helper, verify=False, expected=state['pending_system'])
            return
        except (subprocess.CalledProcessError, OSError, ValueError, u.UpdateError) as error:
            last_error = error
            time.sleep(5)
    remote('rollback', {'token': transaction['token']}, helper, timeout=300)
    raise u.UpdateError(f'VPS health checks failed; software rollback requested: {last_error}')


def dispatch(command, repo, directory):
    if command == 'up-vps':
        update(repo, directory)
    else:
        with ssh_session():
            inspect_deployment(command, directory)


def inspect_deployment(command, directory):
    pending = u.read_state(directory).get('pending_system', {}).get('path', '')
    helper = '/run/current-system/sw/bin/dotfiles-vps-control'
    if u.STORE_PATH.fullmatch(pending) and '-nixos-system-ahimsa-vps-' in pending:
        # Remains usable after bootstrap rolls back to a system without this helper.
        helper = pending + '/sw/bin/dotfiles-vps-control'
    if command == 'status-vps':
        status = remote('status', helper=helper)
        assert_host(status)
        print(json.dumps({'local': u.read_state(directory), 'remote': status}, indent=2))
    elif command == 'confirm-vps':
        confirm(directory, helper)
    elif command == 'rollback-vps':
        status = remote('status', helper=helper)
        assert_host(status)
        if input('Restore the previous VPS configuration? [y/N]: ').strip().lower() != 'y':
            return
        remote('rollback', {'token': status.get('token')}, helper, timeout=300)
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            current = remote('status', helper=helper)
            if current.get('token') != status.get('token'):
                raise u.UpdateError('VPS transaction changed during rollback.')
            if current.get('phase') == 'rolled_back':
                print('VPS software rollback completed. Databases were not restored; inspect the retained backup if needed.')
                return
            if current.get('phase') == 'rollback_failed':
                raise u.UpdateError('VPS rollback failed; inspect up-vps-status and the provider console.')
            time.sleep(3)
        raise u.UpdateError('Rollback is still pending; inspect up-vps-status.')
