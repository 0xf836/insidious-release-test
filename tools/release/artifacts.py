#!/usr/bin/env python3
"""Create canonical sources and validate the complete native release inventory."""
import argparse
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/packaging'))
from prepare import VERSION, inspect_source, render_recipes
from evidence import digest, package_pattern, verify_build

TARGETS = {'arch-x86_64': 'arch', 'fedora44-x86_64': 'fedora'}
RUNTIME_CHECKS = {'installation', 'libraries', 'desktop_metadata', 'x11_startup',
                  'wayland_startup', 'privacy', 'removal', 'settings_preservation'}


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), *args])


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def version_at(source):
    value = (source / 'version.txt').read_bytes().decode('ascii')
    if not re.fullmatch(VERSION + '\n', value):
        raise ValueError('Invalid version.txt')
    manifest = json.loads((source / '.release-please-manifest.json').read_text())
    if manifest != {'.': value.strip()}:
        raise ValueError('Release-please manifest/version mismatch')
    return value.strip()


def release_targets(data):
    # This is an explicit supported inventory. Removing a row cannot silently
    # make an incomplete release pass; adding a platform needs a code review.
    rows = {}
    seen = set()
    if data['schema_version'] != 1 or data['architecture'] != 'x86_64':
        raise ValueError('Unsupported platform matrix')
    for row in data['platforms']:
        target = row['id']
        if target in seen:
            raise ValueError('Duplicate platform')
        seen.add(target)
        if not row['release_required']:
            continue
        if (target not in TARGETS or not row['native_qualified']
                or not row['selected_for_future_qualification']):
            raise ValueError('Unknown or unqualified mandatory platform')
        image = row['ci_image']
        repository = 'archlinux' if TARGETS[target] == 'arch' else 'fedora'
        if (not re.fullmatch(rf'docker.io/library/{repository}@sha256:[0-9a-f]{{64}}', image)
                or row['image_digest'] != image.split('@')[1]):
            raise ValueError('Unpinned or inconsistent platform image')
        rows[target] = {'target': target, 'distribution': TARGETS[target], 'image': image}
    if set(rows) != set(TARGETS):
        raise ValueError('Missing mandatory release platform')
    return [rows[key] for key in sorted(rows)]


def source_archive(source, output, tag=None, candidate=False):
    source = source.resolve()
    if git(source, 'rev-parse', '--show-toplevel').decode().strip() != str(source):
        raise ValueError('Source must be the checkout root')
    if git(source, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('Source checkout must be clean')
    version = version_at(source)
    commit = git(source, 'rev-parse', 'HEAD').decode().strip()
    if not candidate:
        if tag != 'v' + version or git(source, 'rev-parse', '--verify',
                                      f'refs/tags/{tag}^{{commit}}').decode().strip() != commit:
            raise ValueError('Release tag/version/HEAD mismatch')
    elif tag is not None:
        raise ValueError('Candidate archives cannot be release-tagged')
    epoch = int(git(source, 'show', '-s', '--format=%ct', commit))
    output.mkdir(parents=True, exist_ok=False)
    path = output / f'insidious-{version}.tar.xz'
    exported = git(source, 'archive', '--format=tar', commit)
    with tarfile.open(fileobj=io.BytesIO(exported)) as archive, \
            tarfile.open(path, 'w:xz', format=tarfile.PAX_FORMAT) as result:
        members = list(archive)
        if any(m.name == 'source-metadata.json' for m in members):
            raise ValueError('Source metadata must be generated, not tracked')
        for member in sorted(members, key=lambda m: m.name):
            name = PurePosixPath(member.name)
            if (name.is_absolute() or '..' in name.parts or '.git' in name.parts
                    or not (member.isfile() or member.isdir())):
                raise ValueError('Unsupported source archive member')
            member.name = f'insidious-{version}/{name}'
            member.uid = member.gid = 0
            member.uname = member.gname = ''
            member.mtime = epoch
            member.pax_headers = {}
            result.addfile(member, archive.extractfile(member) if member.isfile() else None)
        metadata = (json.dumps({'version': version, 'commit': commit}, sort_keys=True) + '\n').encode()
        member = tarfile.TarInfo(f'insidious-{version}/source-metadata.json')
        member.size, member.mtime, member.mode = len(metadata), epoch, 0o644
        result.addfile(member, io.BytesIO(metadata))
    inspect_source(path)
    return path


def descriptor(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError('Payload must be a regular file')
    return {'filename': path.name, 'size': path.stat().st_size, 'sha256': digest(path)}


def payload_names(version):
    return {f'insidious-{version}.tar.xz', f'insidious-{version}-arch-PKGBUILD',
            f'insidious-{version}-fedora44.spec', package_pattern('arch', version),
            package_pattern('fedora', version), f'insidious-{version}-1.fc44.src.rpm'}


def allowed_payload(name, version):
    return name in payload_names(version) or bool(re.fullmatch(
        rf'insidious-(?:debuginfo|debugsource)-{re.escape(version)}-1.fc44.x86_64.rpm', name))


def checksums(directory, manifest):
    names = sorted([p['filename'] for p in manifest['payloads']] + ['release-manifest.json'])
    return ''.join(f'{digest(directory / name)}  {name}\n' for name in names)


def assemble(prepared, results, matrix, identity, output):
    version, commit, tag = identity['version'], identity['commit'], identity['tag']
    rows = release_targets(matrix)
    source = prepared / f'insidious-{version}.tar.xz'
    source_version, source_digest = inspect_source(source)
    with tarfile.open(source) as archive:
        metadata = json.load(archive.extractfile(f'insidious-{version}/source-metadata.json'))
    if source_version != version or metadata['commit'] != commit or tag != 'v' + version:
        raise ValueError('Source archive/release identity mismatch')
    for name, content in render_recipes(source, identity['repository'])[2].items():
        if (prepared / name).read_text() != content:
            raise ValueError('Prepared recipes do not match the canonical source archive')
    targets = []
    packages = []
    for row in rows:
        directory = results / row['target']
        build = verify_build(directory / 'build', row['distribution'])
        runtime = json.loads((directory / 'runtime/runtime.json').read_text())
        if (build['source'] != {'version': version, 'commit': commit,
                               'filename': source.name, 'sha256': source_digest}
                or any(runtime.get(key) != value for key, value in build.items())
                or runtime.get('runtime_checks') != {key: 'passed' for key in RUNTIME_CHECKS}
                or runtime.get('installation_mode') != 'clean-install'
                or runtime.get('upgrade') not in ('not-run', 'not-applicable-first-package')):
            raise ValueError('Missing or mismatched clean package qualification')
        if identity.get('previous_tag'):
            upgrade = json.loads((directory / 'upgrade/runtime.json').read_text())
            if (any(upgrade.get(key) != value for key, value in build.items())
                    or upgrade.get('runtime_checks') != runtime['runtime_checks']
                    or upgrade.get('installation_mode') != 'upgrade'
                    or upgrade.get('upgrade') != 'passed'):
                raise ValueError('Missing or mismatched upgrade qualification')
        files = [p for p in (directory / 'build').iterdir()
                 if p.name.endswith(('.rpm', '.pkg.tar.zst'))]
        if any(not allowed_payload(p.name, version) for p in files):
            raise ValueError('Unexpected package filename')
        packages.extend(files)
        targets.append({**row, 'package': build['package'],
                        'upgrade': 'passed' if identity.get('previous_tag') else 'not-applicable-first-package',
                        'build_packages': (directory / 'build/packages.txt').read_text().splitlines(),
                        'runtime_packages': (directory / 'runtime/packages.txt').read_text().splitlines(),
                        'os_release': (directory / 'build/os-release').read_text().splitlines()})
    output.mkdir(parents=True, exist_ok=False)
    for path in [source, *packages]:
        target = output / path.name
        if target.exists():
            raise ValueError('Duplicate payload filename')
        shutil.copyfile(path, target)
    shutil.copyfile(prepared / 'PKGBUILD', output / f'insidious-{version}-arch-PKGBUILD')
    shutil.copyfile(prepared / 'insidious.spec', output / f'insidious-{version}-fedora44.spec')
    manifest = {'schema_version': 1, **identity, 'targets': targets,
                'payloads': [descriptor(p) for p in sorted(output.iterdir())]}
    write_json(output / 'release-manifest.json', manifest)
    (output / 'SHA256SUMS').write_text(checksums(output, manifest))
    verify(output, matrix, identity)
    return manifest


def verify(directory, matrix, identity):
    manifest = json.loads((directory / 'release-manifest.json').read_text())
    if (manifest['schema_version'] != 1
            or any(manifest.get(key) != value for key, value in identity.items())
            or not re.fullmatch(VERSION, manifest['version'])
            or not re.fullmatch('[0-9a-f]{40}', manifest['commit'])
            or manifest['tag'] != 'v' + manifest['version']):
        raise ValueError('Release manifest identity mismatch')
    expected = release_targets(matrix)
    actual = manifest['targets']
    if ([{key: row[key] for key in ('target', 'distribution', 'image')} for row in actual]
            != expected):
        raise ValueError('Release manifest platform mismatch')
    names = [item['filename'] for item in manifest['payloads']]
    if (len(names) != len(set(names)) or not payload_names(manifest['version']) <= set(names)
            or any(not allowed_payload(name, manifest['version']) for name in names)):
        raise ValueError('Missing, duplicate or unexpected release payload')
    for item in manifest['payloads']:
        if descriptor(directory / item['filename']) != item:
            raise ValueError('Release payload digest/size mismatch')
    source = directory / f'insidious-{manifest["version"]}.tar.xz'
    version, _, recipes = render_recipes(source, identity['repository'])
    with tarfile.open(source) as archive:
        metadata = json.load(archive.extractfile(f'insidious-{version}/source-metadata.json'))
    if version != manifest['version'] or metadata['commit'] != manifest['commit']:
        raise ValueError('Canonical source metadata/release manifest mismatch')
    for name, filename in [('PKGBUILD', f'insidious-{version}-arch-PKGBUILD'),
                           ('insidious.spec', f'insidious-{version}-fedora44.spec')]:
        if (directory / filename).read_text() != recipes[name]:
            raise ValueError('Published recipes do not match the canonical source archive')
    for row in actual:
        if row['package'] != {key: value for key, value in descriptor(
                directory / package_pattern(row['distribution'], manifest['version'])).items()
                if key != 'size'}:
            raise ValueError('Target/package digest disagreement')
    if (directory / 'SHA256SUMS').read_text() != checksums(directory, manifest):
        raise ValueError('Checksum inventory mismatch')
    permitted = set(names) | {'release-manifest.json', 'SHA256SUMS', 'provenance.jsonl'}
    if {p.name for p in directory.iterdir()} - permitted:
        raise ValueError('Unexpected release file')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    source = sub.add_parser('source')
    source.add_argument('--source', type=Path, required=True)
    source.add_argument('--output', type=Path, required=True)
    source.add_argument('--tag')
    source.add_argument('--candidate', action='store_true')
    for name in ('assemble', 'verify'):
        command = sub.add_parser(name)
        command.add_argument('--matrix', type=Path, required=True)
        command.add_argument('--identity', type=Path, required=True)
        command.add_argument('--directory', type=Path, required=True)
        if name == 'assemble':
            command.add_argument('--prepared', type=Path, required=True)
            command.add_argument('--results', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'source':
            print(source_archive(args.source, args.output, args.tag, args.candidate).name)
        else:
            options = (json.loads(args.matrix.read_text()), json.loads(args.identity.read_text()))
            if args.command == 'assemble':
                options[1]['build_run'] = {'id': int(os.environ['GITHUB_RUN_ID']),
                                           'attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
                                           'workflow_sha': os.environ['GITHUB_SHA']}
                assemble(args.prepared, args.results, *options, args.directory)
            else:
                verify(args.directory, *options)
    except (ValueError, OSError, KeyError, TypeError, tarfile.TarError,
            subprocess.CalledProcessError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
