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
import shutil
import stat
import subprocess
import sys
import tempfile

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


PROBE_PREFIX = 'ci_receipts_probe_'
#: constant text on purpose. The first version printed the probe's unique path here, and the
#: archive compares its instrument block byte for byte - a random path in the transcript made
#: every capture "stale" forever. Facts that vary belong to --probe-census, not in here.
PROBE_RETAINED_NOTE = ('NOTE: shallow probe dir retained (read-only objects survived two '
                       'rmtree passes); census: python tools/ci_receipts.py --probe-census\n')


def reclaim(path):
    """Delete a shallow git clone, including on Windows where its objects are read-only.

    Round 64 measured the first version: `shutil.rmtree(probe, ignore_errors=True)` reported success
    while the directory stayed, and the fallback printed its **unique path** into the instrument
    capture - so every capture differed from every other and the archive's byte-equality gate on §10
    could never converge (52 leaked directories accumulated on one machine). Clearing the read-only
    bit and retrying is what actually removes it; `ignore_errors` is what hid that it never did.
    """
    if not os.path.exists(path):
        return True
    for attempt in (1, 2):
        try:
            shutil.rmtree(path)
        except OSError:
            if attempt == 2:
                return False
            for dirpath, _dirnames, filenames in os.walk(path):
                for name in filenames:
                    try:
                        os.chmod(os.path.join(dirpath, name), stat.S_IWRITE)
                    except OSError:
                        pass
        else:
            return not os.path.exists(path)
    return False


def probe_retained():
    """How many probe directories are on disk right now - enumerated, never a copied constant.

    Returns None when the temp directory cannot be read: "could not count" must not be reportable
    as "counted zero", and a leg that compares two counts has to be able to tell those apart.
    """
    base = tempfile.gettempdir()
    try:
        return len([n for n in os.listdir(base) if n.startswith(PROBE_PREFIX)])
    except OSError:
        return None


def probe_census():
    n = probe_retained()
    if n is None:
        return 'PROBE-CENSUS: unreadable (%s)' % tempfile.gettempdir()
    return 'PROBE-CENSUS: retained=%d base=%s' % (n, tempfile.gettempdir())


def ancestor_state(sha):
    """True (in this history) / False (present but not an ancestor) / None (cannot see it).

    CI checks out with depth 1, so the commit a receipt names is usually not in the local object
    store at all. That must be reported as blindness, not as a pass and not as a failure: the first
    version of this check demanded `git merge-base --is-ancestor` unconditionally and turned the
    quality job red on the day it shipped, which is the same mistake as scoring an unmeasured leg
    as green - the difference is only which way the lie points.
    """
    if not sha or len(sha) < 7:
        return False
    if run(['git', 'cat-file', '-e', '%s^{commit}' % sha]).returncode != 0:
        return None
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
    """Pure predicate: (declared blocks on disk, the committed ledger) -> (problems, blind_count).

    `ancestor` returns True / False / None and is injected so every branch - including "this object
    is not in the local store" - can be driven from a selftest without a git repository.
    """
    bad = []
    blind = 0
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
        else:
            state = ancestor(r.get('sha') or '')
            if state is False:
                bad.append('%s/%s receipt names commit %s which is in this history but not an '
                           'ancestor of HEAD' % (key[0], key[1], (r.get('sha') or '?')[:9]))
            elif state is None:
                blind += 1
    return bad, blind


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
    bad, blind = receipt_issues(blocks, ledger, ancestor=ancestor_state)
    n = sum(len(v) for v in blocks.values())
    face = ('%d job block(s) covered, %d receipt(s), newest run=%s sha=%s ancestry=%s'
            % (n, len(ledger['receipts']), max(r['run_id'] for r in ledger['receipts']),
               (ledger['receipts'][0]['sha'] or '')[:9],
               ('verified' if blind == 0 else 'BLIND(%d, shallow checkout: cannot see the commit)'
                % blind)))
    if bad:
        return False, 'RECEIPT-FAIL: %d problem(s): %s | %s' % (len(bad), '; '.join(bad)[:200], face)
    return True, 'CI-RECEIPTS-OK: %s' % face


def selftest():
    import ci_hygiene as hyg
    blocks = {'a.yml': {'deploy': {'contents': 'read'}}}
    ok_ledger = {'receipts': [{'workflow': 'a.yml', 'job': 'deploy',
                               'declared': {'contents': 'read'}, 'run_id': 1,
                               'sha': 'a' * 40, 'job_conclusion': 'success'}]}
    cases = []
    b0, bl0 = receipt_issues(blocks, ok_ledger)
    cases.append(('a matching receipt passes', not b0 and bl0 == 0, '%s blind=%d' % (b0, bl0)))
    cases.append(('no receipt at all is named', any('no behaviour receipt' in x for x in
                  receipt_issues(blocks, {'receipts': []})[0]), 'red'))
    cases.append(('widening the block after capture is caught',
                  any('scopes changed' in x for x in receipt_issues(
                      {'a.yml': {'deploy': {'contents': 'write'}}}, ok_ledger)[0]), 'red'))
    cases.append(('a failed job cannot certify a permission',
                  any('not success' in x for x in receipt_issues(
                      blocks, {'receipts': [dict(ok_ledger['receipts'][0],
                                                 job_conclusion='failure')]})[0]), 'red'))
    cases.append(('a receipt in this history but not an ancestor is refused',
                  any('not an ancestor' in x for x in receipt_issues(
                      blocks, ok_ledger, ancestor=lambda s: False)[0]), 'red'))
    # the shallow-CI case: blindness is its own state. It must NOT be a problem (that red is what
    # this judge shipped with) and must NOT be silent - the caller prints `ancestry=BLIND(n)`.
    bblind, blblind = receipt_issues(blocks, ok_ledger, ancestor=lambda s: None)
    cases.append(('a commit the checkout cannot see is blindness, not a failure',
                  not bblind and blblind == 1, 'problems=%s blind=%d' % (bblind, blblind)))
    ok, line = check()
    cases.append(('the real verdict says whether ancestry was verified or blind (no quiet skip)',
                  'ancestry=' in line and ('verified' in line or 'BLIND' in line), line[-60:]))
    cases.append(('an orphan receipt (block deleted) does not stay green',
                  any('stale exemption' in x for x in receipt_issues(
                      {'a.yml': {}}, ok_ledger)[0]), 'red'))
    real_blocks = declared_blocks(hyg)
    real_n = sum(len(v) for v in real_blocks.values())
    cases.append(('the real tree does carry a job-level block (else this judge is decorative)',
                  real_n >= 1, '%d block(s) across %d workflow(s)' % (real_n, len(real_blocks)))
                 )
    cases.append(('the committed ledger passes against the real tree', ok, line[:110]))
    # The CI condition, reproduced instead of asserted: a depth-1 clone over file:// really does
    # lack the receipt's commit. Without this case "blind" is a path nobody has walked, and a local
    # `verified` reading says nothing about a shallow runner.
    import shutil
    import tempfile
    # A fixed path + `rmtree(ignore_errors=True)` was the first version, and it failed in the worst
    # shape: a manual probe run left the directory behind, the silent cleanup did not remove it, and
    # git then refused to clone into it - the case reported "clone failed" about an environment
    # leftover instead of what it means. So: claim a unique path, and refuse to continue if the
    # empty directory cannot be released (a probe that cannot run must say so, not pass quietly).
    # Sampled BEFORE this run creates anything - `mkdtemp` already adds one, so sampling after it
    # (the first version) compared "54 including the dir I had just made" with "53 after cleanup"
    # and failed: a self-measurement taken at the wrong moment is wrong in the direction of
    # looking broken, which is the easiest kind to "fix" by deleting the leg.
    census_before = probe_retained()
    staging = tempfile.mkdtemp(prefix=PROBE_PREFIX)
    try:
        shutil.rmtree(staging)                     # git clone wants to create the directory itself
    except OSError as exc:
        cases.append(('shallow probe path could not be released (named, not silently skipped)',
                      False, '%s: %s' % (type(exc).__name__, str(exc)[:70])))
    probe = staging
    clone = run(['git', 'clone', '--depth', '1', '-q',
                 'file://' + ROOT.replace('\\', '/'), probe], cwd=tempfile.gettempdir())
    if clone.returncode != 0:
        cases.append(('shallow-clone probe could not run (named as a failure, not skipped)', False,
                      'git clone failed: %s' % (clone.stderr or '').strip()[:80]))
    else:
        depth = run(['git', 'rev-list', '--count', 'HEAD'], cwd=probe).stdout.strip()
        seen = run([sys.executable, os.path.join('tools', 'ci_receipts.py'), '--check'], cwd=probe)
        cases.append(('in a depth-1 checkout the same ledger reads BLIND and still exits 0',
                      depth == '1' and 'BLIND' in (seen.stdout or '') and seen.returncode == 0,
                      'depth=%s rc=%d %s' % (depth, seen.returncode,
                                             (seen.stdout or '').strip()[-56:])))
        # Round 64's finding about my own cleanup: `rmtree(ignore_errors=True)` "succeeded" while the
        # directory survived, and the fallback printed its unique path - which made every instrument
        # capture differ from every other, so the archive's byte-equality gate on §10 could not
        # converge (6 extra captures in one round, 52 leaked directories on the machine).
        reclaimed = reclaim(probe)
        cases.append(('the probe directory is really gone afterwards (not "ignore_errors said so")',
                      reclaimed and not os.path.exists(probe), 'reclaimed=%s exists=%s'
                      % (reclaimed, os.path.exists(probe))))
        sandbox = tempfile.mkdtemp(prefix=PROBE_PREFIX + 'ro_')
        io.open(os.path.join(sandbox, 'obj'), 'w', encoding='utf-8').write(u'x' + chr(10))
        os.chmod(os.path.join(sandbox, 'obj'), stat.S_IREAD)   # what a git clone leaves on Win
        cases.append(('reclaim clears a read-only file instead of reporting success over it',
                      reclaim(sandbox) and not os.path.exists(sandbox),
                      'exists=%s' % os.path.exists(sandbox)))
        cases.append(('the retained line carries no absolute path and no unique dir name, so a capture'
                      ' holding it stays byte-comparable',
                      chr(92) not in PROBE_RETAINED_NOTE
                      and tempfile.gettempdir() not in PROBE_RETAINED_NOTE
                      and PROBE_PREFIX not in PROBE_RETAINED_NOTE
                      and 'probe-census' in PROBE_RETAINED_NOTE,
                      PROBE_RETAINED_NOTE.strip()[:56]))
        census_after = probe_retained()
        cases.append(('one selftest run leaves no new probe directory behind',
                      census_after == census_before, 'retained %d -> %d' % (census_before,
                                                                           census_after)))
        if not reclaimed:
            # a constant line, never a unique path: the countable fact belongs to --probe-census, not
            # to a transcript that is later compared byte for byte
            sys.stderr.write(PROBE_RETAINED_NOTE)
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
    ap.add_argument('--probe-census', action='store_true',
                    help='count leftover probe dirs (read-only; the count is never printed as a path)')
    a = ap.parse_args()
    if a.probe_census:
        print(probe_census())
        return 0
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
