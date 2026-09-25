#!/usr/bin/env python3
"""Cut a release: verify the version is agreed across files, tag it, publish the GitHub
Release from the CHANGELOG section that already exists.

Not run in CI on purpose. `tools/test_build.py::t_release` checks the file agreement (cheap,
portable); this script is the one place that touches the shared remote, and it refuses to move
when the sources disagree rather than tagging whatever it finds.

Usage:
  python tools/release.py            # dry run: what would be tagged and shipped
  python tools/release.py --apply    # tag, push tag, create the release
"""
import io
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPLY = '--apply' in sys.argv


def read(fp):
    return io.open(os.path.join(ROOT, fp), encoding='utf-8').read()


def sh(args, check=True):
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    if check and r.returncode != 0:
        raise SystemExit('command failed: %s\n%s' % (' '.join(args), (r.stderr or r.stdout)[:400]))
    return (r.stdout or '').strip()


def section(log, version):
    m = re.search(r'^## \[%s\][^\n]*\n(.*?)(?=^## \[|\Z)' % re.escape(version), log, re.S | re.M)
    return m.group(1).strip() if m else ''


def main():
    version = json.loads(read('package.json')).get('version', '')
    log = read('CHANGELOG.md')
    released = re.findall(r'^## \[(\d+\.\d+\.\d+)\]', log, re.M)
    problems = []
    if not released:
        problems.append('CHANGELOG has no released-version heading')
    elif released[0] != version:
        problems.append('CHANGELOG top released version %s != package.json %s' % (released[0], version))
    body = section(log, version)
    if not body:
        problems.append('CHANGELOG has no body under [%s] - nothing to publish' % version)
    head = sh(['git', 'rev-parse', 'HEAD'])
    dirty = sh(['git', 'status', '--porcelain'])
    if dirty:
        problems.append('working tree is dirty (%d paths) - commit first' % len(dirty.splitlines()))
    if problems:
        print('REFUSING to release:')
        for p in problems:
            print('  - ' + p)
        return 1

    tag = 'v' + version
    exists = sh(['git', 'tag', '-l', tag])
    print('version      : %s' % version)
    print('commit       : %s' % head[:9])
    print('tag          : %s%s' % (tag, ' (already exists, will be reused)' if exists else ''))
    print('release body : %d lines from CHANGELOG [%s]' % (len(body.splitlines()), version))
    print('mode         : %s' % ('APPLY' if APPLY else 'dry run (pass --apply to publish)'))
    if not APPLY:
        return 0

    if not exists:
        sh(['git', 'tag', '-a', tag, '-m', 'Release %s' % version])
        sh(['git', 'push', 'origin', tag])
        print('tag pushed   : %s' % tag)
    else:
        print('tag already present, skipping creation')

    out = sh(['gh', 'release', 'view', tag], check=False)
    if 'Not Found' in out or out == '':
        bf = os.path.join(ROOT, '.release-body.tmp.md')
        io.open(bf, 'w', encoding='utf-8', newline='\n').write(body + '\n')
        try:
            r = sh(['gh', 'release', 'create', tag, '--title', 'FilialConnect %s' % version,
                    '--notes-file', bf])
            print('release      : %s' % r)
        finally:
            os.remove(bf)
    else:
        print('release already exists for %s' % tag)
    return 0


if __name__ == '__main__':
    sys.exit(main())
