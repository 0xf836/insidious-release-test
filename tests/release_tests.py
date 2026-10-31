"""Release identity, inventory, recovery and immutable-upload regressions.

GitHub is simulated here; hosted App/OIDC/publication trials are separate checks.
"""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/release'))
import artifacts
SPEC = importlib.util.spec_from_file_location('release_github', ROOT / 'tools/release/github.py')
github = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(github)


class FakeGitHub:
    repository = 'example/viewer'

    def __init__(self, commit):
        self.commit = commit
        self.current = {'id': 1, 'tag_name': 'v0.1.0', 'draft': True, 'prerelease': False, 'immutable': True,
                        'body': 'Initial release'}
        self.pr = {'number': 5, 'merged_at': '2026-01-01T00:00:00Z', 'merge_commit_sha': commit,
                   'base': {'ref': 'master', 'repo': {'full_name': self.repository}},
                   'head': {'ref': 'release-please--branches--master',
                            'repo': {'full_name': self.repository}},
                   'labels': [{'name': 'autorelease: tagged'}]}
        self.run = {'id': 123, 'run_attempt': 1, 'path': '.github/workflows/release-please.yml', 'event': 'push',
                    'head_branch': 'master', 'head_sha': commit,
                    'head_repository': {'full_name': self.repository}}
        self.files = {}
        self.patches = []
        self.uploads = []
        self.fail_upload = None

    def release(self, tag):
        if tag != self.current['tag_name']:
            raise ValueError('Unknown tag')
        return copy.deepcopy(self.current)

    def pages(self, path):
        if path.startswith('commits/'):
            return [copy.deepcopy(self.pr)]
        if path.startswith('releases?'):
            return [copy.deepcopy(self.current)]
        raise AssertionError(path)

    def api(self, path, data=None):
        if path.startswith('git/ref/tags/'):
            return {'object': {'type': 'commit', 'sha': self.commit}}
        if path.startswith('actions/runs/'):
            return copy.deepcopy(self.run)
        if path == 'releases/latest':
            return copy.deepcopy(self.current)
        if data is not None:
            self.patches.append(copy.deepcopy(data))
            self.current.update(data)
            return copy.deepcopy(self.current)
        raise AssertionError(path)

    def assets(self, release):
        return [{'id': i, 'name': name, 'size': len(data)}
                for i, (name, data) in enumerate(self.files.items(), 1)]

    def download(self, asset, output):
        output.write_bytes(self.files[asset['name']])

    def upload(self, tag, path):
        if path.name == self.fail_upload:
            raise OSError('Interrupted upload')
        if path.name in self.files:
            raise ValueError('Duplicate upload')
        self.uploads.append(path.name)
        self.files[path.name] = path.read_bytes()


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.matrix = json.loads((ROOT / 'packaging/platforms.json').read_text())
        self.command('init', '-q', '--initial-branch=master')
        self.command('config', 'user.name', 'Test')
        self.command('config', 'user.email', 'test@example.invalid')
        (self.source / 'version.txt').write_text('0.1.0\n')
        (self.source / '.release-please-manifest.json').write_text('{".": "0.1.0"}\n')
        (self.source / 'release-please-config.json').write_text('{"packages": {".": {"release-type": "simple"}}}\n')
        (self.source / 'packaging').mkdir()
        (self.source / 'packaging/platforms.json').write_text(json.dumps(self.matrix))
        (self.source / 'image.txt').write_text('fixture\n')
        (self.source / 'CHANGELOG.md').write_text('# Changelog\n\n## 0.1.0\n\nInitial viewer.\n')
        self.command('add', '.')
        self.command('commit', '-qm', 'feat: initial viewer')
        self.commit = self.command('rev-parse', 'HEAD').strip()
        self.command('tag', 'v0.1.0')
        self.command('update-ref', 'refs/remotes/origin/master', self.commit)
        self.api = FakeGitHub(self.commit)
        self.state = github.guard(self.api, self.source, 'v0.1.0')

    def command(self, *args):
        return subprocess.check_output(['git', '-C', str(self.source), *args], stderr=subprocess.PIPE).decode()

    def fixture_bundle(self):
        source = artifacts.source_archive(self.source, self.root / 'archive', 'v0.1.0')
        prepared = self.root / 'prepared'
        artifacts_path = ROOT / 'tools/packaging'
        sys.path.insert(0, str(artifacts_path))
        import prepare
        import evidence
        prepare.prepare(source, prepared, self.api.repository)
        results = self.root / 'results'
        for target, distribution in artifacts.TARGETS.items():
            build = results / target / 'build'
            runtime = results / target / 'runtime'
            build.mkdir(parents=True)
            runtime.mkdir()
            package = build / evidence.package_pattern(distribution, '0.1.0')
            package.write_bytes(b'qualified package ' + distribution.encode())
            evidence.record_build(distribution, source, package, build / 'build.json')
            version_file = self.root / 'installed-version'
            version_file.write_text('Insidious 0.1.0\n')
            evidence.record_runtime(build, distribution, version_file, runtime / 'runtime.json',
                                    'not-applicable-first-package')
            (build / 'packages.txt').write_text('runtime-library 1.0\ncompiler 1.0\n')
            (runtime / 'packages.txt').write_text('runtime-library 1.0\n')
            (build / 'os-release').write_text(f'ID={distribution}\n')
            if distribution == 'fedora':
                (build / 'insidious-0.1.0-1.fc44.src.rpm').write_bytes(b'source package')
                (build / 'insidious-debuginfo-0.1.0-1.fc44.x86_64.rpm').write_bytes(b'debug package')
        identity = {**self.state['identity'], 'build_run':
                    {'id': 123, 'attempt': 1, 'workflow_sha': self.commit}}
        bundle = self.root / 'bundle'
        manifest = artifacts.assemble(prepared, results, self.matrix, identity, bundle)
        (bundle / 'provenance.jsonl').write_text('hosted signed bundle placeholder\n')
        return bundle, manifest, results

    def test_source_is_reproducible_and_has_normalized_identity(self):
        first = artifacts.source_archive(self.source, self.root / 'one', 'v0.1.0')
        second = artifacts.source_archive(self.source, self.root / 'two', 'v0.1.0')
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with tarfile.open(first) as archive:
            metadata = json.load(archive.extractfile('insidious-0.1.0/source-metadata.json'))
            self.assertEqual(metadata, {'version': '0.1.0', 'commit': self.commit})
            for item in archive:
                self.assertEqual((item.uid, item.gid, item.uname, item.gname), (0, 0, '', ''))
                self.assertEqual(item.mtime, self.state['identity']['source_date_epoch'])
                self.assertNotIn('.git', Path(item.name).parts)

    def test_source_rejects_wrong_tag_dirty_and_untracked_state(self):
        with self.assertRaises(ValueError):
            artifacts.source_archive(self.source, self.root / 'wrong', 'v0.2.0')
        (self.source / 'untracked').touch()
        with self.assertRaises(ValueError):
            artifacts.source_archive(self.source, self.root / 'untracked', 'v0.1.0')
        (self.source / 'untracked').unlink()
        (self.source / 'version.txt').write_text('0.2.0\n')
        with self.assertRaises(ValueError):
            artifacts.source_archive(self.source, self.root / 'dirty', 'v0.1.0')

    def test_candidate_has_no_tag_requirement_and_cannot_claim_a_release_tag(self):
        self.command('tag', '-d', 'v0.1.0')
        path = artifacts.source_archive(self.source, self.root / 'candidate', candidate=True)
        self.assertTrue(path.exists())
        with self.assertRaises(ValueError):
            artifacts.source_archive(self.source, self.root / 'bad-candidate', 'v0.1.0', True)

    def test_source_rejects_symlinks(self):
        (self.source / 'link').symlink_to('image.txt')
        self.command('add', '.')
        self.command('commit', '-qm', 'test: symlink')
        with self.assertRaises(ValueError):
            artifacts.source_archive(self.source, self.root / 'bad-source', candidate=True)

    def test_mandatory_matrix_cannot_be_empty_deleted_or_unqualified(self):
        for change in ('empty', 'deleted', 'optional', 'unqualified', 'duplicate', 'unpinned'):
            matrix = copy.deepcopy(self.matrix)
            if change == 'empty':
                matrix['platforms'] = []
            elif change == 'deleted':
                matrix['platforms'].pop(0)
            elif change == 'optional':
                matrix['platforms'][0]['release_required'] = False
            elif change == 'unqualified':
                matrix['platforms'][0]['native_qualified'] = False
            elif change == 'duplicate':
                matrix['platforms'].append(matrix['platforms'][0])
            else:
                matrix['platforms'][0]['ci_image'] = 'archlinux:latest'
            with self.subTest(change=change), self.assertRaises(ValueError):
                artifacts.release_targets(matrix)

    def test_bundle_binds_source_packages_runtime_and_inventory(self):
        bundle, manifest, _ = self.fixture_bundle()
        self.assertEqual(artifacts.verify(bundle, self.matrix, self.state['identity']), manifest)
        self.assertEqual(len(manifest['targets']), 2)
        self.assertTrue(artifacts.payload_names('0.1.0') <= {p.name for p in bundle.iterdir()})
        self.assertIn('https://github.com/example/viewer', (bundle / 'insidious-0.1.0-arch-PKGBUILD').read_text())

    def test_missing_or_mutated_payload_and_unexpected_file_fail(self):
        bundle, _, _ = self.fixture_bundle()
        name = artifacts.package_pattern('arch', '0.1.0')
        original = (bundle / name).read_bytes()
        for mutation in ('missing', 'digest', 'unexpected'):
            with self.subTest(mutation=mutation):
                if mutation == 'missing':
                    (bundle / name).unlink()
                elif mutation == 'digest':
                    (bundle / name).write_bytes(b'other bytes')
                else:
                    (bundle / 'unexpected').touch()
                with self.assertRaises((ValueError, FileNotFoundError)):
                    artifacts.verify(bundle, self.matrix, self.state['identity'])
                (bundle / name).write_bytes(original)
                (bundle / 'unexpected').unlink(missing_ok=True)

    def test_missing_runtime_or_source_rpm_prevents_assembly(self):
        bundle, manifest, results = self.fixture_bundle()
        prepared = self.root / 'prepared'
        for change in ('runtime', 'source-rpm', 'source-identity', 'upgrade'):
            with self.subTest(change=change):
                directory = self.root / ('results-' + change)
                shutil.copytree(results, directory)
                identity = {key: value for key, value in manifest.items()
                            if key not in ('schema_version', 'targets', 'payloads')}
                if change == 'runtime':
                    (directory / 'arch-x86_64/runtime/runtime.json').unlink()
                elif change == 'source-rpm':
                    (directory / 'fedora44-x86_64/build/insidious-0.1.0-1.fc44.src.rpm').unlink()
                elif change == 'source-identity':
                    identity['commit'] = 'a' * 40
                else:
                    identity['previous_tag'] = 'v0.0.1'
                with self.assertRaises((ValueError, FileNotFoundError)):
                    artifacts.assemble(prepared, directory, self.matrix, identity,
                                       self.root / ('bad-' + change))

    def test_guard_rejects_untrusted_pr_wrong_manifest_and_invalid_tags(self):
        for tag in ('master', 'v01.1.0', 'v0.1.0\n', 'v0.1.0;false'):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                github.guard(self.api, self.source, tag)
        for change in ('fork', 'branch', 'label', 'sha'):
            api = FakeGitHub(self.commit)
            if change == 'fork':
                api.pr['head']['repo']['full_name'] = 'fork/viewer'
            elif change == 'branch':
                api.pr['head']['ref'] = 'arbitrary-release'
            elif change == 'label':
                api.pr['labels'] = []
            else:
                api.commit = 'a' * 40
            with self.subTest(change=change), self.assertRaises(ValueError):
                github.guard(api, self.source, 'v0.1.0')

    def test_early_failure_can_rebuild_without_a_release_manifest(self):
        self.assertEqual(self.state['mode'], 'build')
        self.api.files['unexpected.rpm'] = b'bytes'
        with self.assertRaises(ValueError):
            github.guard(self.api, self.source, 'v0.1.0')

    def test_guard_checks_version_manifest_changelog_and_bootstrap_config(self):
        original = github.read_at
        invalid = {'version.txt': '0.2.0\n', '.release-please-manifest.json': '{".": "0.2.0"}',
                   'CHANGELOG.md': '# Changelog\n\n## 0.0.1\n',
                   'release-please-config.json': '{"packages": {".": {"release-as": "0.1.0"}}}'}
        for filename, content in invalid.items():
            def read(checkout, commit, path):
                return content if path == filename else original(checkout, commit, path)
            with self.subTest(filename=filename), patch.object(github, 'read_at', side_effect=read), self.assertRaises(ValueError):
                github.guard(self.api, self.source, 'v0.1.0')

    def test_another_draft_requires_explicit_abandonment(self):
        original = self.api.pages
        other = {'tag_name': 'v0.0.1', 'draft': True, 'prerelease': False, 'body': 'Unfinished'}
        def pages(path):
            return original(path) + [other] if path.startswith('releases?') else original(path)
        with patch.object(self.api, 'pages', side_effect=pages):
            with self.assertRaises(ValueError):
                github.guard(self.api, self.source, 'v0.1.0')
            other['body'] += '\n<!-- insidious-release-abandoned -->'
            self.assertEqual(github.guard(self.api, self.source, 'v0.1.0')['mode'], 'build')

    def test_malformed_and_duplicate_inventory_markers_fail(self):
        for body in ['<!-- insidious-release-inventory:bad -->',
                     ('<!-- insidious-release-inventory:123:1:' + 'a' * 64 + ' -->\n') * 2]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                github.inventory_marker({'body': body})

    def test_marker_selects_retained_inventory_and_validates_origin(self):
        self.api.current['body'] += '\n<!-- insidious-release-inventory:123:1:' + 'a' * 64 + ' -->'
        self.assertEqual(github.guard(self.api, self.source, 'v0.1.0')['mode'], 'resume')
        for change in ('event', 'branch', 'repository', 'workflow'):
            run = copy.deepcopy(self.api.run)
            if change == 'event':
                self.api.run['event'] = 'pull_request'
            elif change == 'branch':
                self.api.run['head_branch'] = 'feature'
            elif change == 'repository':
                self.api.run['head_repository']['full_name'] = 'fork/viewer'
            else:
                self.api.run['path'] = '.github/workflows/ci.yml'
            with self.subTest(change=change), self.assertRaises(ValueError):
                github.guard(self.api, self.source, 'v0.1.0')
            self.api.run = run

    def test_recovery_requires_matching_run_and_available_artifacts(self):
        bundle, _, _ = self.fixture_bundle()
        checksum = artifacts.digest(bundle / 'release-manifest.json')
        self.api.current['body'] += f'\n<!-- insidious-release-inventory:123:1:{checksum} -->'
        with self.assertRaises(ValueError):
            github.guard(self.api, self.source, 'v0.1.0', '456:1')
        state = github.guard(self.api, self.source, 'v0.1.0')
        with patch.object(github.subprocess, 'run', side_effect=OSError('Artifact expired')):
            with self.assertRaises(OSError):
                github.restore(self.api, self.source, state, self.root / 'recover')
        self.assertFalse(self.api.patches)
        self.assertFalse(self.api.uploads)

    def test_conflicting_remote_asset_never_overwrites(self):
        bundle, _, _ = self.fixture_bundle()
        name = artifacts.package_pattern('arch', '0.1.0')
        self.api.files[name] = b'x' * (bundle / name).stat().st_size
        with patch.object(github, 'verify_provenance'), self.assertRaises(ValueError):
            github.publish(self.api, self.source, self.state, bundle)
        self.assertFalse(self.api.patches)
        self.assertFalse(self.api.uploads)

    def test_interrupted_upload_resumes_only_missing_files_and_published_rerun_is_read_only(self):
        bundle, manifest, _ = self.fixture_bundle()
        failed_name = artifacts.package_pattern('arch', '0.1.0')
        self.api.fail_upload = failed_name
        with patch.object(github, 'verify_provenance'), patch.object(github, 'verify_public_source'):
            with self.assertRaises(OSError):
                github.publish(self.api, self.source, self.state, bundle)
            self.assertTrue(self.api.current['draft'])
            self.assertTrue(github.inventory_marker(self.api.current))
            already_uploaded = list(self.api.uploads)
            state = github.guard(self.api, self.source, 'v0.1.0')
            self.assertEqual(state['mode'], 'resume')
            self.api.fail_upload = None
            github.publish(self.api, self.source, state, bundle)
            self.assertFalse(self.api.current['draft'])
            self.assertEqual(len(self.api.uploads), len(set(self.api.uploads)))
            self.assertTrue(set(already_uploaded) <= set(self.api.uploads))
            patches, uploads = copy.deepcopy(self.api.patches), list(self.api.uploads)
            state = github.guard(self.api, self.source, 'v0.1.0')
            self.assertEqual(state['mode'], 'published')
            github.publish(self.api, self.source, state, bundle)
            self.assertEqual(self.api.patches, patches)
            self.assertEqual(self.api.uploads, uploads)
            self.api.files.pop(f'insidious-{manifest["version"]}.tar.xz')
            with self.assertRaises(ValueError):
                github.publish(self.api, self.source, state, bundle)

    def test_provenance_checks_exact_workflow_and_source_identity(self):
        bundle, manifest, _ = self.fixture_bundle()
        with patch.object(github.subprocess, 'run') as run:
            github.verify_provenance(self.api, bundle, manifest)
        self.assertEqual(run.call_count, len(manifest['payloads']) + 1)
        for call in run.call_args_list:
            args = call.args[0]
            self.assertIn('--deny-self-hosted-runners', args)
            self.assertEqual(args[args.index('--signer-digest') + 1], self.commit)
            self.assertEqual(args[args.index('--source-digest') + 1], self.commit)
            self.assertEqual(args[args.index('--signer-workflow') + 1],
                             self.api.repository + '/.github/workflows/release.yml')

    def test_published_restore_uses_remote_files_without_mutating_release(self):
        bundle, _, _ = self.fixture_bundle()
        checksum = artifacts.digest(bundle / 'release-manifest.json')
        self.api.current.update(draft=False, body=f'<!-- insidious-release-inventory:123:1:{checksum} -->')
        self.api.files = {p.name: p.read_bytes() for p in bundle.iterdir()}
        state = github.guard(self.api, self.source, 'v0.1.0')
        recovered = self.root / 'published'
        with patch.object(github, 'verify_provenance'):
            github.restore(self.api, self.source, state, recovered)
        self.assertEqual({p.name for p in recovered.iterdir()}, set(self.api.files))
        self.assertFalse(self.api.patches)
        self.assertFalse(self.api.uploads)


if __name__ == '__main__':
    unittest.main()
