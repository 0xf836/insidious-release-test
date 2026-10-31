#!/usr/bin/env python3
"""Render native recipes for an already verified canonical source archive."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile

VERSION = r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)'


def inspect_source(source):
    match = re.fullmatch(rf'insidious-({VERSION})\.tar\.xz', source.name)
    if not match:
        raise ValueError('Expected insidious-MAJOR.MINOR.PATCH.tar.xz')
    version = match[1]
    root = f'insidious-{version}'
    with tarfile.open(source, 'r:xz') as archive:
        members = {}
        for member in archive:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or '..' in path.parts or not path.parts
                    or path.parts[0] != root or '.git' in path.parts
                    or not (member.isfile() or member.isdir())
                    or str(path) in members):
                raise ValueError('Unsafe or duplicate source archive member')
            members[str(path)] = member
        def read(name):
            member = members.get(f'{root}/{name}')
            if member is None or not member.isfile() or member.size > 4096:
                raise ValueError(f'Missing or oversized {name}')
            return archive.extractfile(member).read().decode('utf-8')
        if read('version.txt') != version + '\n':
            raise ValueError('Archive filename/version.txt mismatch')
        metadata = json.loads(read('source-metadata.json'))
        if (not isinstance(metadata, dict) or metadata.get('version') != version
                or not isinstance(metadata.get('commit'), str)
                or not re.fullmatch('[0-9a-f]{40}', metadata['commit'])):
            raise ValueError('Invalid source identity metadata')
    with source.open('rb') as stream:
        checksum = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            checksum.update(chunk)
        digest = checksum.hexdigest()
    return version, digest


def render_recipes(source, repository='0xf836/insidious'):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Invalid source repository')
    version, digest = inspect_source(source)
    recipes = {}
    # Recovery may use newer workflow code. Recipe data must still come from
    # the exact canonical release source, never the current control checkout.
    with tarfile.open(source, 'r:xz') as archive:
        for template, name in [('arch/PKGBUILD.in', 'PKGBUILD'),
                               ('rpm/insidious.spec.in', 'insidious.spec')]:
            try:
                member = archive.getmember(f'insidious-{version}/packaging/{template}')
            except KeyError as error:
                raise ValueError('Source archive is missing a native recipe template') from error
            if not member.isfile() or not 0 < member.size <= 65536:
                raise ValueError('Invalid or oversized native recipe template')
            content = archive.extractfile(member).read().decode('utf-8')
            recipes[name] = (content.replace('@VERSION@', version).replace('@SHA256@', digest)
                            .replace('@REPOSITORY@', repository))
    return version, digest, recipes


def prepare(source, output, repository='0xf836/insidious'):
    version, digest, recipes = render_recipes(source, repository)
    # Refuse to mix recipes with stale output or overwrite an existing archive.
    output.mkdir(parents=True, exist_ok=False)
    for name, content in recipes.items():
        (output / name).write_text(content)
    shutil.copyfile(source, output / source.name)
    (output / 'SHA256SUMS').write_text(f'{digest}  {source.name}\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repository', default='0xf836/insidious',
                        help='Source release repository; override only for isolated release trials')
    args = parser.parse_args()
    try:
        prepare(args.source, args.output, args.repository)
    except (ValueError, OSError, tarfile.TarError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
