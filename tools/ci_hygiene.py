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
JOB_PERMISSIONS = re.compile(r'^([ \t]+)permissions:[ \t]*\n'
                             r'((?:\1 [ \t]*\w[\w-]*:[ \t]*\S+[ \t]*\n?)+)', re.M)
JOB_KEY = re.compile(r'^  ([A-Za-z_][\w-]*):[ \t]*$', re.M)


def job_blocks(text):
    """The job-level `permissions:` bodies, each anchored on its own header indent.

    A fixed four-space pattern swallowed the following `runs-on:` line (round 43 saw a phantom
    `runs-on` permission), because the block was defined by indentation depth in the abstract rather
    than by *deeper than this header*. Anchoring on the header's indent keeps the block to children.
    """
    return [m[1] for m in JOB_PERMISSIONS.findall(text)]


def named_job_blocks(text):
    """{job name: {scope: level}} for job-level permission blocks - the same parse, attributed.

    `ci_receipts.py` needs to say *which* job a receipt belongs to, and a second parser there would
    be a copy that can drift (round 42's rule: one judgement, one implementation). So attribution
    lives here: a block belongs to the nearest preceding two-space key that sits under `jobs:`.
    """
    out = {}
    jobs_span = text.find('\njobs:')
    if jobs_span < 0:
        return out
    keys = [(m.start(), m.group(1)) for m in JOB_KEY.finditer(text) if m.start() > jobs_span]
    for m in JOB_PERMISSIONS.finditer(text):
        if m.start() < jobs_span:
            continue                    # the workflow header's own block is not a job's
        owner = [name for pos, name in keys if pos < m.start()]
        if not owner:
            continue
        scopes = scope_map(m.group(2))
        if scopes:
            out[owner[-1]] = scopes
    return out
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


#: every way this tool can find a problem, named so a leg with no sample can be declared
#: untested instead of passing (round 43). The tree today contains zero job-level `permissions:`
#: blocks, so `job_within_header` has nothing to bite on - a green that says "verified" there is
#: a green that measured nothing.
LEGS = ('pull_request_target', 'wildcard_scope', 'permissions_block', 'job_within_header')


#: GitHub's own permission keys. Anything else inside a `permissions:` block is a typo
#: (`contets: write` grants nothing and reads fine in review), and the token silently falls back
#: to the workflow default - so an unknown key is a finding, not noise to be skipped. Round 43
#: found this while chasing a false positive: the block-scan had been reading `runs-on:` as a scope.
KNOWN_SCOPES = ('actions', 'attestations', 'checks', 'contents', 'deployments', 'discussions',
                'id-token', 'issues', 'pages', 'packages', 'pull-requests',
                'repository-projects', 'security-events', 'statuses')
KNOWN_LEVELS = ('read', 'write', 'none')


def unknown_scopes(block):
    """Keys or levels in a permissions block that GitHub does not know."""
    bad = []
    for scope, level in scope_map(block).items():
        if scope not in KNOWN_SCOPES:
            bad.append('%s (unknown permission key)' % scope)
        elif level not in KNOWN_LEVELS:
            bad.append('%s:%s (unknown level)' % (scope, level))
    return bad


def leg_samples(texts):
    """How many inputs each leg could actually judge in this population.

    `job_within_header` counts job-level blocks (a widening can only be seen where one exists);
    the other three legs see every workflow file. Zero samples is reported, never inferred as clean.
    """
    jobs = 0
    for text in texts:
        if text:
            jobs += len(job_blocks(text))
    seen = [t for t in texts if t]
    return {'pull_request_target': len(seen), 'wildcard_scope': len(seen),
            'permissions_block': len(seen), 'job_within_header': jobs}


def workflow_findings(text, name='(inline)'):
    """The same verdicts as `workflow_issues`, tagged with the leg that produced each one."""
    found = []
    if PR_TARGET.search(text):
        found.append(('pull_request_target',
                      '%s: uses pull_request_target (runs the base workflow with write access '
                      'against untrusted code)' % name))
    if WILDCARD.search(text):
        found.append(('wildcard_scope', '%s: grants a wildcard scope or write-all' % name))
    tops = TOP_PERMISSIONS.findall(text)
    if not re.search(r'^permissions:', text, re.M):
        found.append(('permissions_block',
                      '%s: no top-level permissions block (inherits the org/repo default, which '
                      'this file cannot prove)' % name))
        return found
    if len(tops) == 0:
        found.append(('permissions_block',
                      '%s: permissions block parsed empty - the shape is not the one this scan '
                      'reads (so nothing here would be judged)' % name))
        return found
    if len(tops) != 1:
        found.append(('permissions_block',
                      '%s: %d top-level permissions blocks, expected exactly 1' % (name, len(tops))))
        return found
    granted = scope_map(tops[0])
    for bad in unknown_scopes(tops[0]):
        found.append(('permissions_block', '%s: top-level permissions has %s' % (name, bad)))
    for job_block in job_blocks(text):
        for bad in unknown_scopes(job_block):
            found.append(('job_within_header', '%s: job-level permissions has %s' % (name, bad)))
        for scope, level in scope_map(job_block).items():
            if scope not in KNOWN_SCOPES:
                continue                                  # already reported above, not as a widening
            if _rank(level) > _rank(granted.get(scope, 'none')):
                found.append(('job_within_header',
                              '%s: job grants %s:%s but the workflow declares %s'
                              % (name, scope, level, granted.get(scope, '(nothing)'))))
    return found


def workflow_issues(text, name='(inline)'):
    """Pure predicate: every way a workflow's declared permissions can be wrong.

    A workflow with no `permissions:` block is a finding, not a pass: GitHub then hands out the
    repository default, which is a setting no file in this tree can show.
    """
    return [msg for _leg, msg in workflow_findings(text, name)]


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
        return None, base          # the judge reads `rep is None` and reports the path it could not see
    findings, unreadable, legs, readable = [], [], {}, []
    for leg in LEGS:
        legs[leg] = 0
    for name, text in items:
        if text is None:
            unreadable.append(name)
            continue
        readable.append(text)
        for leg, msg in workflow_findings(text, name):
            findings.append(msg)
            legs[leg] += 1
    samples = leg_samples(readable)
    return {'workflows': len(items), 'names': [n for n, _ in items],
            'unreadable': unreadable, 'findings': findings,
            'leg_findings': legs, 'leg_samples': samples,
            'untested_legs': [l for l in LEGS if samples[l] == 0]}, base


def coverage_identity_issues(rep):
    """The rules that make "untested" a claim instead of decoration.

    A leg may be declared untested only when it truly had no sample; a finding may not come from a
    leg with no sample; and the declared set must equal the computed one. Without this, a report can
    say `untested=job_within_header` forever - which reads honest and proves nothing.
    """
    bad = []
    for leg in LEGS:
        if leg not in rep.get('leg_samples', {}) or leg not in rep.get('leg_findings', {}):
            bad.append('leg %s missing from the report' % leg)
    declared = sorted(l for l in LEGS if not rep.get('leg_samples', {}).get(l))
    if declared != sorted(rep.get('untested_legs', [])):
        bad.append('declared untested %s != zero-sample legs %s'
                   % (sorted(rep.get('untested_legs', [])), declared))
    for leg, hits in (rep.get('leg_findings') or {}).items():
        if hits and not (rep.get('leg_samples') or {}).get(leg):
            bad.append('leg %s reported %d findings with 0 samples' % (leg, hits))
    return bad


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
    add('an unreadable file is named in the report and never counted clean',
        rep3['unreadable'] == ['wf_broken.yml'] and len(rep3['findings']) == 1
        and rep3['workflows'] == 5, str(rep3))
    # round 43: a leg may only be called untested when an **independent** count agrees it has no
    # sample. Round 42 declared this very leg empty from a hand-run grep that looked only for two
    # spaces of indentation, and `deploy-pages.yml:59` has four - a false zero that went straight
    # into next round's plan. The sample numbers below are therefore cross-checked, not asserted.
    real_rep, _ = scan()
    indep = {}
    for n, txt in workflows(os.path.join(ROOT, WF_DIR))[0]:
        if not txt:
            continue
        for leg in LEGS:
            indep[leg] = indep.get(leg, 0) + (
                1 if leg != 'job_within_header'
                else sum(1 for ln in txt.splitlines()
                         if ln.startswith('    ') and ln.strip().startswith('permissions:')))
    add('per-leg samples match an independent count, so no leg is called untested off a typed grep',
        all(real_rep['leg_samples'][k] == indep[k] for k in LEGS)
        and real_rep['leg_samples']['job_within_header'] >= 1
        and not coverage_identity_issues(real_rep),
        'report=%s independent=%s' % (real_rep['leg_samples'], indep))
    add('the leg that round 42 called empty actually has a sample today (false zero corrected)',
        'job_within_header' not in real_rep['untested_legs']
        and real_rep['leg_findings'].get('job_within_header', 0) == 0,
        'untested=%s findings=%s' % (real_rep['untested_legs'], real_rep['leg_findings']))
    empty_dir = os.path.join(tmp, 'nojob')
    os.makedirs(empty_dir)
    for i in range(2):
        io.open(os.path.join(empty_dir, 'w%d.yml' % i), 'w', encoding='utf-8', newline='\n').write(good)
    e0, _ = scan(empty_dir)
    widen_dir = os.path.join(tmp, 'withjob')
    os.makedirs(widen_dir)
    io.open(os.path.join(widen_dir, 'a.yml'), 'w', encoding='utf-8', newline='\n').write(good)
    io.open(os.path.join(widen_dir, 'b.yml'), 'w', encoding='utf-8', newline='\n').write(
        good + 'jobs:\n  x:\n    permissions:\n      contents: write\n')
    jw, _ = scan(widen_dir)
    add('a population with no job-level block declares that leg untested, and one block ends it',
        e0['untested_legs'] == ['job_within_header'] and e0['findings'] == []
        and 'job_within_header' not in jw['untested_legs']
        and jw['leg_samples']['job_within_header'] == 1
        and any('contents:write' in f for f in jw['findings']),
        'empty=%s withjob=%s' % (e0['leg_samples'], jw['leg_samples']))
    liar = dict(real_rep, untested_legs=['job_within_header', 'wildcard_scope'])
    add('declaring a leg untested while it had samples is caught (the label can lie)',
        any('declared untested' in x for x in coverage_identity_issues(liar)),
        str(coverage_identity_issues(liar))[:120])
    missing = dict(real_rep)
    missing['leg_samples'] = dict(missing['leg_samples'])
    missing['leg_samples'].pop('wildcard_scope')
    add('a leg that vanishes from the report fails the identity (coverage cannot shrink quietly)',
        any('missing from the report' in x for x in coverage_identity_issues(missing)),
        str(coverage_identity_issues(missing))[:120])

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
        print('CI-HYG: %d workflows, %d findings, unreadable=%s, leg_samples=%s, untested=%s'
              % (rep['workflows'], len(rep['findings']), rep['unreadable'],
                 ','.join('%s=%d' % (k, rep['leg_samples'][k]) for k in LEGS),
                 ','.join(rep['untested_legs']) or '-'))
        for f in rep['findings'][:8]:
            print('  - %s' % f[:150])
        for x in coverage_identity_issues(rep)[:4]:
            print('  ! %s' % x[:150])
    return 0 if not rep['findings'] and not coverage_identity_issues(rep) else 1


if __name__ == '__main__':
    sys.exit(main())
