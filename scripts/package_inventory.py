#!/usr/bin/env python3
"""Record actual runtime store closures, without building anything."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def collect(host, flake):
    attributes = [f'nixosConfigurations.{host}.config.system.build.toplevel']
    if host == 'ahimsa':
        attributes.append('homeConfigurations.brenoslivio.activationPackage')
    roots = [command('nix', 'eval', '--raw', '--no-update-lock-file', '--no-write-lock-file',
                     f'{flake}#{attribute}.outPath') for attribute in attributes]
    return closure_packages(roots)


def closure_packages(roots):
    paths = json.loads(command('nix', 'path-info', '--json', '--recursive', *roots))
    # Derivation names unify outputs such as systemd-262 and systemd-262-man.
    identities = {path: (Path(info['deriver']).name[33:-4]
                        if (info.get('deriver') or '').endswith('.drv') else Path(path).name[33:])
                  for path, info in paths.items()}
    names = sorted(set(identities.values()))
    # Use Nix's own name/version parsing, including multiple installed versions.
    with tempfile.NamedTemporaryFile('w', suffix='.json') as stream:
        json.dump(names, stream)
        stream.flush()
        parsed = json.loads(command('nix', 'eval', '--json', '--impure', '--expr',
            'map builtins.parseDrvName (builtins.fromJSON (builtins.readFile '
            + json.dumps(stream.name) + '))'))
    by_name = dict(zip(names, parsed))
    packages = {}
    for path, info in paths.items():
        identity = by_name[identities[path]]
        item = packages.setdefault(identity['name'], {'versions': [], 'paths': [], 'bytes': 0})
        item['versions'].append(identity['version'])
        item['paths'].append(path)
        item['bytes'] += info['narSize']
    for item in packages.values():
        item['versions'] = sorted(set(item['versions']))
        item['paths'].sort()
    return packages


def main():
    host = sys.argv[1]
    if host not in {'ahimsa', 'ahimsa-vps'}:
        raise SystemExit('Unknown host')
    sha = os.environ['GITHUB_SHA']
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    pr = event.get('pull_request', {})
    flake = f"git+{Path.cwd().as_uri()}?rev={sha}"
    inventory = {'schema': 1, 'repository': os.environ['GITHUB_REPOSITORY'], 'host': host,
        'revision': sha, 'head': pr.get('head', {}).get('sha', sha),
        'base': pr.get('base', {}).get('sha'), 'event': os.environ['GITHUB_EVENT_NAME'],
        'run_id': os.environ['GITHUB_RUN_ID'], 'attempt': os.environ['GITHUB_RUN_ATTEMPT'],
        'packages': collect(host, flake)}
    Path('package-inventory.json').write_text(json.dumps(inventory, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
