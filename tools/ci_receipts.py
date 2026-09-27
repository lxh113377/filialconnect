#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Behaviour receipts for job-level `permissions:` blocks.

A declared permission set proves only that someone wrote it down. `ci_hygiene` judges the shape
(one block, no wildcards, narrower than the workflow header); this tool answers the other half -
**did a job actually run green with exactly that set, and is the set still the one on disk?**
Without that, `permissions:` is configuration without behaviour, which is the shape that gave this
project a false advantage against peers before (a dependabot config nobody acted on).

The ledger lives in this repository on purpose: the public judge reads it in CI, and the private
archive side is invisible to `git archive HEAD` - a check that reads an absent file passes forever.

    python tools/ci_receipts.py --collect     # asks gh for the newest run at HEAD (network)
    python tools/ci_receipts.py --check       # pure-local: judge mode, no network
    python tools/ci_receipts.py --selftest
"""
import argparse
import datetime
import io
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
LEDGER = os.path.join('reports', 'ci-job-receipts.json')
GENERATOR = 'python tools/ci_receipts.py --collect'


def run(cmd, cwd=ROOT):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=300)


def head_sha():
    p = run(['git', 'rev-parse', 'HEAD'])
    return p.stdout.strip() if p.returncode == 0 else ''


def is_ancestor(sha):
    """True when `sha` is reachable from HEAD - a receipt must describe commits in this history."""
    if not sha or len(sha) < 7:
        return False
    return run(['git', 'merge-base', '--is-ancestor', sha, 'HEAD']).returncode == 0


def declared_blocks(hyg):
    """{workflow: {job: {scope: level}}} - attribution comes from ci_hygiene's single parser."""
    out = {}
    for name in sorted(os.listdir(os.path.join(ROOT, '.github', 'workflows'))):
        if not name.endswith(('.yml', '.yaml')):
            continue
        text = io.open(os.path.join(ROOT, '.github', 'workflows', name),
                       encoding='utf-8', errors='replace').read()
        blocks = hyg.named_job_blocks(text)
        if blocks:
            out[name] = blocks
    return out


def collect():
    """One receipt per declared job block, taken from the newest run of that workflow at HEAD."""
    import ci_hygiene as hyg
    blocks = declared_blocks(hyg)
    entries = []
    for wf, jobs in sorted(blocks.items()):
        p = run(['gh', 'run', 'list', '--workflow', wf, '--limit', '1',
                 '--json', 'databaseId,headSha,conclusion,status'])
        if p.returncode != 0:
            raise SystemExit('FAIL: gh cannot list runs for %s: %s' % (wf, p.stderr.strip()[:120]))
        runs = json.loads(p.stdout or '[]')
        if not runs:
            raise SystemExit('FAIL: no run found for %s - a receipt must not be typed by hand' % wf)
        r = runs[0]
        if r.get('status') != 'completed':
            raise SystemExit('FAIL: newest run for %s is still %s - take the receipt from a '
                             'finished run, not from one you hope will pass'
                             % (wf, r.get('status')))
        jp = run(['gh', 'run', 'view', str(r['databaseId']), '--json', 'jobs'])
        jobs_info = {j['name']: j['conclusion'] for j in json.loads(jp.stdout or '{}').get('jobs', [])}
        for job, scopes in sorted(jobs.items()):
            entries.append({'workflow': wf, 'job': job, 'declared': scopes,
                            'run_id': r['databaseId'], 'sha': r['headSha'],
                            'run_conclusion': r['conclusion'],
                            'job_conclusion': jobs_info.get(job, 'not-in-run'),
                            'captured_utc': datetime.datetime.now(
                                datetime.timezone.utc).isoformat()})
    text = json.dumps({'generated_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       'generator': GENERATOR,
                       'ruler': 'newest completed run of each workflow that carries a job-level '
                                'permissions block; per-job conclusion read from the run itself',
                       'note': 'A receipt is evidence that the declared set was sufficient AND was '
                               'used: it names the commit, the run, and the exact scopes at capture '
                               'time. `--check` re-reads the blocks and fails if either moved.',
                       'receipts': entries}, indent=2, sort_keys=True) + '\n'
    io.open(os.path.join(ROOT, LEDGER), 'w', encoding='utf-8', newline='\n').write(text)
    print('wrote %s: %d receipt(s)' % (LEDGER, len(entries)))
    return 0


def receipt_issues(blocks, ledger, ancestor=lambda sha: True):
    """Pure predicate: (declared blocks on disk, the committed ledger) -> list of problems.

    `ancestor` is injected so the check can be driven without a git repository under test -
    a judge that cannot be fed a hostile input has no proven failure side.
    """
    bad = []
    got = {(r.get('workflow'), r.get('job')): r for r in (ledger or {}).get('receipts', [])}
    want = set()
    for wf, jobs in sorted(blocks.items()):
        for job in sorted(jobs):
            want.add((wf, job))
    for key in sorted(want - set(got)):
        bad.append('job %s/%s declares permissions but has no behaviour receipt' % key)
    for key in sorted(set(got) - want):
        # an orphan receipt is the quiet half of the same defect: the block it proved is gone, so
        # the ledger now certifies a permission nobody asks for anymore
        bad.append('receipt for %s/%s names no block on disk (stale exemption)' % key)
    for key in sorted(want & set(got)):
        r, scopes = got[key], blocks[key[0]][key[1]]
        if r.get('declared') != scopes:
            bad.append('%s/%s scopes changed since the receipt: ledger %s vs disk %s'
                       % (key[0], key[1], r.get('declared'), scopes))
        if r.get('job_conclusion') != 'success':
            bad.append('%s/%s job conclusion is %r, not success'
                       % (key[0], key[1], r.get('job_conclusion')))
        elif not ancestor(r.get('sha') or ''):
            bad.append('%s/%s receipt names commit %s which is not in this history'
                       % (key[0], key[1], (r.get('sha') or '?')[:9]))
    return bad


def check():
    import ci_hygiene as hyg
    path = os.path.join(ROOT, LEDGER)
    if not os.path.exists(path):
        return False, 'LEDGER-MISSING: %s (run: %s)' % (LEDGER, GENERATOR)
    ledger = json.load(io.open(path, encoding='utf-8'))
    blocks = declared_blocks(hyg)
    if not any(blocks.values()):
        return False, ('UNVERIFIED: no job-level permissions block on disk - a receipt ledger with '
                       'nothing to certify is not a pass (R247)')
    bad = receipt_issues(blocks, ledger, ancestor=is_ancestor)
    n = sum(len(v) for v in blocks.values())
    if bad:
        return False, 'RECEIPT-FAIL: %d problem(s): %s' % (len(bad), '; '.join(bad)[:220])
    return True, ('CI-RECEIPTS-OK: %d job block(s) covered, %d receipt(s), newest run=%s sha=%s'
                  % (n, len(ledger['receipts']),
                     max(r['run_id'] for r in ledger['receipts']),
                     (ledger['receipts'][0]['sha'] or '')[:9]))


def selftest():
    import ci_hygiene as hyg
    blocks = {'a.yml': {'deploy': {'contents': 'read'}}}
    ok_ledger = {'receipts': [{'workflow': 'a.yml', 'job': 'deploy',
                               'declared': {'contents': 'read'}, 'run_id': 1,
                               'sha': 'a' * 40, 'job_conclusion': 'success'}]}
    cases = []
    cases.append(('a matching receipt passes', not receipt_issues(blocks, ok_ledger),
                  str(receipt_issues(blocks, ok_ledger))[:70]))
    cases.append(('no receipt at all is named', any('no behaviour receipt' in x for x in
                  receipt_issues(blocks, {'receipts': []})), 'red'))
    cases.append(('widening the block after capture is caught',
                  any('scopes changed' in x for x in receipt_issues(
                      {'a.yml': {'deploy': {'contents': 'write'}}}, ok_ledger)), 'red'))
    cases.append(('a failed job cannot certify a permission',
                  any('not success' in x for x in receipt_issues(
                      blocks, {'receipts': [dict(ok_ledger['receipts'][0],
                                                 job_conclusion='failure')]})), 'red'))
    cases.append(('a receipt pointing outside this history is refused',
                  any('not in this history' in x for x in receipt_issues(
                      blocks, ok_ledger, ancestor=lambda s: False)), 'red'))
    cases.append(('an orphan receipt (block deleted) does not stay green',
                  any('stale exemption' in x for x in receipt_issues(
                      {'a.yml': {}}, ok_ledger)), 'red'))
    cases.append(('the failure branch is not vacuous: an empty everything reports nothing',
                  receipt_issues({}, {'receipts': []}) == [], 'ok-but-check-the-guard-in-check()'))
    real_blocks = declared_blocks(hyg)
    real_n = sum(len(v) for v in real_blocks.values())
    cases.append(('the real tree does carry a job-level block (else this judge is decorative)',
                  real_n >= 1, '%d block(s) across %d workflow(s)' % (real_n, len(real_blocks)))
                 )
    ok, line = check()
    cases.append(('the committed ledger passes against the real tree and real git history',
                  ok, line[:110]))
    bad = sum(1 for _n, o, _d in cases if not o)
    for name, ok_c, detail in cases:
        print('  %s %s (%s)' % ('ok ' if ok_c else 'SELFTEST-FAIL', name, detail))
    print('ci_receipts selftest: %d cases, %d failures' % (len(cases), bad))
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--collect', action='store_true')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.collect:
        return collect()
    if a.check:
        ok, line = check()
        print(line)
        return 0 if ok else 1
    ap.print_help()
    return 2


if __name__ == '__main__':
    sys.exit(main())
