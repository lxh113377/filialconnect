#!/usr/bin/env python3
"""Verify the live deployment equals the commit that produced it.

Everything else in this repository measures the working tree. Nothing measured the last hop -
Pages staging, the CDN, or a deploy that silently served an older build - so "pipeline green"
and "site broken" were compatible states. This closes that hop, and it is deliberately the only
network-dependent check in the chain: it runs after `deploy`, on `main` pushes only, so a
transient CDN problem cannot block an unrelated pull request.

Usage
  python tools/verify-live.py [--base URL] [--profile deploy] [--skip-dir PREFIX] [--quiet]
Exits 0 only when the staging set is sound and every probed path is reachable and
byte-identical to the repository.
"""
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = 'FilialConnect-verify-live/1.0 (+https://github.com/lxh113377/filialconnect)'


def load_stager():
    """tools/stage-site.py has a hyphen in its name, so it cannot be imported directly."""
    spec = importlib.util.spec_from_file_location(
        'stage_site', os.path.join(ROOT, 'tools', 'stage-site.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git_tracked():
    p = subprocess.run(['git', '-C', ROOT, 'ls-files'], capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise SystemExit('FAIL: git ls-files failed, so nothing could be judged as committed: '
                         + (p.stderr or '')[:120])
    return {f.replace(os.sep, '/') for f in p.stdout.split('\n') if f.strip()}


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Encoding': 'gzip'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            encoding = (r.headers.get('Content-Encoding') or '').lower()
            wire = r.headers.get('Content-Length')
            if encoding == 'gzip':
                body = gzip.decompress(body)
            return r.status, body, {}, encoding, wire
    except urllib.error.HTTPError as e:
        return e.code, b'', {}, '', None
    except Exception as e:                                    # noqa: BLE001 - report, do not guess
        return 0, b'', {'x-error': type(e).__name__ + ': ' + str(e)[:90]}, '', None


def check_wire_size(base, rel, advertised_kb, tolerance=0.05):
    """README advertises the fraud list by its *transferred* size, which is a property of the
    server, not of the repository. Verify the server really compresses and that the compressed
    body matches the number in the copy, or the sentence is an unverified claim again."""
    status, body, hdr, encoding, wire = fetch(base.rstrip('/') + '/' + rel)
    if status != 200:
        return ['%s: http %s %s' % (rel, status, hdr.get('x-error', ''))]
    if encoding != 'gzip':
        return ['%s: served with Content-Encoding=%r, so the advertised compressed size '
                'is not what a visitor downloads' % (rel, encoding or 'identity')]
    try:
        reported = int(wire)
    except (TypeError, ValueError):
        return ['%s: no Content-Length to judge the advertised size against' % rel]
    want = advertised_kb * 1000
    if abs(reported - want) > want * tolerance:
        return ['%s: wire size %d B vs %d KB advertised in README (>%.0f%% off)'
                % (rel, reported, advertised_kb, tolerance * 100)]
    print('wire check: %s transferred=%d B, gzip=yes, README says %d KB' % (
        rel, reported, advertised_kb))
    return []


def fetch_repo_api(slug):
    """One comparison, two transports: the token the runner has, or the `gh` login this
    machine has. Unauthenticated api.github.com answers from a shared proxy IP and its rate
    limit is not ours to spend."""
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN') or ''
    if token:
        req = urllib.request.Request('https://api.github.com/repos/' + slug,
                                     headers={'User-Agent': UA, 'Accept': 'application/vnd.github+json',
                                              'Authorization': 'Bearer ' + token})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    if shutil.which('gh'):
        p = subprocess.run(['gh', 'api', 'repos/' + slug], capture_output=True, text=True, timeout=90)
        if p.returncode == 0 and p.stdout.strip():
            return json.loads(p.stdout)
        raise RuntimeError('gh api failed: ' + (p.stderr or '')[:120])
    raise RuntimeError('no GITHUB_TOKEN and no gh CLI available to read repo metadata')


def check_metadata(slug):
    """The repository's About box is public copy that no file-level gate can see.

    Round 25 banned the revoked "zero dependency" slogan across every public file; the string
    GitHub shows in search results and at the top of the repository kept saying it anyway,
    because it is repository *metadata*, not a file. This reads it back over the API.
    """
    try:
        api = fetch_repo_api(slug)
    except Exception as e:                                     # noqa: BLE001 - a failed read is a red
        return ['could not read repo metadata from GitHub: %s: %s'
                % (type(e).__name__, str(e)[:120])]
    want = json.loads(io.open(os.path.join(ROOT, 'reports', 'repo-metadata.json'),
                              encoding='utf-8').read())
    problems = []
    if api.get('description') != want['description']:
        problems.append('description differs from reports/repo-metadata.json:\n    live: %r'
                        '\n    want: %r' % (api.get('description'), want['description']))
    live_topics = sorted(api.get('topics') or [])
    if live_topics != sorted(want['topics']):
        problems.append('topics differ: live=%s want=%s' % (live_topics, sorted(want['topics'])))
    if api.get('homepage') != want['homepage']:
        problems.append('homepage differs: live=%r want=%r' % (api.get('homepage'), want['homepage']))
    if not problems:
        print('metadata check: description/topics/homepage match the expectation')
    return problems


def main():
    stager = load_stager()
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='https://lxh113377.github.io/filialconnect')
    ap.add_argument('--profile', default='deploy')
    ap.add_argument('--skip-dir', action='append', default=[],
                    help='path prefix to leave out of the probe (repeatable)')
    ap.add_argument('--wire-asset', default='assets/data/destroylist-domains.txt',
                    help='path whose transferred size README advertises')
    ap.add_argument('--quiet', action='store_true')
    ap.add_argument('--metadata-only', action='store_true',
                    help='check the repository About box and skip the file probe')
    ap.add_argument('--skip-metadata', action='store_true')
    ap.add_argument('--slug', default='lxh113377/filialconnect')
    args = ap.parse_args()

    if args.metadata_only:
        problems = check_metadata(args.slug)
        for p in problems:
            print('METADATA FAIL: ' + p)
        print('%d metadata problems' % len(problems))
        return 1 if problems else 0

    sets, audit = stager.staging_sets()
    bad = 0
    # The search index is shipped, so an unbuilt index means this probe would quietly check less
    # of the site than production serves. Ask for it by name instead of shrinking the denominator.
    for p in stager.audit_problems(audit, require_build_outputs=(args.profile == 'deploy')):
        print('STAGING FAIL: ' + p)
        bad += 1
    paths = [p for p in sets[args.profile]
             if not any(p.startswith(d) for d in args.skip_dir)]
    if not paths:
        print('FAIL: zero paths to probe - an empty denominator is never a pass')
        return 1

    fails = []
    committed = git_tracked()
    for rel in paths:
        url = args.base.rstrip('/') + ('/' if rel == 'index.html' else '/' + rel)
        status, body, hdr, _enc, _len = fetch(url)
        if status != 200:
            fails.append('%s -> http %s %s' % (rel, status, hdr.get('x-error', '')))
            continue
        if rel not in committed:
            # A build output (the search index) is regenerated in the deploy job, so its bytes
            # belong to whichever runner built it. Reachability is the property under test.
            continue
        local = hashlib.sha256(open(os.path.join(ROOT, rel), 'rb').read()).hexdigest()
        remote = hashlib.sha256(body).hexdigest()
        if remote != local:
            fails.append('%s -> bytes differ (local %s, live %s)' % (rel, local[:10], remote[:10]))
    readme = io.open(os.path.join(ROOT, 'README.md'), encoding='utf-8').read()
    advertised = re.search(r'gzip\s*后\s*(\d+)\s*KB', readme)
    if not advertised:
        print('STAGING FAIL: README no longer states the "gzip 后 N KB" wire size that '
              'tools/verify-live.py is supposed to re-measure')
        bad += 1
    else:
        fails += check_wire_size(args.base, args.wire_asset, int(advertised.group(1)))
    if not args.skip_metadata:
        fails += check_metadata(args.slug)
    if not args.quiet:
        print('probed %d paths from the %s profile' % (len(paths), args.profile))
    if fails or bad:
        for f in fails:
            print('LIVE FAIL: ' + f)
        print('%d/%d live paths bad, %d staging problems' % (len(fails), len(paths), bad))
        return 1
    head = subprocess.run(['git', '-C', ROOT, 'rev-parse', '--short', 'HEAD'],
                          capture_output=True, text=True).stdout.strip()
    print('PASS: live site matches %s - %d committed files byte-identical, %d build outputs reachable'
          % (head, len([p for p in paths if p in committed]),
             len([p for p in paths if p not in committed])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
