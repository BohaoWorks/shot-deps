import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import shot_deps as sd


class ShotDepsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'asset.txt').write_text('synthetic', encoding='utf-8')
        self.data = {'version': 1, 'assets': {'hero': {'path': 'asset.txt'}},
                     'shots': {'A': {'assets': ['hero'], 'needs': []},
                               'B': {'assets': [], 'needs': ['A']}}}

    def run_check(self):
        return sd.analyze(self.data, self.root)

    def test_layers(self):
        result = self.run_check()
        self.assertTrue(result['ok'])
        self.assertEqual(result['runnable_layers'], [['A'], ['B']])

    def test_missing_propagates(self):
        (self.root / 'asset.txt').unlink()
        result = self.run_check()
        self.assertEqual(set(result['blocked']), {'A', 'B'})
        self.assertIn('blocked_shot:A', result['blocked']['B'])

    def test_hash_match(self):
        self.data['assets']['hero']['sha256'] = hashlib.sha256(b'synthetic').hexdigest().upper()
        self.assertTrue(self.run_check()['ok'])

    def test_changed_hash_impact(self):
        self.data['assets']['hero']['sha256'] = '0' * 64
        self.assertEqual(self.run_check()['impacted_shots'], ['A', 'B'])

    def test_manual_impact(self):
        result = sd.analyze(self.data, self.root, ['hero'])
        self.assertTrue(result['ok'])
        self.assertEqual(result['impacted_shots'], ['A', 'B'])

    def test_unknown_change(self):
        with self.assertRaises(sd.ManifestError):
            sd.analyze(self.data, self.root, ['typo'])

    def test_unknown_asset(self):
        self.data['shots']['A']['assets'] = ['unknown']
        self.assertIn('unknown_asset:unknown', self.run_check()['blocked']['A'])

    def test_unknown_shot(self):
        self.data['shots']['A']['needs'] = ['unknown']
        self.assertEqual(set(self.run_check()['blocked']), {'A', 'B'})

    def test_cycle_and_downstream(self):
        self.data['shots']['A']['needs'] = ['B']
        self.data['shots']['C'] = {'assets': [], 'needs': ['B']}
        self.assertEqual(self.run_check()['cycle_or_downstream'], ['A', 'B', 'C'])

    def test_self_cycle(self):
        self.data['shots']['A']['needs'] = ['A']
        self.assertFalse(self.run_check()['ok'])

    def test_independent_shot_survives(self):
        self.data['shots']['A']['needs'] = ['A']
        self.data['shots']['C'] = {'assets': [], 'needs': []}
        self.assertEqual(self.run_check()['runnable_layers'], [['C']])

    def test_long_chain(self):
        self.data['shots'] = {str(i): {'assets': [], 'needs': [str(i-1)] if i else []}
                              for i in range(2500)}
        self.assertEqual(len(self.run_check()['runnable_layers']), 2500)

    def test_empty(self):
        self.assertTrue(sd.analyze({'version': 1, 'assets': {}, 'shots': {}}, self.root)['ok'])

    def test_unused_missing_asset_fails(self):
        self.data['assets']['unused'] = {'path': 'missing'}
        result = self.run_check()
        self.assertFalse(result['ok'])
        self.assertEqual(result['unused_assets'], ['unused'])
        self.assertEqual(result['blocked'], {})

    def test_unsafe_paths(self):
        for path in ('../secret', '/secret', 'C:/secret', r'folder\secret', '//host/file', '\x00'):
            with self.subTest(path=path), self.assertRaises(sd.ManifestError):
                self.data['assets']['hero']['path'] = path
                self.run_check()

    def test_external_symlink(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / 'secret.txt'
            target.write_text('synthetic')
            try:
                (self.root / 'link.txt').symlink_to(target)
            except OSError:
                self.skipTest('symlink creation unavailable')
            self.data['assets']['hero']['path'] = 'link.txt'
            self.assertEqual(self.run_check()['asset_status']['hero'], 'outside_root')

    def test_bad_shapes(self):
        bad = [None, [], {}, {'version': True, 'assets': {}, 'shots': {}},
               {'version': 1, 'assets': [], 'shots': {}}]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(sd.ManifestError):
                sd.analyze(value, self.root)

    def test_bad_fields(self):
        for field, value in [('assets', ['hero', 'hero']), ('needs', 'A'), ('needs', [3])]:
            data = copy.deepcopy(self.data)
            data['shots']['A'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(sd.ManifestError):
                sd.analyze(data, self.root)

    def test_bad_hash(self):
        self.data['assets']['hero']['sha256'] = 'not-a-hash'
        with self.assertRaises(sd.ManifestError):
            self.run_check()

    def test_duplicate_json_key(self):
        path = self.root / 'duplicate.json'
        path.write_text('{"version":1,"version":1}')
        with self.assertRaises(sd.ManifestError):
            sd.read_manifest(path)

    def test_cli_from_different_directory(self):
        manifest = self.root / 'project.json'
        manifest.write_text(json.dumps(self.data))
        script = str(Path(sd.__file__).resolve())
        process = subprocess.run([sys.executable, script, str(manifest), '--json'],
                                 cwd=self.root.parent, capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertTrue(json.loads(process.stdout)['ok'])

    def test_cli_blocked_and_malformed(self):
        script = str(Path(sd.__file__).resolve())
        manifest = self.root / 'project.json'
        (self.root / 'asset.txt').unlink()
        manifest.write_text(json.dumps(self.data))
        for content, code in [(json.dumps(self.data), 1), ('invalid json', 2)]:
            manifest.write_text(content)
            process = subprocess.run([sys.executable, script, str(manifest), '--json'],
                                     capture_output=True, text=True)
            self.assertEqual(process.returncode, code)
            self.assertFalse(json.loads(process.stdout)['ok'])


if __name__ == '__main__':
    unittest.main()
