#!/usr/bin/env python3
"""Deploy a successful main CI revision, after uploading an encrypted state backup."""
import json
import os
from pathlib import Path
import subprocess
import sys

import update as u
import vps_update as vps


def current_main(sha):
    return u.api_json('git/ref/heads/main')['object']['sha'] == sha


def verified_manifest():
    if os.environ.get('GITHUB_EVENT_NAME') != 'workflow_run' or os.environ.get('GITHUB_REPOSITORY') != u.REPOSITORY:
        raise u.UpdateError('Automatic deployment requires the trusted workflow_run context.')
    sha = os.environ['CI_SHA']
    if not u.SHA.fullmatch(sha):
        raise u.UpdateError('Invalid triggering revision.')
    if not current_main(sha):
        print('Skipped: main has advanced beyond this CI revision.')
        return None
    manifest = u.evidence(sha, vps.HOST)
    if (manifest['run_id'], manifest['run_attempt']) != (os.environ['CI_RUN_ID'], os.environ['CI_RUN_ATTEMPT']):
        raise u.UpdateError('Evidence does not match the triggering CI run and attempt.')
    if u.git(Path.cwd(), 'rev-parse', 'HEAD') != sha:
        raise u.UpdateError('Checkout is not the tested commit.')
    return manifest


def output(name, value):
    with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
        stream.write(f'{name}={value}\n')


def prepare(directory, manifest):
    sha = manifest['sha']
    path = u.build_candidate(Path.cwd(), sha, manifest, directory, False, vps.HOST)
    if not current_main(sha):
        print('Skipped: main advanced during the build.')
        return
    pending = vps.prepare_deployment(path, sha, manifest, directory)
    if pending is None:
        return
    helper = path + '/sw/bin/dotfiles-vps-control'
    vps.remote('backup', {'token': pending['token']}, helper, timeout=1950)
    status = vps.remote('status', helper=helper)
    if any(status.get(key) != pending[key] for key in ('token', 'path', 'sha')):
        raise u.UpdateError('VPS transaction changed during backup.')
    backup = vps.offsite_backup(directory, status, helper, acknowledge=False)
    if backup is None:
        raise u.UpdateError('Automatic deployment requires a media state backup.')
    encrypted = directory / 'encrypted'
    encrypted.mkdir(mode=0o700, exist_ok=True)
    subprocess.run(['age', '-R', 'config/vps-backup-recipients.txt', '-o',
                    str(encrypted / (backup.name + '.age')), str(backup)], check=True)
    output('prepared', 'true')


def verify_backup_upload(artifact_id):
    if not artifact_id.isdecimal():
        raise u.UpdateError('Encrypted backup upload must finish before activation.')
    artifact = u.api_json('actions/artifacts/' + artifact_id)
    expected_name = f"vps-backup-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    if (artifact.get('expired') or artifact.get('name') != expected_name
            or str(artifact.get('workflow_run', {}).get('id')) != os.environ['GITHUB_RUN_ID']
            or artifact.get('size_in_bytes', 0) <= 0):
        raise u.UpdateError('Uploaded backup does not belong to this deployment.')


def activate(directory, manifest):
    pending = u.read_state(directory)['pending_system']
    if pending['sha'] != manifest['sha'] or pending['path'] != manifest['system_path']:
        raise u.UpdateError('Prepared deployment differs from CI evidence.')
    verify_backup_upload(os.environ.get('BACKUP_ARTIFACT_ID', ''))
    if not current_main(pending['sha']):
        print('Skipped: main advanced before activation; backup retained.')
        return
    helper = pending['path'] + '/sw/bin/dotfiles-vps-control'
    status = vps.remote('status', helper=helper)
    if any(status.get(key) != pending[key] for key in ('token', 'path', 'sha')):
        raise u.UpdateError('VPS transaction changed before backup acknowledgement.')
    vps.offsite_backup(directory, status, helper)
    vps.activate_prepared(directory)
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
        stream.write(f"Deployed `{pending['sha']}` to `ahimsa-vps`; SSH, services and public HTTPS passed. No reboot.\n")


def main():
    os.umask(0o077)
    action = sys.argv[1]
    if action not in {'verify', 'prepare', 'activate'}:
        raise u.UpdateError('Unknown deployment phase.')
    manifest = verified_manifest()
    if action == 'verify':
        output('current', 'true' if manifest else 'false')
        return
    if manifest is None:
        return
    directory = Path(os.environ['RUNNER_TEMP']) / 'vps-deploy'
    directory.mkdir(mode=0o700, exist_ok=True)
    if action == 'prepare':
        prepare(directory, manifest)
    else:
        activate(directory, manifest)


if __name__ == '__main__':
    try:
        main()
    except (u.UpdateError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'VPS deployment stopped: {error}', file=sys.stderr)
        sys.exit(1)
