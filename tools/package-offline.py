#!/usr/bin/env python3
"""Build the offline ZIP: the one deliverable a non-developer can actually use.

The site's headline promise is that it works without a network, and the artifact that carries
that promise used to be produced by a script living outside this repository. Two consequences,
both measured: a visitor to a Release could not download what the README describes, and nobody
who cloned this repository could rebuild the file the competition was handed. So the packager
belongs here, next to the ledger that says which files ship.

Entry names stay ASCII and timestamps are pinned to the version, so the same commit always
produces the same bytes (`--verify` proves it).

Usage
  python tools/package-offline.py                 # build into dist/
  python tools/package-offline.py --out PATH
  python tools/package-offline.py --verify        # build twice, require identical bytes
"""
import argparse
import hashlib
import io
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

PREFIX = 'filialconnect/'
# Source a reviewer needs, beyond what a browser fetches. `.github/` stays out on purpose: the
# workflows are evidence about the repository, not part of the deliverable, and the earlier
# archive (built outside this repo) made the same cut.
SOURCE_DIRS = ('tools', 'content', 'reports')
SOURCE_FILES = ('CHANGELOG.md', 'CODE_OF_CONDUCT.md', 'AGENTS.md', '.htmlhintrc',
                'package.json', 'package-lock.json', '.gitattributes')
EXCLUDE_NAMES = {'.gitkeep'}
# Pagefind resolves its shards over HTTP, so an index copied to a phone is unreadable weight.
DROP_DIRS = ('pagefind', '_search', '.github', '.git', 'node_modules', '__pycache__',
             '.lighthouseci', '.lh-tmp', '_site', 'dist', '.bak-neg')
EPOCH = (1980, 1, 1, 0, 0, 0)          # the ZIP epoch: lower is not representable, higher drifts


def load_stager():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'stage_site', os.path.join(ROOT, 'tools', 'stage-site.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def repo_version():
    pkg = json.loads(io.open(os.path.join(ROOT, 'package.json'), encoding='utf-8').read())
    return pkg['version']


def members():
    """Every file in the package, as (abs_path, arcname)."""
    stager = load_stager()
    sets, audit = stager.staging_sets()
    problems = stager.audit_problems(audit)
    if problems:
        raise SystemExit('FAIL: refusing to package an unsound staging set\n  ' + '\n  '.join(problems))
    site = [f for f in sets['deploy'] if not any(f.startswith(d) for d in DROP_DIRS)]
    extra = []
    for d in SOURCE_DIRS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, d)):
            dirnames[:] = sorted(x for x in dirnames if x not in DROP_DIRS)
            for name in sorted(filenames):
                if name in EXCLUDE_NAMES or name.endswith(('.pyc', '.zip')):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, name), ROOT).replace(os.sep, '/')
                extra.append(rel)
    extra += [f for f in SOURCE_FILES if os.path.isfile(os.path.join(ROOT, f))]
    paths = sorted(set(site) | set(extra))
    out = []
    for rel in paths:
        full = os.path.join(ROOT, *rel.split('/'))
        if os.path.isfile(full):
            out.append((full, PREFIX + rel))
    return out, {'site': len(site), 'source': len(extra), 'total': len(paths)}


def build(out_path):
    entries, counts = members()
    bad = [arc for _f, arc in entries if any(ord(c) > 127 for c in arc)]
    if bad:
        raise SystemExit('FAIL: non-ASCII entry names (%d), first: %s' % (len(bad), bad[0]))
    missing = [f for f, _a in entries if not os.path.isfile(f)]
    if missing:
        raise SystemExit('FAIL: %d listed members are not files' % len(missing))
    parent = os.path.dirname(os.path.abspath(out_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.exists(out_path):
        os.remove(out_path)
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for full, arc in entries:
            info = zipfile.ZipInfo(arc, date_time=EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with io.open(full, 'rb') as fh:
                zf.writestr(info, fh.read())
    with zipfile.ZipFile(out_path) as zf:
        names = zf.namelist()
        assert len(names) == len(entries), 'entry count drift: %d vs %d' % (len(names), len(entries))
        corrupt = zf.testzip()
        assert corrupt is None, 'corrupt member: %s' % corrupt
    digest = hashlib.sha256(io.open(out_path, 'rb').read()).hexdigest()
    return {'path': out_path, 'entries': len(names), 'bytes': os.path.getsize(out_path),
            'sha256': digest, 'counts': counts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=None)
    ap.add_argument('--verify', action='store_true', help='rebuild and require identical bytes')
    args = ap.parse_args()
    version = repo_version()
    out = args.out or os.path.join(ROOT, 'dist', 'FilialConnect-%s-offline.zip' % version)
    first = build(out)
    print('wrote %s: %d entries, %.0f KB, sha256 %s' % (
        os.path.basename(first['path']), first['entries'], first['bytes'] / 1024.0,
        first['sha256'][:12]))
    print('  composition: %d site files + %d source files'
          % (first['counts']['site'], first['counts']['source']))
    if not args.verify:
        return 0
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        second = build(os.path.join(td, 'again.zip'))
    if second['sha256'] != first['sha256']:
        print('FAIL: the package is not reproducible (%s vs %s)'
              % (first['sha256'][:12], second['sha256'][:12]))
        return 1
    print('reproducible: two builds of %s agree byte for byte' % version)
    return 0


if __name__ == '__main__':
    sys.exit(main())
