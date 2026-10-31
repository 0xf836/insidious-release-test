"""CI policy regressions: fail closed on missing targets, jobs and identity."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('checks', ROOT / 'tools/ci/checks.py')
checks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checks)


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.platforms = json.loads((ROOT / 'packaging/platforms.json').read_text())

    def test_titles(self):
        for title in ['fix: restore zoom', 'feat(viewer)!: change zoom policy', 'ci: add builds', 'chore(master): release 0.1.0']:
            self.assertTrue(checks.conventional_title(title), title)
        for title in ['Fix zoom', 'fix: ', 'fix:zoom', 'feat(): zoom', 'fix: zoom\nextra', 'fix: zoom\n']:
            self.assertFalse(checks.conventional_title(title), title)

    def test_pr_title_is_advisory_and_never_blocks_validation(self):
        for title in ['fix: restore zoom', 'Fix zoom please',
                      '$(touch unexpected)\n::error::untrusted title']:
            with self.subTest(title=title), tempfile.TemporaryDirectory() as directory:
                event = Path(directory) / 'event.json'
                event.write_text(json.dumps({'pull_request': {'title': title}}))
                env = dict(os.environ, GITHUB_EVENT_NAME='pull_request',
                           GITHUB_EVENT_PATH=str(event), GITHUB_REF='refs/pull/1/merge')
                env.pop('GITHUB_OUTPUT', None)
                for command in ['validate', 'title-hint']:
                    result = subprocess.run(
                        [sys.executable, str(ROOT / 'tools/ci/checks.py'), command],
                        env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    if command == 'validate':
                        self.assertIn('include', json.loads(result.stdout))
                    else:
                        self.assertEqual('::notice' in result.stdout,
                                         not checks.conventional_title(title))
                        self.assertNotIn('::error::', result.stdout)

    def test_matrix(self):
        rows = checks.build_matrix(self.platforms)['include']
        self.assertEqual({r['target'] for r in rows}, {'arch-x86_64', 'fedora44-x86_64'})

    def test_bad_matrices(self):
        for mutation in ['empty', 'unpinned', 'duplicate', 'missing-mandatory', 'wrong-image', 'digest']:
            data = copy.deepcopy(self.platforms)
            if mutation == 'empty':
                data['platforms'] = []
            elif mutation == 'unpinned':
                data['platforms'][0]['ci_image'] = 'archlinux:base'
            elif mutation == 'duplicate':
                data['platforms'].append(data['platforms'][0])
            elif mutation == 'missing-mandatory':
                data['platforms'][0].update(release_required=True, selected_for_future_qualification=False)
            elif mutation == 'wrong-image':
                data['platforms'][0]['ci_image'] = data['platforms'][1]['ci_image']
            else:
                data['platforms'][0]['image_digest'] = 'sha256:' + '0' * 64
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                checks.build_matrix(data)

    def test_aggregate(self):
        passed = {name: {'result': 'success'} for name in ['validation', 'builds']}
        self.assertTrue(checks.aggregate(passed))
        self.assertFalse(checks.aggregate({}))
        self.assertFalse(checks.aggregate({'validation': {'result': 'success'}}))
        for job in passed:
            for status in ['failure', 'cancelled', 'skipped', '', None]:
                results = copy.deepcopy(passed)
                results[job]['result'] = status
                self.assertFalse(checks.aggregate(results), (job, status))

    def test_package_policy_and_conditional_aggregate(self):
        self.assertFalse(checks.package_required(['docs/user-guide.md', 'src/ui/image_view_widget.cpp']))
        self.assertFalse(checks.package_required(['version.txt', '.release-please-manifest.json', 'CHANGELOG.md']))
        self.assertTrue(checks.docs_only(['docs/user-guide.md', 'README.md']))
        self.assertFalse(checks.docs_only(['docs/user-guide.md', 'src/app/main.cpp']))
        documentation = {name: {'result': status} for name, status in {
            'validation': 'success', 'builds': 'skipped',
            'package-source': 'skipped', 'packages': 'skipped'}.items()}
        self.assertTrue(checks.aggregate(documentation, False, True))
        self.assertFalse(checks.aggregate(documentation, False, False))
        for path in ['CMakeLists.txt',
                     'resources/icon.svg', 'tools/release/github.py',
                     'packaging/platforms.json', '.github/workflows/release.yml']:
            self.assertTrue(checks.package_required([path]), path)
        for required in (False, True):
            expected = {'validation': {'result': 'success'},
                        'builds': {'result': 'skipped' if required else 'success'},
                        'package-source': {'result': 'success' if required else 'skipped'},
                        'packages': {'result': 'success' if required else 'skipped'}}
            self.assertTrue(checks.aggregate(expected, required))
            for name in expected:
                for status in ('failure', 'cancelled', 'skipped', 'success'):
                    changed = copy.deepcopy(expected)
                    changed[name]['result'] = status
                    self.assertEqual(checks.aggregate(changed, required),
                                     status == expected[name]['result'])
            expected.pop('packages')
            self.assertFalse(checks.aggregate(expected, required))

    def test_version(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                'GITHUB_REF': 'refs/tags/v0.1.0', 'GITHUB_EVENT_NAME': '', 'GITHUB_EVENT_PATH': ''}):
            root = Path(directory)
            (root / 'version.txt').write_text('0.1.0\n')
            checks.check_version(root)
            (root / '.release-please-manifest.json').write_text('{".": "0.2.0"}')
            with self.assertRaises(ValueError):
                checks.check_version(root)
            (root / '.release-please-manifest.json').write_text('{".": "0.1.0"}')
            with patch.dict(os.environ, {'GITHUB_REF': 'refs/tags/v0.2.0'}), self.assertRaises(ValueError):
                checks.check_version(root)
            for invalid in ['0.1.0', '01.1.0\n', '0.1.0\n\n', '0.1.0\r\n']:
                (root / 'version.txt').write_text(invalid)
                with self.assertRaises(ValueError):
                    checks.check_version(root)

    def test_release_pr_requires_removing_bootstrap_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'version.txt').write_text('0.1.0\n')
            (root / '.release-please-manifest.json').write_text('{".": "0.1.0"}')
            event = root / 'event.json'
            event.write_text(json.dumps({'pull_request': {'head': {'ref': 'release-please--branches--master'}}}))
            config = root / 'release-please-config.json'
            config.write_text('{"packages": {".": {"release-as": "0.1.0"}}}')
            with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'pull_request',
                                         'GITHUB_EVENT_PATH': str(event), 'GITHUB_REF': 'refs/pull/1/merge'}):
                with self.assertRaises(ValueError):
                    checks.check_version(root)
                config.write_text('{"packages": {".": {"release-type": "simple"}}}')
                checks.check_version(root)


if __name__ == '__main__':
    unittest.main()
