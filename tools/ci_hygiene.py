# -*- coding: utf-8 -*-
"""CI hygiene: every workflow declares least-privilege permissions, and the scan proves its reach.

Round 42 measured the population before writing the rule: all four workflows already carry a
top-level `permissions:` block and every `uses:` line is pinned with a `#vX.Y.Z` annotation
(`t_workflows` has judged the pinning since round 12). What nothing judged was the *scope* - a job
that later adds `permissions: contents: write` under a workflow that declared only `read` widens
the token without touching the workflow header, and `permissions: write-all` reads like a
boilerplate line in review. That is the same failure class as "规则存在但没装机器闸".

The predicates are pure functions over workflow text, so the self-test can drive both directions
with in-memory samples: nothing here rewrites a shipped workflow to prove it can fail.

Usage:
    python tools/ci_hygiene.py                # print findings for the real tree
    python tools/ci_hygiene.py --selftest     # both directions + the reach claim
Exit: 0 clean | 1 a workflow is over-privileged or undeclared | 2 the population could not be read
"""
import argparse
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF_DIR = '.github/workflows'
# `*` and `write-all` grant everything; a scheduled job that only pushes a commit still gets a
# token that can delete the repository.
WILDCARD = re.compile(r'^\s*(?:-\s+)?["\x27]?\*["\x27]?\s*(?:[\s:,]|$)|permissions:\s*write-all\s*$',
                      re.M)
TOP_PERMISSIONS = re.compile(r'^permissions:[ \t]*\n((?:[ \t]+\w[\w-]*:[ \t]*\S+\n?)+)', re.M)
JOB_PERMISSIONS = re.compile(r'^ {2,}permissions:[ \t]*\n((?: {4,}\w[\w-]*:[ \t]*\S+\n?)+)', re.M)
PR_TARGET = re.compile(r'pull_request_target')


def scope_map(block):
    """`contents: read` lines -> {scope: level}. Unordered, last wins, comments dropped."""
    out = {}
    for line in block.splitlines():
        m = re.match(r'\s*([A-Za-z][\w-]*)\s*:\s*([^\s#]+)', line)
        if m:
            out[m.group(1).lower()] = m.group(2).strip().strip('"\'').lower()
    return out


def _rank(level):
    return {'none': 0, 'read': 1, 'write': 2, 'admin': 3}.get(level, 2)   # unknown = treat as wide


def workflow_issues(text, name='(inline)'):
    """Pure predicate: every way a workflow's declared permissions can be wrong.

    A workflow with no `permissions:` block is a finding, not a pass: GitHub then hands out the
    repository default, which is a setting no file in this tree can show.
    """
    issues = []
    if PR_TARGET.search(text):
        issues.append('%s: uses pull_request_target (runs the base workflow with write access '
                      'against untrusted code)' % name)
    if WILDCARD.search(text):
        issues.append('%s: grants a wildcard scope or write-all' % name)
    tops = TOP_PERMISSIONS.findall(text)
    if not re.search(r'^permissions:', text, re.M):
        issues.append('%s: no top-level permissions block (inherits the org/repo default, which '
                      'this file cannot prove)' % name)
        return issues
    if len(tops) == 0:
        issues.append('%s: permissions block parsed empty - the shape is not the one this scan '
                      'reads (so nothing here would be judged)' % name)
        return issues
    if len(tops) != 1:
        issues.append('%s: %d top-level permissions blocks, expected exactly 1' % (name, len(tops)))
        return issues
    granted = scope_map(tops[0])
    for job_block in JOB_PERMISSIONS.findall(text):
        for scope, level in scope_map(job_block).items():
            if _rank(level) > _rank(granted.get(scope, 'none')):
                issues.append('%s: job grants %s:%s but the workflow declares %s'
                              % (name, scope, level, granted.get(scope, '(nothing)')))
    return issues


def workflows(dirpath=None):
    """The population, enumerated - never a hand-typed list, so adding a workflow cannot hide."""
    base = dirpath or os.path.join(ROOT, WF_DIR)
    if not os.path.isdir(base):
        return None, base
    names = sorted(f for f in os.listdir(base) if f.endswith(('.yml', '.yaml')))
    out = []
    for n in names:
        try:
            out.append((n, io.open(os.path.join(base, n), encoding='utf-8').read()))
        except (IOError, UnicodeDecodeError):
            out.append((n, None))
    return out, base


def scan(dirpath=None):
    items, base = workflows(dirpath)
    if items is None:
        return None, [], 'workflow directory not found: %s' % base
    findings, unreadable = [], []
    for name, text in items:
        if text is None:
            unreadable.append(name)
            continue
        findings.extend(workflow_issues(text, name))
    return {'workflows': len(items), 'names': [n for n, _ in items],
            'unreadable': unreadable, 'findings': findings}, base


def selftest():
    cases = []

    def add(label, ok, detail):
        cases.append((label, bool(ok), str(detail)[:120]))

    good = ('permissions:\n  contents: read\n  pages: write\njobs:\n  build:\n'
            '    runs-on: ubuntu-latest\n')
    add('a declared least-privilege workflow passes', workflow_issues(good) == [], workflow_issues(good))
    none_declared = ('on: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n')
    got = workflow_issues(none_declared, 'x.yml')
    add('a workflow with no permissions block is a finding, not a pass',
        len(got) == 1 and 'no top-level permissions' in got[0], got)
    widen = (good + 'jobs:\n  deploy:\n    permissions:\n      contents: write\n')
    got2 = workflow_issues(widen, 'y.yml')
    add('a job widening beyond the workflow header is caught',
        len(got2) == 1 and 'contents:write' in got2[0].replace(' ', ''), got2)
    add('a job that only narrows is accepted (read under write is fine)',
        workflow_issues('permissions:\n  contents: write\njobs:\n  a:\n    permissions:\n'
                        '      contents: read\n') == [], 'narrowing ok')
    add('write-all is caught',
        any('wildcard' in x for x in workflow_issues('permissions: write-all\njobs:\n  a:\n')),
        'write-all')
    add('a wildcard scope is caught',
        any('wildcard' in x for x in workflow_issues(
            'permissions:\n  contents: read\njobs:\n  a:\n    permissions:\n      "*": write\n')),
        'star')
    add('pull_request_target is named',
        any('pull_request_target' in x for x in workflow_issues(
            'on:\n  pull_request_target:\npermissions:\n  contents: read\n')), 'pr target')
    add('an empty permissions block is refused rather than silently passing',
        any('parsed empty' in x for x in workflow_issues(
            'permissions:\njobs:\n  a:\n    runs-on: x\n')), 'empty block')
    add('a duplicate top-level block is caught (last-wins would hide the first)',
        len(workflow_issues(good + good)) == 1 and 'expected exactly 1' in
        workflow_issues(good + good)[0], workflow_issues(good + good))
    # the reach claim: the population is enumerated, so an added workflow file is seen.
    import tempfile
    tmp = tempfile.mkdtemp(prefix='cihyg_')
    os.makedirs(os.path.join(tmp, 'sub'))
    for i in range(3):
        io.open(os.path.join(tmp, 'wf%d.yml' % i), 'w', encoding='utf-8').write(good)
    rep, _ = scan(tmp)
    add('the scan counts the directory, not a hard-coded number', rep['workflows'] == 3, str(rep))
    io.open(os.path.join(tmp, 'wf_bad.yml'), 'w', encoding='utf-8').write(none_declared)
    rep2, _ = scan(tmp)
    add('adding an undeclared workflow changes the finding count (reach, not luck)',
        rep2['workflows'] == 4 and len(rep2['findings']) == 1, str(rep2['findings']))
    real, base = scan()
    add('the real tree passes today (and the scan proves it saw all four workflows)',
        real and real['findings'] == [] and real['workflows'] >= 4,
        'workflows=%s findings=%s' % (real and real['workflows'], real and real['findings'][:1]))
    io.open(os.path.join(tmp, 'wf_broken.yml'), 'wb').write(b'\xff\xfe not utf-8 \x81')
    rep3, _ = scan(tmp)
    add('an unreadable file is named in the report and never counted as clean',
        rep3['unreadable'] == ['wf_broken.yml'] and len(rep3['findings']) == 1
        and rep3['workflows'] == 5, str(rep3))

    bad = sum(1 for _n, ok, _d in cases if not ok)
    for name, ok, detail in cases:
        print('  %s %s (%s)' % ('ok ' if ok else 'SELFTEST-FAIL', name, detail))
    print('ci_hygiene selftest: %d cases, %d failures' % (len(cases), bad))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--json', dest='as_json', action='store_true')
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    rep, base = scan()
    if rep is None:
        print('UNVERIFIED: %s' % base)
        return 2
    if args.as_json:
        print(json.dumps(rep, ensure_ascii=False))
    else:
        print('CI-HYG: %d workflows, %d findings, unreadable=%s'
              % (rep['workflows'], len(rep['findings']), rep['unreadable']))
        for f in rep['findings'][:8]:
            print('  - %s' % f[:150])
    return 0 if not rep['findings'] else 1


if __name__ == '__main__':
    sys.exit(main())
