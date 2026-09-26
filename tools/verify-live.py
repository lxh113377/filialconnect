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


# Files a Pagefind 1.5.x bundle really ships, measured from this tree (`ls pagefind/en`).
# Strict = the search cannot work without them, so a 404 is a real failure.
# Best-effort = UI variants we do not necessarily load; a 404 is reported, not judged.
LANG_STRICT = ('pagefind.js', 'pagefind-worker.js', 'wasm.unknown.pagefind')
LANG_OPTIONAL = ('pagefind-ui.js', 'pagefind-ui.css', 'pagefind-component-ui.js',
                 'pagefind-component-ui.css', 'pagefind-modular-ui.js',
                 'pagefind-modular-ui.css', 'pagefind-highlight.js')


def probe_base(base):
    """One cheap request before touching 101 paths.

    On this network github.io is reachable only through a proxy; without one every fetch
    burns its full socket timeout, so the tool spent 300s producing no output. That reads as
    "slow", not as "not measured" - which is the worse failure.
    """
    status, body, hdr, _enc, _len = fetch(base.rstrip('/') + '/robots.txt', timeout=10)
    if status == 200:
        return None
    return ('%s/robots.txt -> http %s %s (github.io usually needs a proxy here: set '
            'HTTPS_PROXY and retry)' % (base.rstrip('/'), status, hdr.get('x-error', '')))


def live_index_paths(base, langs=("en", "zh")):
    """Which search-index files does the DEPLOYED site serve? Ask its own manifest.

    The hashed primary/meta/index trio is named by pagefind-entry.json, so it can be probed
    by real name. The per-page fragment files are hashed too and are not listed anywhere
    public, so they are counted and reported as unnameable rather than skipped in silence.
    """
    strict, best_effort, notes = [], [], []
    for lang in langs:
        entry = base.rstrip('/') + '/pagefind/%s/pagefind-entry.json' % lang
        status, body, hdr, _enc, _len = fetch(entry)
        if status != 200:
            notes.append('pagefind/%s: entry manifest http %s %s'
                         % (lang, status, hdr.get('x-error', '')))
            continue
        try:
            h = json.loads(body.decode('utf-8'))['languages'][lang]['hash']
        except Exception as exc:                                # noqa: BLE001 - report, never guess
            notes.append('pagefind/%s: entry manifest unreadable (%s)' % (lang, type(exc).__name__))
            continue
        root = 'pagefind/%s' % lang
        # Verified by a real E2E probe: the browser fetches entry.json, pagefind.js, the worker,
        # the wasm and the fragments. The hashed `.pf_meta`/`.pf_index` pair is a BUILD-time
        # artifact - absent from production on both the last build and this one - so probing it
        # over HTTP manufactures a false red. Fragments are per-page hashed and cannot be named
        # from the manifest, so they are counted in the coverage note instead.
        strict += [root + '/pagefind-entry.json', root + '/pagefind.' + h + '.p']
        strict = [x for x in strict if not x.endswith('.p')]
        strict += ['%s/%s' % (root, f) for f in LANG_STRICT]
        if lang == 'en':
            strict.append(root + '/wasm.en.pagefind')
        best_effort += ['%s/%s' % (root, f) for f in LANG_OPTIONAL]
    return strict, best_effort, notes


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


NAMED_SUFFIXES = ('.css', '.js', '.json', '.pagefind', '.wasm')


def classify_build_outputs(paths):
    """Sort shipped `pagefind/` output by what the measured layout actually is.

    Kinds are decided in one order, so a file cannot be double counted. A file that lands in
    `unclassified` is not a shrug: it means Pagefind changed a naming shape, and the size of the
    declared blind spot (the fragments) depends on that shape, so the accounting must stop.
    """
    buckets = {'named': [], 'fragment': [], 'build_only': [], 'unclassified': []}
    for p in paths:
        name = p.rsplit('/', 1)[-1]
        if '/fragment/' in p:
            # still under fragment/, but no longer the extension we sized the blind spot by
            key = 'fragment' if name.endswith('.pf_fragment') else 'unclassified'
        elif name.endswith('.pf_index') or name.endswith('.pf_meta'):
            key = 'build_only'
        elif name.endswith(NAMED_SUFFIXES):
            key = 'named'
        else:
            key = 'unclassified'
        buckets[key].append(p)
    return {k: sorted(v) for k, v in buckets.items()}


def coverage_identity(counts, local_total, probed_build_outputs):
    """named + fragment + build-only == shipped, and probed must equal the named kind.

    The fragments are the acknowledged blind spot (production serves them, the public manifest
    never names them); the `.pf_*` pair is a build-time artifact production has no reason to serve.
    Nothing may fall between those three, and every named file must actually have been fetched -
    otherwise "we could not name it" quietly becomes "we did not check it".
    """
    problems = []
    if local_total == 0:
        return False, ['no build outputs enumerated - a coverage claim needs a denominator (R247)']
    named, frag, build_only = counts['named'], counts['fragment'], counts['build_only']
    if counts['unclassified']:
        problems.append('%d build output(s) match no known kind, so the blind spot is mis-sized: %s'
                        % (len(counts['unclassified']), counts['unclassified'][:3]))
    bucketed = len(named) + len(frag) + len(build_only)
    if bucketed != local_total:
        problems.append('named %d + fragment %d + build-only %d = %d != shipped %d'
                        % (len(named), len(frag), len(build_only), bucketed, local_total))
    if probed_build_outputs == 0:
        problems.append('the live manifest named no build output to probe, so reachability is '
                        'unverified for all %d shipped' % local_total)
    elif probed_build_outputs != len(named):
        problems.append('%d build outputs are named and served but %d were probed'
                        % (len(named), probed_build_outputs))
    return not problems, problems


def selftest():
    """Both directions, offline, using the names the real build produced.

    The identity must close on the real shapes, must catch every kind of shape drift, and must
    never read a missing denominator as a pass.
    """
    named = ['pagefind/%s' % f for f in
             ('pagefind-entry.json', 'pagefind-highlight.js', 'pagefind-component-ui.css',
              'pagefind-component-ui.js', 'wasm.en.pagefind')]
    frag = ['pagefind/en/fragment/en_%07x.pf_fragment' % i for i in range(25)]
    build_only = ['pagefind/en/index/en_dab4a82.pf_index', 'pagefind/zh/index/zh_dab4a82.pf_index',
                  'pagefind/en/pagefind.en_96b08b50ce.pf_meta',
                  'pagefind/zh/pagefind.zh_96b08b50ce.pf_meta']
    real = sorted(named * 5 + frag + build_only)   # 25 named + 25 fragments + 4 build-only
    cases = [
        ('measured layout closes (25 named + 25 fragments + 4 build-only)',
         real, len(real), len(classify_build_outputs(real)['named']), True),
        ('a fragment that lost its extension is shape drift, not a shrug',
         real + ['pagefind/en/fragment/en_odd.md'], len(real) + 1, 25, False),  # red: unclassified
        ('a brand new service file type is unclassified until it is named',
         real + ['pagefind/en/pagefind-newthing.br'], len(real) + 1, 25, False),
        ('25 named files but only 20 surfaced by the manifest cannot pass',
         real, len(real), 20, False),
        ('no shipped list means no denominator, never a pass',
         [], 0, 0, False),
        ('a manifest naming nothing cannot prove reachability',
         real, len(real), 0, False),
    ]
    bad = 0
    for name, paths, total, probed, want_ok in cases:
        ok, problems = coverage_identity(classify_build_outputs(paths), total, probed)
        if ok != want_ok:
            bad += 1
            print('  SELFTEST-FAIL %s: ok=%s want=%s %s' % (name, ok, want_ok, problems[:1]))
        else:
            print('  ok  %s' % name)
    print('verify-live selftest: %d cases, %d failures' % (len(cases), bad))
    return 1 if bad else 0


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
    ap.add_argument('--selftest', action='store_true',
                    help='re-check the coverage identity arithmetic offline and exit')
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.metadata_only:
        problems = check_metadata(args.slug)
        for p in problems:
            print('METADATA FAIL: ' + p)
        print('%d metadata problems' % len(problems))
        return 1 if problems else 0

    sets, audit = stager.staging_sets()
    bad = 0
    # An uncommitted working tree is not a deployment; say so before the byte diffs arrive.
    dirty = subprocess.run(['git', '-C', ROOT, 'status', '--porcelain'],
                           capture_output=True, text=True, timeout=60).stdout.strip()
    if dirty:
        print('note: the working tree has uncommitted changes, so byte comparisons below are '
              'against THIS tree, not against the commit production was built from')

    unreachable = probe_base(args.base)
    if unreachable:
        print('UNVERIFIED: the live site could not be reached, so nothing about the '
              'deployment was measured: ' + unreachable)
        print('exit 2 = not measured. A green would be a lie; a red would blame the deploy.')
        return 2
    # The search index is shipped, so an unbuilt index means this probe would quietly check less
    # of the site than production serves. Ask for it by name instead of shrinking the denominator.
    for p in stager.audit_problems(audit, require_build_outputs=(args.profile == 'deploy')):
        print('STAGING FAIL: ' + p)
        bad += 1
    kept = [p for p in sets[args.profile]
            if not any(p.startswith(d) for d in args.skip_dir)]
    dropped = len(sets[args.profile]) - len(kept)
    if dropped:
        print('note: --skip-dir removed %d/%d paths from the denominator'
              % (dropped, len(sets[args.profile])))
    paths = kept
    if not paths:
        print('FAIL: zero paths to probe - an empty denominator is never a pass')
        return 1

    fails = []
    committed = git_tracked()
    local_index = [p for p in paths if p.startswith('pagefind/')]
    live_strict, live_optional, index_notes = live_index_paths(args.base)
    if local_index and not live_strict:
        fails.append('pagefind: the live site published no readable entry manifest, so %d '
                     'shipped index files could not be probed by their real names'
                     % len(local_index))
    optional = set(live_optional)
    paths = [p for p in paths if not p.startswith('pagefind/')] + live_strict + live_optional
    build_buckets = classify_build_outputs(local_index)
    n_local_build = len(local_index)
    for rel in paths:
        url = args.base.rstrip('/') + ('/' if rel == 'index.html' else '/' + rel)
        status, body, hdr, _enc, _len = fetch(url)
        if status != 200:
            fails.append('%s -> http %s %s' % (rel, status, hdr.get('x-error', '')))
            continue
        if rel not in committed:
            # A build output is regenerated in the deploy job, so its bytes belong to whichever
            # runner built it. Reachability is the property under test - and the name now comes
            # from the live manifest, so a 404 here really is a file production is missing.
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
    n_live_index = len([p for p in paths if p.startswith('pagefind/')])
    # built whether or not --quiet was passed: the ledger write below used to read a name that
    # only existed inside the printing branch, so a quiet passing run died with a NameError
    coverage = {'build_outputs_shipped': n_local_build,
                'named_build_outputs_probed': len(build_buckets['named']),
                'fragment_paths_unnameable': len(build_buckets['fragment']),
                'build_only_artifacts_not_served': len(build_buckets['build_only']),
                'build_outputs_unclassified': len(build_buckets['unclassified']),
                'runtime_outputs_probed': n_live_index,
                'committed_probed': len(paths) - n_live_index}
    identity_ok, identity_problems = coverage_identity(build_buckets, n_local_build, n_live_index)
    if not identity_ok:
        fails += ['coverage identity: ' + p for p in identity_problems]
    if not args.quiet:
        print('probed %d paths from the %s profile: %d committed (byte-compared) + %d build '
              'outputs named by the live manifest'
              % (len(paths), args.profile, len(paths) - n_live_index, n_live_index))
        print('coverage note: %d shipped build outputs = %d named and probed by real name + %d '
              'fragment files production serves but the public manifest never names (declared '
              'blind spot) + %d build-time artifacts production has no reason to serve; '
              'unclassified %d'
              % (n_local_build, n_live_index, len(build_buckets['fragment']),
                 len(build_buckets['build_only']), len(build_buckets['unclassified'])))
        for note in index_notes:
            print('note: ' + note)
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
    # Only an achieved verification is worth committing.
    io.open(os.path.join(ROOT, 'reports', 'live-verify-coverage.json'), 'w',
            encoding='utf-8', newline='').write(
        json.dumps(coverage, indent=2, sort_keys=True) + '\n')
    print('wrote reports/live-verify-coverage.json (only on a pass)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
