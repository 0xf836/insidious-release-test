"""Source identity, integrity and path safety at the packaging boundary."""
import hashlib
import configparser
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('prepare', ROOT / 'tools/packaging/prepare.py')
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


class PackagingTests(unittest.TestCase):
    def evidence(self, *arguments):
        return subprocess.run(
            [sys.executable, str(ROOT / 'tools/packaging/evidence.py'), *map(str, arguments)],
            capture_output=True, text=True)

    def build_evidence(self, directory, distribution='arch'):
        source = self.archive(directory)
        suffix = '-1-x86_64.pkg.tar.zst' if distribution == 'arch' else '-1.fc44.x86_64.rpm'
        package = directory / f'insidious-0.1.0{suffix}'
        package.write_bytes(b'package fixture')
        result = self.evidence('build', distribution, source, package, directory / 'build.json')
        self.assertEqual(result.returncode, 0, result.stderr)
        return package

    def test_runtime_evidence_binds_package_source_and_installed_version(self):
        for distribution in ('arch', 'fedora'):
            with self.subTest(distribution=distribution), tempfile.TemporaryDirectory() as directory:
                directory = Path(directory)
                package = self.build_evidence(directory, distribution)
                result = self.evidence('verify', distribution, directory)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), package.name)
                version = directory / 'version.txt'
                version.write_text('Insidious 0.2.0\n')
                output = directory / 'runtime.json'
                args = ('runtime', distribution, directory, version, output,
                        'not-applicable-first-package')
                self.assertNotEqual(self.evidence(*args).returncode, 0)
                self.assertFalse(output.exists())
                version.write_text('Insidious 0.1.0\n')
                self.assertEqual(self.evidence(*args).returncode, 0)
                data = json.loads(output.read_text())
                self.assertEqual(data['source']['commit'], 'a' * 40)
                self.assertEqual(data['package']['sha256'], hashlib.sha256(package.read_bytes()).hexdigest())
                self.assertTrue(all(value == 'passed' for value in data['runtime_checks'].values()))
                self.assertEqual(data['installation_mode'], 'clean-install')
                # A retry cannot overwrite a successful result with new evidence.
                self.assertNotEqual(self.evidence(*args).returncode, 0)

    def test_clean_and_upgrade_reports_remain_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            self.build_evidence(directory)
            version = directory / 'version.txt'
            version.write_text('Insidious 0.1.0\n')
            for outcome, mode in [('not-run', 'clean-install'), ('passed', 'upgrade')]:
                output = directory / f'{mode}.json'
                result = self.evidence('runtime', 'arch', directory, version, output, outcome)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(output.read_text())['installation_mode'], mode)

    def test_rpm_copy_requires_source_and_propagates_copy_failure(self):
        helper = ROOT / 'tools/packaging/assertions.sh'
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for name in ('RPMS', 'SRPMS', 'output'):
                (directory / name).mkdir()
            (directory / 'RPMS/app.rpm').write_bytes(b'binary')
            command = ['bash', '-c', 'source "$1"; copy_rpms "$2" "$2/output"',
                       '_', str(helper), str(directory)]
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            (directory / 'SRPMS/app.src.rpm').write_bytes(b'source')
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            # A destination directory at a package filename makes cp fail even as root.
            (directory / 'output/app.rpm').unlink()
            (directory / 'output/app.rpm').mkdir()
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_reject_mismatched_or_missing_package_evidence(self):
        for mutation in ('bytes', 'missing-package', 'distribution', 'version', 'commit',
                         'path', 'failed-build', 'missing-evidence'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                directory = Path(directory)
                package = self.build_evidence(directory)
                evidence = directory / 'build.json'
                data = json.loads(evidence.read_text())
                if mutation == 'bytes':
                    package.write_bytes(b'changed package')
                elif mutation == 'missing-package':
                    package.unlink()
                elif mutation == 'distribution':
                    data['distribution'] = 'fedora'
                elif mutation == 'version':
                    data['source']['version'] = '0.2.0'
                elif mutation == 'commit':
                    data['source']['commit'] = 'invalid'
                elif mutation == 'path':
                    data['package']['filename'] = '../' + package.name
                elif mutation == 'failed-build':
                    data['build_and_tests'] = 'failed'
                evidence.write_text(json.dumps(data))
                if mutation == 'missing-evidence':
                    evidence.unlink()
                self.assertNotEqual(self.evidence('verify', 'arch', directory).returncode, 0)

    def test_upgrade_requires_strictly_older_version(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            self.build_evidence(directory)
            version = directory / 'previous-version.txt'
            for value, passed in [('0.0.9', True), ('0.1.0', False), ('0.2.0', False),
                                  ('0.1.0-dev+unknown', False)]:
                with self.subTest(value=value):
                    version.write_text(f'Insidious {value}\n')
                    result = self.evidence('previous', 'arch', directory, version)
                    self.assertEqual(result.returncode == 0, passed, result.stderr)

    def test_runtime_diagnostic_failures_stop_the_runner(self):
        helper = ROOT / 'tools/packaging/assertions.sh'
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'launch.log'
            for content, passed in [('startup complete', True),
                                    ('libQt6Gui.so => not found', False),
                                    ('Could not connect to display', False),
                                    (None, False)]:
                with self.subTest(content=content):
                    if content is not None:
                        log.write_text(content)
                    else:
                        log.unlink()
                    result = subprocess.run(
                        ['bash', '-c', 'set -euo pipefail; source "$1"; '
                         'reject_matches "not found|could not connect" "$2"; '
                         'printf reached-success', '_', str(helper), str(log)],
                        capture_output=True, text=True)
                    self.assertEqual(result.returncode == 0, passed)
                    self.assertEqual('reached-success' in result.stdout, passed)

    def test_desktop_resource_identity_agrees(self):
        metadata = ET.parse(ROOT / 'resources/io.github._0xf836.Insidious.metainfo.xml').getroot()
        identity = metadata.findtext('id')
        self.assertGreaterEqual(len(identity.split('.')), 3)
        for component in identity.split('.'):
            self.assertRegex(component, r'^[A-Za-z_][A-Za-z0-9_]*$')
        desktop = metadata.findtext("launchable[@type='desktop-id']")
        self.assertEqual(desktop, identity + '.desktop')
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(ROOT / 'resources' / desktop)
        entry = parser['Desktop Entry']
        self.assertEqual(entry['Icon'], identity)
        self.assertEqual(entry['Exec'], 'insidious %f')
        for directory in ['scalable', '48x48', '64x64', '128x128', '256x256']:
            suffix = 'svg' if directory == 'scalable' else 'png'
            self.assertTrue((ROOT / 'resources/icons' / directory / 'apps' / f'{identity}.{suffix}').is_file())

    def archive(self, directory, changes=None, extra=None):
        files = {'version.txt': '0.1.0\n',
                 'source-metadata.json': json.dumps({'version': '0.1.0', 'commit': 'a' * 40})}
        for template in ('arch/PKGBUILD.in', 'rpm/insidious.spec.in'):
            files['packaging/' + template] = (ROOT / 'packaging' / template).read_text()
        files.update(changes or {})
        source = directory / 'insidious-0.1.0.tar.xz'
        with tarfile.open(source, 'w:xz') as archive:
            for name, content in files.items():
                if content is None:
                    continue
                member = tarfile.TarInfo(f'insidious-0.1.0/{name}')
                data = content.encode()
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            if extra:
                archive.addfile(extra)
        return source

    def test_prepared_recipes_bind_version_and_source_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = self.archive(directory)
            output = directory / 'recipes'
            prepare.prepare(source, output)
            checksum = hashlib.sha256(source.read_bytes()).hexdigest()
            self.assertEqual((output / source.name).read_bytes(), source.read_bytes())
            self.assertEqual((output / 'SHA256SUMS').read_text(), f'{checksum}  {source.name}\n')
            arch = (output / 'PKGBUILD').read_text()
            rpm = (output / 'insidious.spec').read_text()
            self.assertIn(f"sha256sums=('{checksum}')", arch)
            self.assertIn('pkgver=0.1.0\n', arch)
            self.assertIn('Version:        0.1.0\n', rpm)
            self.assertNotIn('SKIP', arch)
            with self.assertRaises(FileExistsError):
                prepare.prepare(source, output)

    def test_reject_identity_mismatches_before_creating_output(self):
        for changes in [{'version.txt': '0.2.0\n'}, {'version.txt': '0.1.0'},
                        {'source-metadata.json': '{}'},
                        {'source-metadata.json': '[]'},
                        {'source-metadata.json': '{'},
                        {'source-metadata.json': json.dumps({'version': '0.2.0', 'commit': 'a' * 40})}]:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                directory = Path(directory)
                source = self.archive(directory, changes)
                output = directory / 'recipes'
                with self.assertRaises(ValueError):
                    prepare.prepare(source, output)
                self.assertFalse(output.exists())

    def test_recipes_come_from_the_archive_during_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            frozen = (ROOT / 'packaging/arch/PKGBUILD.in').read_text() + '\n# Frozen release template\n'
            source = self.archive(directory, {'packaging/arch/PKGBUILD.in': frozen})
            prepare.prepare(source, directory / 'recipes', 'example/viewer')
            rendered = (directory / 'recipes/PKGBUILD').read_text()
            self.assertIn('# Frozen release template', rendered)
            self.assertIn('https://github.com/example/viewer', rendered)
        for content in (None, '', 'x' * 65537):
            with self.subTest(content_size=len(content or '')), tempfile.TemporaryDirectory() as directory:
                directory = Path(directory)
                source = self.archive(directory, {'packaging/arch/PKGBUILD.in': content})
                with self.assertRaises(ValueError):
                    prepare.prepare(source, directory / 'recipes')
                self.assertFalse((directory / 'recipes').exists())

    def test_reject_unsafe_members(self):
        for name, kind in [('insidious-0.1.0/../escape', tarfile.REGTYPE),
                           ('/absolute', tarfile.REGTYPE),
                           ('wrong-root/file', tarfile.REGTYPE),
                           ('insidious-0.1.0/.git/config', tarfile.REGTYPE),
                           ('insidious-0.1.0/link', tarfile.SYMTYPE),
                           ('insidious-0.1.0/version.txt', tarfile.REGTYPE)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                member = tarfile.TarInfo(name)
                member.type = kind
                member.linkname = '/outside'
                source = self.archive(Path(directory), extra=member)
                with self.assertRaises(ValueError):
                    prepare.inspect_source(source)


if __name__ == '__main__':
    unittest.main()
