#!/usr/bin/env python3
"""Single source of truth for "which files leave this repository".

Two hand-copied `cp -r` lists used to decide that: `.github/workflows/deploy-pages.yml`
staged the site for Pages, `.github/workflows/ci.yml` staged a *different* set for the
local server that Lighthouse measures. The two already disagree (CI serves `content/`,
which is generator input and no page fetches; Pages serves `sw.js` and `pagefind/`, which
CI never measures). A page that references a path only the other list carries would be
green in CI and 404 in production, which is the shrinking-denominator failure class with
the largest blast radius: the only reader who notices is an older visitor.

Profiles
  deploy  what GitHub Pages serves.
  probe   what the local CI server serves. Deliberately a subset: the service worker and
          the search index are excluded so Lighthouse measures a first visit, not a
          cached second one, and the Markdown docs are not fetched by any page.

Usage
  python tools/stage-site.py list   [--profile deploy]
  python tools/stage-site.py stage  --out DIR [--profile deploy]
  python tools/stage-site.py check  [--write]      # compare/refresh reports/deploy-staging.json
"""
import fnmatch
import hashlib
import io
import json
import os
import posixpath
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join('reports', 'deploy-staging.json')
BUILD_OUTPUT_DIRS = ('pagefind',)          # gitignored, built by tools/build-search.mjs
DOC_FILES = ('README.md', 'LICENSE', 'SECURITY.md', 'SOURCES.md', 'CONTRIBUTING.md')
# Referenced by the page but withheld from the probe server on purpose (see module docstring).
PROBE_EXCLUDE_PATTERNS = ('sw.js', 'workbox-*.js', 'manifest.json', 'pagefind/*', '*.md')
FLOOR = 20                                  # a scan that finds 3 references is broken, not tidy

SRC_HREF = re.compile(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', re.I)
CSS_URL = re.compile(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)', re.I)
SCHEME_PREFIX = ('http://', 'https://', 'mailto:', 'tel:', 'data:', 'javascript:', '//')
# The hand-copied list shipped all of assets/, so the derived set must too: a new image that
# nothing references yet still has to be reachable, and `assets_unshipped` says the day that
# stops being true.
ALWAYS_SHIP_DIRS = ('assets',)


def site_base():
    """Our own origin, read from sitemap.xml rather than restated here.

    Pages serves the site under a subpath, so an og:image written as an absolute URL is a real
    reference to a repository file, and skipping it would take the social cards offline.
    """
    m = re.search(r'<loc>(https?://[^<]*/)[^<]*</loc>', read('sitemap.xml'))
    if not m:
        raise SystemExit('FAIL: sitemap.xml has no <loc> to derive the site base from')
    return m.group(1)


def read(fp):
    return io.open(os.path.join(ROOT, fp), encoding='utf-8').read()


def repo_files():
    out = set()
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel = os.path.relpath(dirpath, ROOT).replace(os.sep, '/')
        if rel == '.':
            rel = ''
        dirnames[:] = [d for d in dirnames if d not in ('.git', 'node_modules', '__pycache__',
                                                       '.lighthouseci', '.bak-neg')]
        for name in filenames:
            out.add(posixpath.join(rel, name).lstrip('/') if rel else name)
    return out


def html_pages():
    return sorted(['index.html', '404.html'] +
                  [p for p in repo_files() if p.startswith('pages/') and p.endswith('.html')])


def resolve(page, ref, origin=None):
    """Turn one src/href value into a repo-relative path, or None if it leaves the page tree.

    Root-absolute values return None: Pages serves this site under /filialconnect/, so a
    leading slash is not the repository root and a page that relied on one would 404.
    """
    low = ref.strip().lower()
    if origin and low.startswith(origin.lower()):
        tail = ref[len(origin):].split('#')[0].split('?')[0].strip()
        return posixpath.normpath(tail) if tail else 'index.html'
    if low.startswith(SCHEME_PREFIX):
        return None
    clean = ref.split('#')[0].split('?')[0].strip()
    if not clean or clean.startswith('/'):
        return None
    base = posixpath.dirname(page)
    return posixpath.normpath(posixpath.join(base, clean))


def html_refs():
    """Every local path a deployed page names: src/href, inline css url(), and absolute self-URLs."""
    origin = site_base()
    found = {}
    for page in html_pages():
        text = read(page)
        for ref in SRC_HREF.findall(text) + CSS_URL.findall(text):
            path = resolve(page, ref, origin)
            if path:
                found.setdefault(path, set()).add(page)
    return found


def manifest_refs():
    """manifest.json names the icons an installer fetches; no HTML element points at them."""
    man = json.loads(read('manifest.json').lstrip('﻿'))
    out = []
    for key in ('icons', 'screenshots'):
        for item in man.get(key, []):
            src = (item.get('src') or '').lstrip('/')
            if src:
                out.append(('manifest.json:%s' % key, src))
    return out


def dynamic_refs():
    """Paths a script computes at runtime, so no attribute scan can see them.

    Each entry names the file that produces it: if that file stops referencing the
    pattern the entry has to be revisited, and the ledger's `provenance` block is where
    a reader checks whether the pattern still exists.
    """
    entries = []
    sw = read('sw.js')
    entries.append(('sw.js (registered by assets/js/main.js)', 'sw.js'))
    for imported in re.findall(r"importScripts\(\s*['\"]([^'\"]+)['\"]", sw):
        entries.append(('sw.js:importScripts', posixpath.normpath(imported.lstrip('./'))))
    # workbox generates an unhashed chunk name and loads it through its own AMD shim, which
    # appends ".js" at request time - so the module id in sw.js is not a filename yet.
    for chunk in re.findall(r'define\(\[\s*"(\./[\w.\-/]+)"', sw):
        name = posixpath.normpath(chunk.lstrip('./'))
        entries.append(('sw.js:define', name if name.endswith('.js') else name + '.js'))
    entries.append(('sw.js:precache manifest', 'manifest.json'))
    # fetch() resolves against the *document* URL, not the script file. The self-check lives on
    # pages/fraud-database.html and is guarded by that page's element ids, so its '../assets/..'
    # is a /pages/-relative path. If the checker ever moves to index.html this line is where the
    # wrong resolution would be silently baked in.
    for script in ('assets/js/main.js', 'assets/js/search.js'):
        body = read(script)
        for literal in re.findall(r"['\"](\.\./assets/[\w.\-/]+)['\"]", body):
            entries.append(('%s:fetch target' % script,
                            posixpath.normpath(posixpath.join('pages', literal))))
    if 'pagefind/' in read(os.path.join('assets', 'js', 'search.js')):
        for d in BUILD_OUTPUT_DIRS:
            entries.append(('assets/js/search.js:dynamic import', d))
    # The fraud feed refresher writes both files, and the checker reads the meta one.
    entries.append(('assets/data is fetched at runtime', 'assets/data'))
    return entries


def expand(pattern):
    """A ledger entry -> the concrete files it claims. Directories expand; globs match.

    Dot-files are never returned: GitHub Pages treats a leading dot as "not part of the site"
    (the same rule that hides .github/), so staging `assets/images/.gitkeep` would put a path in
    the ledger that no server ever answers. It measured a 404 rather than take that on trust.
    """
    files = {f for f in repo_files()
             if not posixpath.basename(f).startswith('.')}
    if pattern.endswith('/') or pattern in BUILD_OUTPUT_DIRS:
        prefix = pattern.rstrip('/') + '/'
        return {f for f in files if f.startswith(prefix)}
    if os.path.isdir(os.path.join(ROOT, pattern.replace('/', os.sep))):
        prefix = pattern.rstrip('/') + '/'
        return {f for f in files if f.startswith(prefix)}
    if any(ch in pattern for ch in '*?['):
        return {f for f in files if fnmatch.fnmatch(f, pattern)}
    return {pattern} if pattern in files else set()


def is_build_output(rel):
    """A path that a downstream build step regenerates, so its bytes belong to a runner."""
    return rel.startswith(tuple(d + '/' for d in BUILD_OUTPUT_DIRS))


def ledger_files(paths):
    """The part of a profile that a checkout can be compared against deterministically.

    The ledger used to list the search index's 52 shard files. That made `check` order-dependent:
    run it before `build-search.mjs index` - as CI does on a fresh checkout, where pagefind/ does
    not exist - and the pattern resolves to nothing, so the gate that is supposed to catch drift
    became the drift. Committed files are what a ledger can honestly pin.
    """
    return [p for p in paths if not is_build_output(p)]


def staging_sets():
    """Return {'deploy': …, 'probe': …} as sorted file lists, plus the audit trail."""
    refs = html_refs()
    dyn = dynamic_refs() + manifest_refs()
    unresolved, absent_outputs = [], []
    for origin, pattern in dyn:
        if expand(pattern):
            continue
        if pattern in BUILD_OUTPUT_DIRS:
            absent_outputs.append(pattern)
        else:
            unresolved.append('%s -> %s' % (origin, pattern))
    precache = sorted({u.strip('/') for u in
                       re.findall(r'\{url:"([^"]+)"', read('sw.js'))})
    deploy = {p for p in html_pages()} | {'404.html', 'sitemap.xml', 'robots.txt'}
    for _origin, pattern in dyn:
        deploy |= expand(pattern)
    for claim in ALWAYS_SHIP_DIRS:
        deploy |= expand(claim)
    deploy |= set(DOC_FILES)
    # References are deliberately NOT merged in: a page may name a path nobody decided to ship,
    # and folding it in silently would make the check below impossible to fail. It has to be a
    # decision recorded here, not a side effect of someone typing src="…".
    missing = sorted(p for p in deploy if p not in repo_files())
    probe = {f for f in deploy if not any(fnmatch.fnmatch(f, pat) for pat in PROBE_EXCLUDE_PATTERNS)}
    probe_extra = sorted(probe - deploy)
    return {'deploy': sorted(deploy), 'probe': sorted(probe)}, {
        'html_refs': sorted(refs),
        'refs_not_staged': sorted(p for p in refs if p not in deploy),
        'dynamic_patterns': ['%s -> %s' % (o, p) for o, p in dyn],
        'unresolved_dynamic': sorted(unresolved),
        'build_outputs_absent': sorted(set(absent_outputs)),
        # The service worker promises these URLs are available offline; if one is not staged,
        # the promise is a 404 with a nice cache name.
        'precache_not_staged': sorted(u for u in precache if u not in deploy),
        'missing_from_disk': missing,
        'probe_only': probe_extra,
    }


def build_ledger():
    sets, audit = staging_sets()
    body = {
        'generated_by': 'tools/stage-site.py',
        'do_not_edit': 'run: python tools/stage-site.py check --write',
        'floor': FLOOR,
        'profiles': {name: {'committed_count': len(ledger_files(paths)),
                            'committed_files': ledger_files(paths),
                            'build_outputs_declared': sorted(BUILD_OUTPUT_DIRS)}
                     for name, paths in sets.items()},
        'probe_excludes': list(PROBE_EXCLUDE_PATTERNS),
        # `build_outputs_absent` is the one audit field that legitimately differs between a fresh
        # checkout and a built tree; storing it would put the same non-determinism back in.
        'audit': {k: sorted(v) if isinstance(v, (list, set, dict)) else v
                  for k, v in audit.items() if k != 'build_outputs_absent'},
    }
    return body


def sha(data):
    return hashlib.sha256(data).hexdigest()


def serialise(body):
    return json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + '\n'


def audit_problems(audit, require_build_outputs=False):
    """Non-empty audit lists that mean the enumerator stopped seeing reality."""
    out = []
    if audit['refs_not_staged']:
        out.append('a page references a path that is not deployed (would 404 live): %s'
                   % audit['refs_not_staged'][:3])
    if audit['unresolved_dynamic']:
        out.append('dynamic pattern matches no file: %s' % audit['unresolved_dynamic'][:3])
    if require_build_outputs and audit['build_outputs_absent']:
        out.append('refusing to stage a site whose search index was never built: %s'
                   % audit['build_outputs_absent'])
    if audit['precache_not_staged']:
        out.append('sw.js precaches a path that is not staged: %s' % audit['precache_not_staged'][:3])
    if audit['missing_from_disk']:
        out.append('staged path missing from disk: %s' % audit['missing_from_disk'][:3])
    if audit['probe_only']:
        out.append('probe serves a file Pages does not: %s' % audit['probe_only'][:3])
    return out


def cmd_stage(profile, out):
    sets, audit = staging_sets()
    problems = audit_problems(audit, require_build_outputs=(profile == 'deploy'))
    if problems:
        raise SystemExit('FAIL: staging set is not sound\n  ' + '\n  '.join(problems))
    paths = sets[profile]
    destination = os.path.abspath(out)
    if os.path.isdir(destination):
        shutil.rmtree(destination)
    for rel in paths:
        target = os.path.join(destination, *rel.split('/'))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, rel), target)
    print('staged profile %s -> %s: %d files' % (profile, out, len(paths)))
    return 0


def cmd_check(write):
    body = build_ledger()
    problems = audit_problems(body['audit'])
    if len(body['audit']['html_refs']) < FLOOR:
        problems.append('only %d html references enumerated, floor is %d'
                        % (len(body['audit']['html_refs']), FLOOR))
    if problems:
        print('FAIL: staging set is not sound')
        for p in problems:
            print('  - ' + p)
        return 1
    fresh = serialise(body)
    path = os.path.join(ROOT, LEDGER)
    if write:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        io.open(path, 'w', encoding='utf-8', newline='\n').write(fresh)
        print('wrote %s: deploy=%d probe=%d refs=%d (build outputs declared: %s)' % (
            LEDGER, body['profiles']['deploy']['committed_count'],
            body['profiles']['probe']['committed_count'], len(body['audit']['html_refs']),
            ','.join(body['profiles']['deploy']['build_outputs_declared'])))
        return 0
    if not os.path.isfile(path):
        print('FAIL: %s is not committed (run: check --write)' % LEDGER)
        return 1
    committed = io.open(path, encoding='utf-8').read()
    if sha(committed.encode()) != sha(fresh.encode()):
        print('FAIL: %s is stale - the staging set moved without the ledger' % LEDGER)
        old = json.loads(committed)
        for name in ('deploy', 'probe'):
            o = set(old['profiles'][name].get('committed_files', []))
            n = set(body['profiles'][name]['committed_files'])
            if o != n:
                print('  %s: -%s +%s' % (name, sorted(o - n)[:4], sorted(n - o)[:4]))
        return 1
    print('staging ledger in sync: deploy=%d probe=%d refs=%d dynamic=%d' % (
        body['profiles']['deploy']['committed_count'],
        body['profiles']['probe']['committed_count'],
        len(body['audit']['html_refs']), len(body['audit']['dynamic_patterns'])))
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    verb = argv[0]
    profile = 'deploy'
    out = None
    if '--profile' in argv:
        profile = argv[argv.index('--profile') + 1]
    if '--out' in argv:
        out = argv[argv.index('--out') + 1]
    if verb == 'list':
        sets, _ = staging_sets()
        for p in sets[profile]:
            print(p)
        return 0
    if verb == 'stage':
        if not out:
            raise SystemExit('stage needs --out DIR')
        return cmd_stage(profile, out)
    if verb == 'check':
        return cmd_check('--write' in argv)
    print('unknown verb: %s' % verb)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
