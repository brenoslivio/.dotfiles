#!/usr/bin/env python3
"""Render untrusted inventory data using trusted main-branch code; never execute artifacts."""
import html
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile

import update as u

START = '<!-- package-report:start -->'
END = '<!-- package-report:end -->'
HOSTS = ('ahimsa', 'ahimsa-vps')
BRANCH = 'automation/flake-update'


def cell(value):
    text = re.sub(r'\s+', ' ', str(value)).strip()
    text = re.sub(r'([\\\[\]()*_!])', r'\\\1', text[:220])
    return html.escape(text).replace('|', '&#124;').replace('`', '&#96;').replace('@', '&#64;')


def validate_inventory(data, host, run, pr=None):
    expected = {'schema': 1, 'repository': u.REPOSITORY, 'host': host,
        'run_id': str(run['id']), 'attempt': str(run['run_attempt']),
        'event': 'pull_request' if pr else 'push',
        'head': pr['head']['sha'] if pr else run['head_sha'],
        'base': pr['base']['sha'] if pr else None,
        'revision': pr['merge_commit_sha'] if pr else run['head_sha']}
    if any(data.get(key) != value for key, value in expected.items()):
        raise ValueError('Inventory revision, host or run does not match')
    packages = data.get('packages')
    if not isinstance(packages, dict) or len(packages) > 100000:
        raise ValueError('Invalid package inventory')
    for name, item in packages.items():
        if not isinstance(name, str) or len(name) > 250 or not isinstance(item, dict):
            raise ValueError('Invalid package entry')
        for field in ('versions', 'paths'):
            values = item.get(field)
            if not isinstance(values, list) or len(values) > 200 or not all(isinstance(v, str) and len(v) < 500 for v in values):
                raise ValueError('Invalid package versions/paths')
        if not all(u.STORE_PATH.fullmatch(path) for path in item['paths']):
            raise ValueError('Invalid package path')
        if not isinstance(item.get('bytes'), int) or not 0 <= item['bytes'] <= 10**15:
            raise ValueError('Invalid package size')
    return packages


def inventory(host, run, pr=None):
    name = f"packages-{host}-{run['run_attempt']}"
    artifacts = [a for a in u.pages(f"actions/runs/{run['id']}/artifacts", 'artifacts')
                 if a['name'] == name and not a['expired']]
    if len(artifacts) != 1:
        raise ValueError('Package inventory missing or expired')
    if artifacts[0].get('size_in_bytes', 0) > 5_000_000:
        raise ValueError('Inventory archive too large')
    raw = u.api(f"actions/artifacts/{artifacts[0]['id']}/zip", binary=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != ['package-inventory.json']:
            raise ValueError('Unexpected inventory archive')
        if archive.getinfo('package-inventory.json').file_size > 5_000_000:
            raise ValueError('Inventory too large')
        return validate_inventory(json.loads(archive.read('package-inventory.json')), host, run, pr)


def differences(before, after, host):
    result = []
    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name, {}), after.get(name, {})
        a, b = sorted(set(old.get('versions', []))), sorted(set(new.get('versions', [])))
        if a == b and old.get('paths') == new.get('paths'):
            continue
        kind = 'Added' if not old else 'Removed' if not new else 'Rebuilt' if a == b else 'Version change'
        result.append({'package': name, 'hosts': [host], 'before': a, 'after': b, 'kind': kind,
                       'size_delta': new.get('bytes', 0) - old.get('bytes', 0)})
    return result


def combine(rows):
    result = {}
    for row in rows:
        key = (row['package'], tuple(row['before']), tuple(row['after']), row['kind'], row['size_delta'])
        if key in result:
            result[key]['hosts'].extend(row['hosts'])
        else:
            result[key] = dict(row, hosts=list(row['hosts']))
    return sorted(result.values(), key=lambda row: row['package'])


def short_note(body):
    # A bounded upstream excerpt, not an invented/AI-generated release claim.
    for line in body.splitlines():
        line = re.sub(r'^\s*[-*+]\s*', '', line).strip()
        line = re.sub(r'\[([^]]+)\]\([^)]*\)', r'\1', line)
        line = re.sub(r'<[^>]*>|https?://\S+', '', line)
        line = line.replace('**', '').replace('`', '')
        line = re.sub(r'^[0-9a-f]{7,40}\s+', '', line)
        # Match change verbs, including scoped bullets, not words like "Additionally".
        if not re.match(r'(?i)^(?:[\w./()-]+:\s*)?(?:fix(?:ed|es)?|add(?:ed|s)?|'
                        r'improv(?:e|ed|es|ements?)|support(?:ed|s)?|updat(?:e|ed|es)|'
                        r'security|resolv(?:e|ed|es)|prevent(?:ed|s)?|correct(?:ed|s)?|'
                        r'chang(?:e|ed|es)|remov(?:e|ed|es|al))\b', line):
            continue
        line = re.sub(r'\s+by\s+@\S+.*$', '', line)
        line = re.sub(r'\s+', ' ', line).strip()
        return ' '.join(line.split()[:18])[:130]
    return None


class ReleaseNotes:
    def __init__(self, sources):
        self.sources, self.cache = sources, {}
        self.deadline = time.monotonic() + 90

    def get(self, row):
        if row['kind'] == 'Rebuilt':
            return 'Rebuilt; version unchanged. Packaging or dependency change.', None
        if row['kind'] == 'Removed':
            return 'Removed from this configuration.', None
        source = self.sources.get(row['package'])
        versions = sorted(set(row['after']) - set(row['before']) - {''})
        # Helper derivations may append suffixes to the same upstream version.
        versions = [v for v in versions if not any(v == base + suffix for base in versions
            for suffix in ('-bin', '-dev', '-doc', '-man', '-fish-completions', '-modules'))]
        if not source or len(versions) != 1 or not re.fullmatch(r'[0-9][A-Za-z0-9.+_-]*', versions[0]):
            return 'No upstream release notes available.', None
        version = versions[0]
        if 'url' in source:
            return 'Release-note summary unavailable; see upstream notes.', source['url'].format(version=version, major=version.split('.')[0])
        repo = source['repo']
        key = (repo, version)
        if key in self.cache:
            return self.cache[key]
        fallback = ('No upstream release notes available.', f'https://github.com/{repo}/releases')
        for pattern in source['tags']:
            if time.monotonic() >= self.deadline:
                break
            tag = pattern.format(version=version)
            url = f'https://api.github.com/repos/{repo}/releases/tags/{urllib.parse.quote(tag, safe="")}'
            try:
                request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'dotfiles-package-report'})
                with urllib.request.urlopen(request, timeout=5) as response:
                    release = json.loads(response.read(1_000_001))
                if release.get('draft') or release.get('tag_name') != tag:
                    continue
                note = short_note(release.get('body') or '')
                # Explicitly label the target release: this does not claim to cover skipped releases.
                result = (f'{version}: {note}' if note else 'Release-note summary unavailable; see upstream notes.',
                          f'https://github.com/{repo}/releases/tag/{urllib.parse.quote(tag, safe="")}')
                self.cache[key] = result
                return result
            except (OSError, ValueError):
                continue
        self.cache[key] = fallback
        return fallback


def table(rows):
    lines = ['| Package | Host | Before → After | Release note |', '|---|---|---|---|']
    for row in rows:
        old = ', '.join(v or '(unversioned)' for v in row['before']) or '—'
        new = ', '.join(v or '(unversioned)' for v in row['after']) or '—'
        hosts = 'Both' if set(row['hosts']) == set(HOSTS) else ', '.join(row['hosts'])
        note = cell(row['note'])
        if row.get('url'):
            note += f" [Upstream]({row['url']})"
        lines.append(f"| {cell(row['package'])} | {hosts} | {cell(old)} → {cell(new)} | {note} |")
    return '\n'.join(lines)


def replace_section(body, section):
    block = f'{START}\n{section}\n{END}'
    if START not in body and END not in body:
        return body.rstrip() + '\n\n' + block + '\n'
    if body.count(START) != 1 or body.count(END) != 1 or body.index(START) > body.index(END):
        raise ValueError('Ambiguous generated section; preserving PR body')
    return body[:body.index(START)] + block + body[body.index(END)+len(END):]


def find_pr(run):
    candidates = u.api_json(f'pulls?state=open&base=main&head=brenoslivio:{BRANCH}')
    for candidate in candidates:
        pr = u.api_json(f"pulls/{candidate['number']}")
        if (pr['head']['repo']['full_name'] == u.REPOSITORY and pr['head']['sha'] == run['head_sha']
                and pr['head']['ref'] == BRANCH and pr['state'] == 'open'):
            return pr
    return None


def render():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    run = u.api_json(f"actions/runs/{event['workflow_run']['id']}")
    workflow = u.api_json('actions/workflows/ci.yml')
    if (run['workflow_id'] != workflow['id'] or run['path'] != '.github/workflows/ci.yml'
            or run['event'] != 'pull_request' or run['status'] != 'completed'
            or run['head_repository']['full_name'] != u.REPOSITORY or run['head_branch'] != BRANCH):
        raise ValueError('Not a trusted weekly PR CI run')
    pr = find_pr(run)
    if pr is None:
        return
    baselines = u.pages(f"actions/workflows/ci.yml/runs?event=push&branch=main&head_sha={pr['base']['sha']}", 'workflow_runs')
    baselines = [r for r in baselines if r['status'] == 'completed' and r['conclusion'] == 'success']
    baseline = max(baselines, key=lambda r: (r['id'], r['run_attempt'])) if baselines else None
    if baseline:
        u.validate_run(workflow, baseline, pr['base']['sha'])
    rows, warnings = [], []
    for host in HOSTS:
        try:
            if baseline is None:
                raise ValueError('No successful main baseline')
            rows.extend(differences(inventory(host, baseline), inventory(host, run, pr), host))
        except (ValueError, KeyError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
            warnings.append(f'{host}: comparison unavailable ({type(error).__name__}). Main CI must first publish an inventory for the exact base; failed/missing PR builds are not treated as unchanged.')
    rows = combine(rows)
    sources = json.loads(Path('config/release-sources.json').read_text())
    notes = ReleaseNotes(sources)
    # Prioritize applications before spending the bounded release-note request budget.
    rows.sort(key=lambda r: (r['package'] not in sources, r['package']))
    for row in rows:
        row['note'], row['url'] = notes.get(row)
    primary = [r for r in rows if r['package'] in sources]
    other = [r for r in rows if r['package'] not in sources]
    prefix = f"Package comparison: `{pr['base']['sha'][:12]}` → `{pr['head']['sha'][:12]}` (PR build).\n\n"
    prefix += '\n\n'.join(warnings) + ('\n\n' if warnings else '')
    if not rows and not warnings:
        prefix += 'No runtime package changes.\n'
    section = prefix + (table(primary[:40]) + '\n\n' if primary else '')
    if other:
        section += f'<details><summary>Dependencies and rebuilds ({len(other)})</summary>\n\n{table(other[:60])}\n\n</details>\n'
    section += (f'\n{len(rows)} changed package groups. Notes describe the target release; upstream links provide the full changelog. '
                f"[Complete tables and JSON](https://github.com/{u.REPOSITORY}/actions/runs/{os.environ['GITHUB_RUN_ID']})\n")
    directory = Path('package-report')
    directory.mkdir(exist_ok=True)
    (directory/'report.md').write_text(prefix + table(rows) + '\n')
    (directory/'packages.json').write_text(json.dumps(rows, indent=2) + '\n')
    (directory/'publication.json').write_text(json.dumps({'number': pr['number'], 'base': pr['base']['sha'], 'head': pr['head']['sha'], 'section': section}))


def publish():
    path = Path('package-report/publication.json')
    if not path.exists():
        return
    data = json.loads(path.read_text())
    pr = u.api_json(f"pulls/{data['number']}")
    if (pr['state'] != 'open' or pr['base']['sha'] != data['base'] or pr['head']['sha'] != data['head']
            or pr['head']['ref'] != BRANCH or pr['head']['repo']['full_name'] != u.REPOSITORY):
        print('Skipped outdated report')
        return
    body = replace_section(pr.get('body') or '', data['section'])
    if len(body) > 60000:
        raise ValueError('PR body too large; full report remains available as an artifact')
    subprocess.run(['gh', 'api', '--method', 'PATCH', f'repos/{u.REPOSITORY}/pulls/{pr["number"]}', '--input', '-'],
                   input=json.dumps({'body': body}), text=True, stdout=subprocess.DEVNULL, check=True)


if __name__ == '__main__':
    if sys.argv[1] == 'render':
        render()
    elif sys.argv[1] == 'publish':
        publish()
    else:
        raise SystemExit('Use render or publish')
