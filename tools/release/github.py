#!/usr/bin/env python3
"""Trusted GitHub release orchestration; build jobs never receive write tokens."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from artifacts import VERSION, digest, git, release_targets, verify, write_json

MARKER = re.compile(r'<!-- insidious-release-inventory:([1-9][0-9]*):([1-9][0-9]*):([0-9a-f]{64}) -->')


class GitHub:
    def __init__(self, repository):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('Invalid repository')
        self.repository = repository
        self.prefix = f'repos/{repository}/'

    def api(self, path, data=None):
        command = ['gh', 'api', self.prefix + path, '--method', 'GET' if data is None else 'PATCH']
        if data is not None:
            command.extend(['--input', '-'])
        result = subprocess.check_output(command, input=None if data is None else json.dumps(data).encode())
        return json.loads(result)

    def pages(self, path):
        result = json.loads(subprocess.check_output(
            ['gh', 'api', self.prefix + path, '--paginate', '--slurp']))
        return [item for page in result for item in page]

    def release(self, tag):
        # The by-tag endpoint documents published releases. Enumerate drafts too.
        releases = [r for r in self.pages('releases?per_page=100') if r['tag_name'] == tag]
        if len(releases) != 1:
            raise ValueError('Expected one existing release for this tag')
        return self.api(f'releases/{releases[0]["id"]}')

    def assets(self, release):
        return self.pages(f'releases/{release["id"]}/assets?per_page=100')

    def download(self, asset, output):
        with output.open('xb') as stream:
            subprocess.run(['gh', 'api', self.prefix + f'releases/assets/{int(asset["id"])}',
                            '-H', 'Accept: application/octet-stream'], stdout=stream, check=True)

    def upload(self, tag, path):
        # Never pass --clobber: even a same-name race must fail without replacing bytes.
        subprocess.run(['gh', 'release', 'upload', tag, str(path),
                        '--repo', self.repository], check=True)


def read_at(checkout, commit, path):
    return git(checkout, 'show', f'{commit}:{path}').decode()


def ancestry(checkout, ancestor, descendant):
    subprocess.run(['git', '-C', str(checkout), 'merge-base', '--is-ancestor',
                    ancestor, descendant], check=True)


def live_commit(api, tag):
    obj = api.api('git/ref/tags/' + tag)['object']
    for _ in range(8):
        if obj['type'] == 'commit':
            return obj['sha']
        if obj['type'] != 'tag':
            break
        obj = api.api('git/tags/' + obj['sha'])['object']
    raise ValueError('Invalid or excessively nested release tag')


def inventory_marker(release):
    body = release.get('body') or ''
    matches = list(MARKER.finditer(body))
    if len(matches) > 1 or ('insidious-release-inventory:' in body and not matches):
        raise ValueError('Malformed or duplicate release inventory marker')
    return matches[0].groups() if matches else None


def validate_run(api, checkout, run_id, attempt):
    run = api.api(f'actions/runs/{int(run_id)}/attempts/{int(attempt)}')
    if (run['id'] != int(run_id) or run['run_attempt'] != int(attempt)
            or run['path'] not in ('.github/workflows/release.yml', '.github/workflows/release-please.yml')
            or run['event'] not in ('push', 'workflow_dispatch')
            or run['head_branch'] != 'master'
            or run['head_repository']['full_name'] != api.repository):
        raise ValueError('Recovery artifacts must originate from a trusted release workflow')
    ancestry(checkout, run['head_sha'], 'refs/remotes/origin/master')
    return run


def require_no_other_draft(api, tag):
    for release in api.pages('releases?per_page=100'):
        if (release['tag_name'] != tag and release['draft']
                and '<!-- insidious-release-abandoned -->' not in (release.get('body') or '')):
            raise ValueError('Recover or explicitly abandon the preceding draft first')


def guard(api, checkout, tag, recovery_run=''):
    if not re.fullmatch('v' + VERSION, tag):
        raise ValueError('Expected an existing numeric release tag')
    version = tag[1:]
    commit = git(checkout, 'rev-parse', '--verify', f'refs/tags/{tag}^{{commit}}').decode().strip()
    if live_commit(api, tag) != commit:
        raise ValueError('Remote release tag changed')
    ancestry(checkout, commit, 'refs/remotes/origin/master')
    if (read_at(checkout, commit, 'version.txt') != version + '\n'
            or json.loads(read_at(checkout, commit, '.release-please-manifest.json')) != {'.': version}):
        raise ValueError('Tag/version/release-please manifest mismatch')
    if not re.search(r'^## (?:\[' + re.escape(version) + r'\]|' + re.escape(version)
                     + r')(?=[ (\n]|$)', read_at(checkout, commit, 'CHANGELOG.md'), re.MULTILINE):
        raise ValueError('Release version is missing from the changelog')
    config = json.loads(read_at(checkout, commit, 'release-please-config.json'))
    if 'release-as' in config or any('release-as' in p for p in config['packages'].values()):
        raise ValueError('Remove the one-time release-as override in the first release PR')
    matrix = json.loads(read_at(checkout, commit, 'packaging/platforms.json'))
    rows = release_targets(matrix)
    associated = api.pages(f'commits/{commit}/pulls?per_page=100')
    prs = [pr for pr in associated if pr.get('merged_at')
           and pr['merge_commit_sha'] == commit and pr['base']['ref'] == 'master'
           and pr['base']['repo']['full_name'] == api.repository
           and pr['head']['repo'] and pr['head']['repo']['full_name'] == api.repository
           and pr['head']['ref'] == 'release-please--branches--master'
           and any(label['name'] in ('autorelease: pending', 'autorelease: tagged') for label in pr['labels'])]
    if len(prs) != 1:
        raise ValueError('Tag must identify the merge of one labelled release-please PR')
    release = api.release(tag)
    if release['tag_name'] != tag or release['prerelease']:
        raise ValueError('Unexpected release tag/channel')
    if release['draft']:
        if '<!-- insidious-release-abandoned -->' in (release.get('body') or ''):
            raise ValueError('This draft was explicitly abandoned; use a new version')
        require_no_other_draft(api, tag)
    versions = []
    for previous in api.pages('releases?per_page=100'):
        previous_tag = previous['tag_name']
        if (not previous['draft'] and not previous['prerelease']
                and re.fullmatch('v' + VERSION, previous_tag)
                and tuple(map(int, previous_tag[1:].split('.'))) < tuple(map(int, version.split('.')))):
            versions.append(previous_tag)
    previous_tag = max(versions, key=lambda v: tuple(map(int, v[1:].split('.')))) if versions else None
    identity = {'repository': api.repository, 'version': version, 'tag': tag, 'commit': commit,
                'source_date_epoch': int(git(checkout, 'show', '-s', '--format=%ct', commit)),
                'release_pr': prs[0]['number'], 'previous_tag': previous_tag}
    marker = inventory_marker(release)
    if recovery_run:
        if not re.fullmatch(r'[1-9][0-9]*:[1-9][0-9]*', recovery_run):
            raise ValueError('Recovery run must be RUN_ID:ATTEMPT')
        run_id, attempt = recovery_run.split(':')
        if marker and (run_id, attempt) != marker[:2]:
            raise ValueError('Recovery run disagrees with the draft inventory')
    elif marker:
        run_id, attempt = marker[:2]
    else:
        run_id = attempt = ''
    if not release['draft']:
        if not marker:
            raise ValueError('Published release has no trusted inventory marker')
        mode = 'published'
    elif run_id:
        validate_run(api, checkout, run_id, attempt)
        mode = 'resume'
    else:
        if api.assets(release):
            raise ValueError('Draft has assets but no trusted inventory; supply the original recovery run')
        mode = 'build'
    return {'identity': identity, 'matrix': matrix, 'rows': rows, 'mode': mode,
            'run_id': run_id, 'attempt': attempt,
            'manifest_sha256': marker[2] if marker else None}


def verify_provenance(api, directory, manifest):
    run = manifest['build_run']
    if not re.fullmatch('[0-9a-f]{40}', run['workflow_sha']):
        raise ValueError('Invalid provenance source identity')
    names = [p['filename'] for p in manifest['payloads']] + ['release-manifest.json']
    for name in names:
        subprocess.run(['gh', 'attestation', 'verify', str(directory / name),
                        '--repo', api.repository, '--bundle', str(directory / 'provenance.jsonl'),
                        '--signer-workflow', api.repository + '/.github/workflows/release.yml',
                        '--signer-digest', run['workflow_sha'], '--source-digest', run['workflow_sha'],
                        '--deny-self-hosted-runners'], check=True)


def check_bundle(api, checkout, state, directory):
    manifest = verify(directory, state['matrix'], state['identity'])
    if state['manifest_sha256'] and digest(directory / 'release-manifest.json') != state['manifest_sha256']:
        raise ValueError('Retained inventory disagrees with the release marker')
    build_run = manifest['build_run']
    run_id, attempt = str(build_run['id']), str(build_run['attempt'])
    if state['run_id'] and (run_id, attempt) != (state['run_id'], state['attempt']):
        raise ValueError('Inventory originated from a different workflow run')
    run = validate_run(api, checkout, run_id, attempt)
    if run['head_sha'] != build_run['workflow_sha']:
        raise ValueError('Inventory workflow SHA mismatch')
    ancestry(checkout, manifest['commit'], run['head_sha'])
    verify_provenance(api, directory, manifest)
    return manifest


def restore(api, checkout, state, directory):
    if directory.exists():
        raise ValueError('Recovery output must not exist')
    if state['mode'] == 'published':
        directory.mkdir(parents=True)
        release = api.release(state['identity']['tag'])
        for asset in api.assets(release):
            name = asset['name']
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
                raise ValueError('Unsafe remote asset name')
            api.download(asset, directory / name)
    elif state['mode'] == 'resume':
        subprocess.run(['gh', 'run', 'download', state['run_id'], '--repo', api.repository,
                        '--name', f'release-bundle-{state["identity"]["tag"]}-{state["attempt"]}',
                        '--dir', str(directory)], check=True)
    else:
        raise ValueError('No retained inventory is expected before a build')
    check_bundle(api, checkout, state, directory)


def remote_inventory(api, release, directory, complete):
    expected = {p.name: descriptor_for_remote(p) for p in directory.iterdir()}
    seen = set()
    with tempfile.TemporaryDirectory() as temporary:
        for asset in api.assets(release):
            name = asset['name']
            if name in seen or name not in expected:
                raise ValueError('Duplicate or unexpected remote release asset')
            seen.add(name)
            if asset['size'] != expected[name]['size']:
                raise ValueError('Remote asset size mismatch')
            path = Path(temporary) / name
            api.download(asset, path)
            if digest(path) != expected[name]['sha256']:
                raise ValueError('Remote asset digest mismatch; never overwrite')
    if complete and seen != set(expected):
        raise ValueError('Published/uploaded release is missing required assets')
    return set(expected) - seen


def descriptor_for_remote(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError('Release files must be regular files')
    return {'size': path.stat().st_size, 'sha256': digest(path)}


def release_notes(body, manifest):
    version, repository, tag = manifest['version'], manifest['repository'], manifest['tag']
    rows = '\n'.join(f'| {row["target"]} | [{row["package"]["filename"]}]'
                     f'(https://github.com/{repository}/releases/download/{tag}/{row["package"]["filename"]}) |'
                     for row in manifest['targets'])
    return (body.rstrip() + '\n\n### Downloads\n\n| Platform | Package |\n| --- | --- |\n' + rows
            + f'\n\nNative packages use system libraries; excluded platforms are listed in '
              f'[the platform matrix](https://github.com/{repository}/blob/{tag}/packaging/README.md).\n\n'
              'Install the Arch package with `sudo pacman -U PACKAGE.pkg.tar.zst` or the Fedora package '
              'with `sudo dnf install ./PACKAGE.rpm`. Verify downloaded payloads using '
              '`sha256sum -c SHA256SUMS` (download all listed files), and '
              f'`gh attestation verify FILE --repo {repository} --bundle provenance.jsonl '
              f'--signer-workflow {repository}/.github/workflows/release.yml`.\n\n'
              f'[Usage and limitations](https://github.com/{repository}/blob/{tag}/docs/user-guide.md) · '
              f'[Changelog](https://github.com/{repository}/blob/{tag}/CHANGELOG.md)\n')


def publish(api, checkout, state, directory):
    manifest = check_bundle(api, checkout, state, directory)
    tag = manifest['tag']
    if live_commit(api, tag) != manifest['commit']:
        raise ValueError('Remote release tag changed before publication')
    release = api.release(tag)
    marker = inventory_marker(release)
    build_run = manifest['build_run']
    expected_marker = (str(build_run['id']), str(build_run['attempt']),
                       digest(directory / 'release-manifest.json'))
    if marker and marker != expected_marker:
        raise ValueError('Release inventory was already bound to different bytes')
    if not release['draft']:
        if release.get('immutable') is not True:
            raise ValueError('Published release is not immutable')
        remote_inventory(api, release, directory, complete=True)
        verify_public_source(api, directory, manifest)
        return  # Published reruns are strictly read-only.
    if '<!-- insidious-release-abandoned -->' in (release.get('body') or ''):
        raise ValueError('Cannot publish an abandoned draft')
    require_no_other_draft(api, tag)
    for other in api.pages('releases?per_page=100'):
        if (not other['draft'] and not other['prerelease'] and re.fullmatch('v' + VERSION, other['tag_name'])
                and tuple(map(int, other['tag_name'][1:].split('.')))
                > tuple(map(int, manifest['version'].split('.')))):
            raise ValueError('Cannot publish an older draft after a newer release')
    missing = remote_inventory(api, release, directory, complete=False)
    if not marker:
        body = release_notes(release.get('body') or '', manifest)
        body += '\n<!-- insidious-release-inventory:' + ':'.join(expected_marker) + ' -->\n'
        api.api(f'releases/{release["id"]}', {'body': body, 'name': 'Insidious ' + manifest['version']})
    for name in sorted(missing):
        api.upload(tag, directory / name)
    release = api.release(tag)
    remote_inventory(api, release, directory, complete=True)
    api.api(f'releases/{release["id"]}', {'draft': False, 'make_latest': 'true'})
    published = api.release(tag)
    if published['draft'] or published.get('immutable') is not True:
        raise ValueError('Release was not published with immutability enabled')
    remote_inventory(api, published, directory, complete=True)
    if api.api('releases/latest')['tag_name'] != tag:
        raise ValueError('Latest does not identify the completed release')
    verify_public_source(api, directory, manifest)


def verify_public_source(api, directory, manifest):
    # Check the actual public source URL used by the stable Arch recipe.
    with tempfile.TemporaryDirectory() as temporary:
        source = f'insidious-{manifest["version"]}.tar.xz'
        downloaded = Path(temporary) / source
        subprocess.run(['curl', '--fail', '--location', '--proto', '=https', '--output', str(downloaded),
                        f'https://github.com/{api.repository}/releases/download/{manifest["tag"]}/{source}'], check=True)
        if digest(downloaded) != digest(directory / source):
            raise ValueError('Public source URL returned different bytes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('guard', 'restore', 'publish', 'previous'))
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY'), required=False)
    parser.add_argument('--checkout', type=Path, default=Path('.'))
    parser.add_argument('--tag', default=os.environ.get('RELEASE_TAG', ''))
    parser.add_argument('--recovery-run', default=os.environ.get('RECOVERY_RUN', ''))
    parser.add_argument('--state', type=Path, default=Path('release-state.json'))
    parser.add_argument('--directory', type=Path, default=Path('release-bundle'))
    args = parser.parse_args()
    try:
        api = GitHub(args.repository)
        if args.command == 'guard':
            state = guard(api, args.checkout, args.tag, args.recovery_run)
            write_json(args.state, state)
            write_json(Path('release-identity.json'), state['identity'])
            write_json(Path('release-platforms.json'), state['matrix'])
            if os.environ.get('GITHUB_OUTPUT'):
                with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
                    outputs = {'mode': state['mode'], 'sha': state['identity']['commit'],
                               'matrix': json.dumps({'include': state['rows']}),
                               'previous_tag': state['identity']['previous_tag'] or ''}
                    for key, value in outputs.items():
                        stream.write(f'{key}={value}\n')
        elif args.command == 'previous':
            state = guard(api, args.checkout, args.tag)
            if state['mode'] != 'published':
                raise ValueError('Upgrade requires a published previous release')
            restore(api, args.checkout, state, args.directory)
        else:
            state = json.loads(args.state.read_text())
            if args.command == 'restore':
                restore(api, args.checkout, state, args.directory)
            else:
                publish(api, args.checkout, state, args.directory)
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
