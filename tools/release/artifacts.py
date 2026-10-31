#!/usr/bin/env python3
"""Export source archives with application version metadata."""
import argparse
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/packaging'))
from prepare import VERSION, inspect_source


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), *args])


def version_at(source):
    value = (source / 'version.txt').read_bytes().decode('ascii')
    if not re.fullmatch(VERSION + '\n', value):
        raise ValueError('Invalid version.txt')
    manifest = json.loads((source / '.release-please-manifest.json').read_text())
    if manifest != {'.': value.strip()}:
        raise ValueError('Release-please manifest/version mismatch')
    return value.strip()


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['source'])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tag')
    parser.add_argument('--candidate', action='store_true')
    args = parser.parse_args()
    try:
        print(source_archive(args.source, args.output, args.tag, args.candidate).name)
    except (ValueError, OSError, KeyError, tarfile.TarError,
            subprocess.CalledProcessError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
