#!/usr/bin/env python3
"""Cut a release: verify the version is agreed across files, tag it, publish the GitHub
Release from the CHANGELOG section that already exists.

Not run in CI on purpose. `tools/test_build.py::t_release` checks the file agreement (cheap,
portable); this script is the one place that touches the shared remote, and it refuses to move
when the sources disagree rather than tagging whatever it finds.

Usage:
  python tools/release.py            # dry run: what would be tagged and shipped
  python tools/release.py --apply    # tag, push tag, create the release
  python tools/release.py --allow-pending   # spare a still-running pipeline (HEAD touches only
                                            # release metadata); RED always blocks
"""
import io
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPLY = '--apply' in sys.argv
ALLOW_PENDING = '--allow-pending' in sys.argv


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


REQUIRED_JOBS = ('quality', 'deploy')
# The post-deploy probe is the only evidence that the *published* site matches the commit being
# tagged. Before round 26 `ci_verdict` lumped every check together, so a release could be cut on
# a commit where the live-site job simply did not exist (v1.6.1 measured: quality + deploy only).
POST_DEPLOY_JOB = 'verify-live'


def classify_checks(pairs):
    """('green'|'red'|'pending'|'unknown', detail) from [(name, status, conclusion), ...].

    Pure on purpose: the network call is one line, but the three ways this can be wrong
    (a job missing, a job still running, a job failed) are all reachable with a fixture.
    A missing post-deploy job is 'unknown', never 'green' - absence of a signal is not a
    passing signal, which is the same rule the perf baseline gate applies to its own fields.
    """
    by_name = {name: (status, conclusion) for name, status, conclusion in pairs}
    detail = ','.join('%s:%s' % (n, by_name[n][1] or by_name[n][0]) for n in sorted(by_name))
    if not by_name:
        return 'unknown', 'no check-runs at all'
    for name in REQUIRED_JOBS:
        if name not in by_name:
            return 'unknown', 'required job %s never reported [%s]' % (name, detail)
    if POST_DEPLOY_JOB not in by_name:
        deploy_status, deploy_concl = by_name.get('deploy', ('queued', None))
        if deploy_status == 'completed' and deploy_concl == 'success':
            return 'unknown', '%s is absent although deploy succeeded - the live site was ' \
                              'never probed for this commit [%s]' % (POST_DEPLOY_JOB, detail)
        return 'pending', '%s has not reported yet [%s]' % (POST_DEPLOY_JOB, detail)
    states = [by_name[n] for n in list(REQUIRED_JOBS) + [POST_DEPLOY_JOB]]
    if any(s != 'completed' for s, _ in states):
        return 'pending', detail
    if any(c != 'success' for _, c in states):
        return 'red', detail
    return 'green', detail


def ci_verdict(sha):
    """('green' | 'red' | 'pending' | 'unknown', detail) for one commit.

    A tag is the one artefact that cannot be quietly moved afterwards, and v1.4.0 was cut on a
    red commit because this script only compared files. So: look at the pipeline before pushing.
    """
    slug = sh(['gh', 'repo', 'view', '--json', 'nameWithOwner', '-q', '.nameWithOwner'], check=False)
    if not slug or '/' not in slug:
        return 'unknown', 'gh could not resolve the repository slug'
    out = sh(['gh', 'api', 'repos/%s/commits/%s/check-runs' % (slug, sha), '--jq',
              '[.check_runs[] | .name + ":" + .status + ":" + (.conclusion // "null")] | join(",")'],
             check=False)
    if not out:
        return 'unknown', 'gh reported no check-runs for %s' % sha[:9]
    pairs = []
    for chunk in out.split(','):
        parts = chunk.rsplit(':', 2)
        if len(parts) == 3:
            pairs.append((parts[0], parts[1], None if parts[2] == 'null' else parts[2]))
    return classify_checks(pairs)


def offline_package(apply):
    """Build (and return the path to) the ZIP a visitor can actually download.

    Every release used to carry zero assets while the README's promise was offline use: the
    archive existed only on one machine, in a different repository. `tools/package-offline.py`
    is reproducible, so the Release is the place the promise can be kept.
    """
    dest = os.path.join(ROOT, 'dist', 'FilialConnect-%s-offline.zip'
                        % json.loads(read('package.json'))['version'])
    if not apply:
        print('offline asset  : would build %s' % os.path.relpath(dest, ROOT))
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'package_offline', os.path.join(ROOT, 'tools', 'package-offline.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    info = mod.build(dest)
    print('offline asset  : %s (%d entries, %.0f KB, sha256 %s)'
          % (os.path.basename(info['path']), info['entries'], info['bytes'] / 1024.0,
             info['sha256'][:12]))
    return info['path']


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
    tag = 'v' + version
    exists = sh(['git', 'tag', '-l', tag])
    verdict, detail = ci_verdict(head)
    if not exists and verdict == 'red':
        problems.append('CI is RED on %s [%s] - a pushed tag cannot be moved, so it has to land '
                        'on a green commit' % (head[:9], detail[:120]))
    elif not exists and verdict == 'pending' and not ALLOW_PENDING:
        problems.append('CI has not finished on %s [%s] - wait for it, or pass --allow-pending '
                        'when HEAD only touches release metadata' % (head[:9], detail[:120]))
    elif not exists and verdict == 'unknown':
        problems.append('CI verdict unknown for %s (%s) - pass --allow-pending only if you have '
                        'checked the pipeline by hand' % (head[:9], detail[:120]))
    if problems:
        print('REFUSING to release:')
        for p in problems:
            print('  - ' + p)
        return 1

    print('version      : %s' % version)
    print('commit       : %s' % head[:9])
    print('ci verdict   : %s (%s)' % (verdict, detail[:150]))
    print('tag          : %s%s' % (tag, ' (already exists, will be reused)' if exists else ''))
    print('release body : %d lines from CHANGELOG [%s]' % (len(body.splitlines()), version))
    print('mode         : %s' % ('APPLY' if APPLY else 'dry run (pass --apply to publish)'))
    asset = offline_package(APPLY)
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
            cmd = ['gh', 'release', 'create', tag, '--title', 'FilialConnect %s' % version,
                   '--notes-file', bf]
            if asset:
                cmd.append(asset)
            r = sh(cmd)
            print('release      : %s' % r)
        finally:
            os.remove(bf)
    else:
        print('release already exists for %s' % tag)
        if asset:
            sh(['gh', 'release', 'upload', tag, asset, '--clobber'])
            print('asset        : uploaded %s' % os.path.basename(asset))
    return 0


if __name__ == '__main__':
    sys.exit(main())
