import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import package_report as r

SHA = 'a'*40
STORE = '/nix/store/'+'a'*32+'-jellyfin-1.0'
RUN = {'id': 1, 'run_attempt': 2, 'head_sha': SHA}
DATA = {'schema': 1, 'repository': r.u.REPOSITORY, 'host': 'ahimsa-vps', 'run_id': '1',
        'attempt': '2', 'head': SHA, 'base': None, 'revision': SHA, 'event': 'push',
        'packages': {'jellyfin': {'versions': ['1.0'], 'paths': [STORE], 'bytes': 123}}}


class ReportTests(unittest.TestCase):
    def test_identity_and_untrusted_paths(self):
        self.assertEqual(r.validate_inventory(DATA, 'ahimsa-vps', RUN), DATA['packages'])
        for key, value in [('host', 'ahimsa'), ('revision', 'b'*40), ('attempt', '1'), ('repository', 'other/repo')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                r.validate_inventory({**DATA, key: value}, 'ahimsa-vps', RUN)
        bad = copy.deepcopy(DATA)
        bad['packages']['jellyfin']['paths'] = ['/tmp/evil']
        with self.assertRaises(ValueError):
            r.validate_inventory(bad, 'ahimsa-vps', RUN)

    def test_pr_inventory_is_bound_to_head_base_and_merge(self):
        pr = {'head': {'sha': 'b'*40}, 'base': {'sha': SHA}, 'merge_commit_sha': 'c'*40}
        data = {**DATA, 'head': 'b'*40, 'base': SHA, 'revision': 'c'*40, 'event': 'pull_request'}
        r.validate_inventory(data, 'ahimsa-vps', RUN, pr)
        with self.assertRaises(ValueError):
            r.validate_inventory({**data, 'base': 'd'*40}, 'ahimsa-vps', RUN, pr)

    def test_version_add_remove_rebuild_and_unchanged(self):
        before = DATA['packages']
        self.assertEqual(r.differences(before, before, 'ahimsa'), [])
        after = copy.deepcopy(before)
        after['jellyfin']['paths'] = [STORE.replace('a'*32, 'b'*32)]
        self.assertEqual(r.differences(before, after, 'ahimsa')[0]['kind'], 'Rebuilt')
        after['jellyfin']['versions'] = ['2.0']
        row = r.differences(before, after, 'ahimsa')[0]
        self.assertEqual(row['kind'], 'Version change')
        self.assertEqual(r.differences({}, after, 'ahimsa')[0]['kind'], 'Added')
        self.assertEqual(r.differences(before, {}, 'ahimsa')[0]['kind'], 'Removed')
        self.assertEqual(r.combine([row, {**row, 'hosts': ['ahimsa-vps']}])[0]['hosts'], list(r.HOSTS))

    def test_generated_section_preserves_manual_notes(self):
        body = f'User note\n{r.START}\nold\n{r.END}\nMore notes'
        self.assertEqual(r.replace_section(body, 'new'), body.replace('old', 'new'))
        with self.assertRaises(ValueError):
            r.replace_section(body+r.START, 'new')

    def test_artifact_archive_cannot_extract_arbitrary_files(self):
        import io, zipfile
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('../../script.py', 'unsafe')
        with patch.object(r.u, 'pages', return_value=[{'name': 'packages-ahimsa-vps-2', 'expired': False, 'id': 2}]), patch.object(r.u, 'api', return_value=stream.getvalue()):
            with self.assertRaises(ValueError):
                r.inventory('ahimsa-vps', RUN)

    def test_unavailable_notes_are_honest_and_rebuilds_do_not_fetch(self):
        notes = r.ReleaseNotes({})
        with patch.object(r.urllib.request, 'urlopen') as fetch:
            self.assertIn('No upstream', notes.get({'package': 'unknown', 'kind': 'Added', 'before': [], 'after': ['1.0']})[0])
            self.assertIn('version unchanged', notes.get({'kind': 'Rebuilt'})[0])
            fetch.assert_not_called()
        self.assertIsNone(r.short_note('Release v2.0\nSee changelog'))
        self.assertEqual(r.short_note('- Fix playback crashes'), 'Fix playback crashes')

    def test_table_cells_do_not_inject_markdown(self):
        safe = r.cell('evil | <script> @everyone ![x](https://evil.invalid)\nnext')
        self.assertNotIn('<script>', safe)
        self.assertNotIn('@everyone', safe)
        self.assertNotIn('![x]', safe)
        self.assertNotIn('|', safe)

    def test_stale_publication_does_not_mutate_pr(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = {'number': 5, 'head': SHA, 'base': SHA, 'section': 'new'}
            path = Path(tmp)/'publication.json'
            path.write_text(json.dumps(data))
            with patch.object(r, 'Path', return_value=path), patch.object(r.u, 'api_json', return_value={'state': 'closed'}), patch.object(r.subprocess, 'run') as command:
                r.publish()
                command.assert_not_called()

    def test_failed_upstream_lookup_keeps_version_comparison(self):
        notes = r.ReleaseNotes({'jellyfin': {'repo': 'jellyfin/jellyfin', 'tags': ['v{version}']}})
        row = {'package': 'jellyfin', 'kind': 'Version change', 'before': ['1.0'], 'after': ['2.0']}
        with patch.object(r.urllib.request, 'urlopen', side_effect=OSError('offline')):
            note, url = notes.get(row)
        self.assertIn('No upstream', note)
        self.assertEqual(url, 'https://github.com/jellyfin/jellyfin/releases')
        output = r.table([{**row, 'hosts': ['ahimsa-vps'], 'note': note, 'url': url}])
        self.assertIn('1.0 → 2.0', output)

    def test_missing_baseline_is_not_reported_as_unchanged(self):
        import os
        run = {**RUN, 'workflow_id': 10, 'path': '.github/workflows/ci.yml', 'event': 'pull_request',
               'status': 'completed', 'head_repository': {'full_name': r.u.REPOSITORY}, 'head_branch': r.BRANCH}
        pr = {'number': 5, 'head': {'sha': 'b'*40}, 'base': {'sha': SHA}, 'merge_commit_sha': 'c'*40}
        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            try:
                os.chdir(tmp)
                Path('event.json').write_text(json.dumps({'workflow_run': {'id': 1}}))
                Path('config').mkdir()
                Path('config/release-sources.json').write_text('{}')
                with patch.dict(os.environ, {'GITHUB_EVENT_PATH': 'event.json', 'GITHUB_RUN_ID': '99'}), patch.object(r.u, 'api_json', side_effect=[run, {'id': 10}]), patch.object(r, 'find_pr', return_value=pr), patch.object(r.u, 'pages', return_value=[]):
                    r.render()
                body = json.loads(Path('package-report/publication.json').read_text())['section']
                self.assertIn('comparison unavailable', body)
                self.assertNotIn('No runtime package changes', body)
            finally:
                os.chdir(old)

    def test_inventory_groups_outputs_by_derivation_name(self):
        import package_inventory as inventory
        paths = {STORE: {'deriver': STORE+'.drv', 'narSize': 123},
                 STORE+'-man': {'deriver': STORE+'.drv', 'narSize': 10},
                 STORE+'-source': {'deriver': None, 'narSize': 1}}
        parsed = [{'name': 'jellyfin', 'version': '1.0'}, {'name': 'jellyfin', 'version': '1.0-source'}]
        with patch.object(inventory, 'command', side_effect=[json.dumps(paths), json.dumps(parsed)]):
            packages = inventory.closure_packages(['/run/current-system'])
        self.assertEqual(packages['jellyfin']['versions'], ['1.0', '1.0-source'])
        self.assertEqual(packages['jellyfin']['bytes'], 134)

    def test_notes_ignore_thanks_and_read_scoped_changes(self):
        self.assertIsNone(r.short_note('Additionally, thank you to everyone who donated!'))
        self.assertEqual(r.short_note('* config/lua: fix expired window references by @author in https://example.invalid/123'),
                         'config/lua: fix expired window references')
        self.assertEqual(r.short_note('* [3f28a79](https://example.invalid/commit) Fixed: Wildcard IP addresses in Allowed Hosts'),
                         'Fixed: Wildcard IP addresses in Allowed Hosts')
