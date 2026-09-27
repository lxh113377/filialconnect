#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Do the paths this repository's own documents claim actually resolve?

Round 46's denominator first: widening close-out gate 15 ("a cited artefact must be tracked") to
the public docs produced **110 unresolved backticked strings**, and counting them that way was
wrong - the unit matters. Classified: 1 deliberate cross-repository citation set (17 items,
`_internal/...`, invisible to `git archive HEAD` by design), 41 prose/domain/fixture fragments with
no slash, 24 bare-name shorthands that do exist elsewhere in the tree, and exactly **1 real dead
path claim** (`rootlist/online_root_domains.txt` in SOURCES.md, which is a file inside the *upstream*
repository). A judge aimed at all 110 would have been 109 false alarms and one truth; aimed at the
unit, it has one job.

So the rule is narrow and the exemptions must be earned:
  * `_internal/...` and `PROJECT_MEMORY.md` are archive-side - exempt, but the exemption is only
    valid while `git archive HEAD` really ships no such file (proved by `archive_has_no_internal()`,
    not asserted);
  * an upstream path is exempt only when the **same line** names the owning `owner/repo`, and that
    owner is in UPSTREAM_OWNERS below - delete the attribution and the reference goes dead;
  * anything else with a slash must resolve from the repository root or from the citing file's own
    directory.

    python tools/doc_citations.py            # report
    python tools/doc_citations.py --check   # the judge's mode (used by tools/test_build.py)
    python tools/doc_citations.py --selftest
"""
import argparse
import glob
import io
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEP = os.sep
#: a path claim needs an extension on its last segment. Without it the regex also matches
#: `before/after`, `--write/--verify/--check`, `.py/.json/.yml`, `actions/checkout` - round 46's
#: first run called 17 of those "dead links", which is the same error as counting 110 references
#: as defects: the unit, not the number.
REF = re.compile(r'`([A-Za-z0-9_.\-一-鿿]+(?:/[A-Za-z0-9_.\-一-鿿]+)+\.[A-Za-z0-9]{1,6})`')
OWNER = re.compile(r'\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b')
#: whose paths may be cited un-resolved, and why. Adding an entry means naming a real upstream.
UPSTREAM_OWNERS = {
    'phishdestroy/destroylist': 'the fraud-domain list we download; rootlist/… lives there',
    'withastro/starlight': 'documentation upstream cited for comparison',
    'dequelabs/axe-core': 'accessibility engine referenced by name in docs',
}
ARCHIVE_ONLY = ('_internal/', 'PROJECT_MEMORY.md')
DOCS = ('*.md', 'docs/*.md')


def norm(p):
    return p.replace(SEP, '/')


def documents(root=None):
    root = root or ROOT
    out = []
    for pat in DOCS:
        out += glob.glob(os.path.join(root, pat))
    return sorted(set(out))


def archive_has_no_internal(root=None):
    """Prove the archive-side exemption from member NAMES.

    The first version ran `git archive HEAD` and searched the raw tar bytes for `_internal/` - which
    reported "the archive ships archive files!" because CHANGELOG.md's *content* mentions that path.
    A proof that reads the thing it is supposed to exclude is not a proof. (`git archive --list` was
    the second attempt and it prints nothing at all here - so the function returned None, i.e.
    "cannot prove", which is the only honest answer an empty listing can ever produce.)
    """
    p = subprocess.run(['git', 'ls-tree', '-r', '--name-only', 'HEAD'], cwd=root or ROOT,
                       capture_output=True, text=True, encoding='utf-8', errors='replace',
                       timeout=300)
    if p.returncode != 0:
        return None                      # cannot prove -> cannot claim
    names = [ln.strip().replace(SEP, '/') for ln in (p.stdout or '').splitlines() if ln.strip()]
    if not names:
        return None                      # an empty listing proves nothing either
    return not any(n == '_internal' or n.startswith('_internal/') for n in names)


def escape_to(ref):
    """(escaped_above_root_depth, residual path) for a reference that walks out of the repository.

    `../_internal/build_zip.py` in a public document is an archive-side reference, and it must be
    classified that way **without looking outside the repository**: the first version resolved paths
    against the filesystem, so it "resolved" on my machine (the archive happens to be a sibling
    directory) and was a dead link in a clean checkout. A judge whose verdict depends on what sits
    next to the checkout is not a judge. The residual after climbing out is what the author means,
    so `_internal/...` is recognised as archive-side while `../../Windows/win.ini` is not.
    """
    out, up = [], 0
    for p in ref.split('/'):
        if p == '..':
            if out:
                out.pop()
            else:
                up += 1
        elif p not in ('', '.'):
            out.append(p)
    return up, '/'.join(out)


def classify(ref, line, doc_dir, root=None):
    root = root or ROOT
    if any(ref.startswith(a) or ref == a for a in ARCHIVE_ONLY):
        return 'archive-exempt'
    up, residual = escape_to(ref)
    if up:
        # an escaped reference is archive-side exactly when what remains after climbing out is an
        # archive-only name; `../../Windows/win.ini` escapes too but proves nothing about our repo
        if any(residual == a or residual.startswith(a) for a in ARCHIVE_ONLY):
            return 'archive-exempt'
        return 'dead'
    if resolve(ref, doc_dir, root):
        return 'resolves'
    for owner in UPSTREAM_OWNERS:
        # co-location on the same logical line is the safety property, not left-to-right order:
        # prose legitimately reads "the file y/z.txt in owner/repo" as often as the reverse, and
        # ordering-based attribution failed on my own CHANGELOG sentence the day it shipped
        if owner in line:
            return 'upstream-attributed'
    return 'dead'


def resolve(ref, doc_dir, root=None):
    root = root or ROOT
    rel = ref.replace('/', SEP)
    return os.path.exists(os.path.join(root, rel)) or os.path.exists(os.path.join(doc_dir, rel))


def logical_lines(text):
    """Markdown source lines joined with their continuation lines.

    Attributing "on the same line" against raw source lines means re-wrapping a paragraph - a pure
    formatting change - can turn an attributed upstream citation into a dead link. The unit has to
    be the sentence-level logical line, so continuation indent is folded in.
    """
    out = []
    for raw in text.splitlines():
        if out and raw.startswith(('  ', '\t')) and not raw.startswith(('- ', '* ')):
            out[-1] = out[-1] + ' ' + raw.strip()
        else:
            out.append(raw.rstrip())
    return out


def scan(root=None, lines=None):
    """Counts by class plus the dead list. `lines` is the selftest seam (an in-memory file set)."""
    root = root or ROOT
    counts = dict.fromkeys(('resolves', 'archive-exempt', 'upstream-attributed', 'dead'), 0)
    dead = []
    # `lines` is an in-memory population: the keys ARE the document names, so nothing is opened.
    # A selftest seam that still hits the disk tests the fixture, not the judge.
    files = ([(norm(os.path.relpath(p, root)), io.open(p, encoding='utf-8').read())
              for p in documents(root)] if lines is None
             else sorted(lines.items()))
    for rel_doc, text in files:
        for line in logical_lines(text):
            for m in REF.finditer(line):
                ref = m.group(1)
                if ' ' in ref:
                    continue
                kind = classify(ref, line, os.path.dirname(os.path.join(root, rel_doc)), root)
                counts[kind] += 1
                if kind == 'dead':
                    dead.append('%s: %s' % (rel_doc, ref))
    counts['documents'] = len(files)
    return counts, sorted(set(dead))


def issues(counts, dead, internal_proved):
    bad = []
    if dead:
        bad.append('%d dead path claim(s): %s' % (len(dead), '; '.join(dead)[:200]))
    if not counts['documents']:
        bad.append('no documents scanned - an empty population is not a pass')
    if internal_proved is not True:
        bad.append('the `_internal/` exemption could not be proved against `git archive HEAD` '
                   '(%r) - an exemption nobody verified is a hole, not a rule' % internal_proved)
    if not counts['archive-exempt'] and not counts['upstream-attributed'] and not counts['resolves']:
        bad.append('nothing was classified at all - the extractor matches no reference, so it '
                   'cannot be trusted to find a dead one either')
    return bad


def report():
    counts, dead = scan()
    proved = archive_has_no_internal()
    bad = issues(counts, dead, proved)
    print('citations: %s' % ' '.join('%s=%d' % (k, counts[k]) for k in
                                      ('documents', 'resolves', 'archive-exempt',
                                       'upstream-attributed', 'dead')))
    print('archive ships no _internal/: %r' % proved)
    for d in dead:
        print('  DEAD ' + d)
    print('CITATIONS-%s: %d doc(s), %d resolved, %d exempt, %d dead'
          % ('OK' if not bad else 'FAIL', counts['documents'], counts['resolves'],
             counts['archive-exempt'] + counts['upstream-attributed'], len(dead)))
    return 1 if bad else 0


def selftest():
    import tempfile
    tmp = tempfile.mkdtemp(prefix='cites_')
    os.makedirs(os.path.join(tmp, 'sub'))
    io.open(os.path.join(tmp, 'sub', 'exists.md'), 'w', encoding='utf-8', newline='\n').write(
        'nothing here\n')
    io.open(os.path.join(tmp, 'SOURCES.md'), 'w', encoding='utf-8', newline='\n').write(
        'upstream: `phishdestroy/destroylist` root file `rootlist/online_root_domains.txt`\n'
        'archive harness: `_internal/audit_dupes.py`\n'
        'real file: `sub/exists.md`\n'
        'a bare claim: `tools/nope-does-not-exist.py`\n')
    lines = {'SOURCES.md': io.open(os.path.join(tmp, 'SOURCES.md'), encoding='utf-8').read()}
    counts, dead = scan(tmp, lines)
    cases = [
        ('a slash path that exists in the tree resolves', counts['resolves'] >= 1, str(counts)),
        ('an upstream path named on a line that also names its owner is attributed',
         counts['upstream-attributed'] >= 1 and not any('online_root_domains' in x for x in dead),
         str(dead[:3])),
        ('archive-only paths are exempt, not counted dead',
         counts['archive-exempt'] >= 1 and not any('_internal' in x for x in dead), str(dead[:3])),
        ('a slash path with nothing behind it IS dead and is named',
         any('nope-does-not-exist' in x for x in dead), str(dead[:3])),
    ]
    # every exemption has to be shown to be load-bearing, or it is just a hole with a comment
    solo = {'X.md': 'root file `rootlist/online_root_domains.txt`\n'}
    c2, d2 = scan(tmp, solo)
    cases.append(('remove the upstream attribution from the line and the same path turns DEAD',
                  any('online_root_domains' in x for x in d2) and c2['upstream-attributed'] == 0,
                  str(d2[:2])))
    c3, d3 = scan(tmp, {'X.md': 'see `tools/nope-does-not-exist.py`\n'})
    cases.append(('a document with only a dead claim still reports it (no稀释 by volume)',
                  len(d3) == 1, str(d3)))
    # re-wrapping a paragraph is a formatting change, so it must not move a reference between classes
    wrapped = {'Y.md': ('upstream `phishdestroy/destroylist` root list file\n'
                        '  `rootlist/online_root_domains.txt` here\n')}
    unwrapped = {'Y.md': ('upstream `phishdestroy/destroylist` root list file '
                          '`rootlist/online_root_domains.txt` here\n')}
    cw, dw = scan(tmp, wrapped)
    cu, du = scan(tmp, unwrapped)
    cases.append(('attribution survives re-wrapping the same paragraph (unit is the logical line)',
                  not dw and not du and cw['upstream-attributed'] == cu['upstream-attributed'] == 1,
                  'wrapped_dead=%s unwrapped_dead=%s' % (dw, du)))
    far = {'Z.md': ('upstream `phishdestroy/destroylist` is mentioned first\n\n'
                    'and much later the bare path `rootlist/online_root_domains.txt` appears\n')}
    cf, df = scan(tmp, far)
    cases.append(('an owner named in a DIFFERENT paragraph does not license the path',
                  any('online_root_domains' in x for x in df) and cf['upstream-attributed'] == 0,
                  str(df[:2])))
    # the exact strings my first version called "dead links" - this is the counter-case for the
    # unit, not for the resolver, so it must stay even while everything else is green
    noise = {'N.md': ('compare `before/after` and pass `--write/--verify/--check`; extensions like '
                       '`.py/.json/.yml`; markers `BEGIN/END`; the action `actions/checkout` and '
                       '`actions/dependency-review-action`; ranges like `.py/.json`\n')}
    cn, dn = scan(tmp, noise)
    cases.append(('prose slashes (before/after, --a/--b, actions/checkout) are not path claims',
                  not dn and all(cn[k] == 0 for k in ('resolves', 'archive-exempt',
                                                      'upstream-attributed', 'dead')),
                  'collected=%s' % {k: cn[k] for k in
                                     ('resolves', 'archive-exempt', 'upstream-attributed', 'dead')}))
    cases.append(('an empty population is refused, not passed',
                  bool(issues(dict.fromkeys(('resolves', 'archive-exempt',
                                             'upstream-attributed', 'dead', 'documents'), 0),
                              [], True)), 'empty docs -> red'))
    cases.append(('an unprovable archive exemption is refused',
                  bool(issues(dict.fromkeys(('resolves', 'archive-exempt',
                                              'upstream-attributed', 'dead'), 1) | {'documents': 3},
                              [], None)), 'None from git -> red'))
    up = {'E.md': 'see `../_internal/audit_dupes.py`\n'}
    ce, de = scan(tmp, up)
    cases.append(('an escaped archive path is exempt WITHOUT reading outside the repository',
                  not de and ce['archive-exempt'] == 1, 'dead=%s counts=%s' % (de, dict(ce))))
    esc, ed = scan(tmp, {'F.md': 'escape hatch `../../Windows/win.ini` and `../outside/thing.py`\n'})
    cases.append(('an escaped path that is NOT archive-side stays a dead claim (no blanket ..豁免)',
                  len(ed) == 2 and esc['archive-exempt'] == 0, str(ed)))
    real_counts, real_dead = scan()
    cases.append(('the shipped documents have no dead path claim today', not real_dead,
                  'dead=%s' % (real_dead[:3],)))
    cases.append(('the real archive really contains no _internal/ file (exemption earned)',
                  archive_has_no_internal() is True, str(archive_has_no_internal())))
    # the discriminator for the byte-grep bug: the documents DO mention `_internal/`, and the
    # archive still contains no such member. If a future edit makes these two readings agree,
    # the proof has quietly become "does the string appear anywhere".
    mentions = any('_internal/' in io.open(p, encoding='utf-8').read() for p in documents())
    cases.append(('documents mention `_internal/` while the archive ships none (names, not bytes)',
                  mentions and archive_has_no_internal() is True,
                  'docs_mention=%s archive_clean=%s' % (mentions, archive_has_no_internal())))
    cases.append(('the extractor sees the classes it claims to (nothing classified is a broken probe)',
                  all(real_counts[k] > 0 for k in ('resolves', 'archive-exempt')),
                  ' '.join('%s=%d' % (k, real_counts[k]) for k in
                           ('resolves', 'archive-exempt', 'upstream-attributed', 'dead'))))
    bad = sum(1 for _n, ok, _d in cases if not ok)
    for name, ok, detail in cases:
        print('  %s %s (%s)' % ('ok ' if ok else 'SELFTEST-FAIL', name, str(detail)[:110]))
    print('doc_citations selftest: %d cases, %d failures' % (len(cases), bad))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.check:
        counts, dead = scan()
        bad = issues(counts, dead, archive_has_no_internal())
        print('%s: docs=%d resolves=%d exempt=%d dead=%d'
              % ('CITATIONS-OK' if not bad else 'CITATIONS-FAIL', counts['documents'],
                 counts['resolves'], counts['archive-exempt'] + counts['upstream-attributed'],
                 len(dead)))
        for b in bad:
            print('  ' + b[:200])
        return 1 if bad else 0
    return report()


if __name__ == '__main__':
    sys.exit(main())
