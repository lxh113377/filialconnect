#!/usr/bin/env python3
"""Poll a commit's CI verdict and print the repair instruction, not just a red exit.

Why this exists: every round re-runs the same four commands by hand after a push (push, poll
check-runs, find the failed run, read its log). Repeated manual work is what a hook should own, so
this is the piece a hook calls; wiring it into a client's hook config stays a local decision (it
changes what every session runs, which is not this file's business).

Verdict discipline inherited from `tools/release.py` (reused, not re-derived): green / red / pending
/ unknown are four different answers, and "gh returned nothing" is `unknown`, never green. A 10-minute
budget is the same reason the chain has one: a watcher that waits forever is a hang with a name.

Usage:
  python tools/ci-watch.py                       # this repo's HEAD, 600s budget
  python tools/ci-watch.py --sha <sha> --timeout 300
  python tools/ci-watch.py --once                # single poll: for hook-per-event use
  python tools/ci-watch.py --selftest            # the mapping and the signatures, offline
Exit: 0 green | 1 red (named repair hint + log tail) | 2 pending / UNVERIFIED
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build as B          # noqa: E402  (for ROOT)
import release as R        # noqa: E402  (ci_verdict + gh plumbing are already there)

# (pattern, what to do). The table is the single source for the triage list in AGENTS.md: a second
# copy of these strings in prose is the defect class this repository already calls class 6.
HINTS = (
    (r'ERR_MODULE_NOT_FOUND|Cannot find (?:package|module)',
     'run `npm ci` - dependencies are missing, this is not artifact drift; a worktree must never '
     'link node_modules from the live repo (t_no_link_code)'),
    (r'no build input is untracked|Did you mean --force|pathspec .* did not match any files',
     'a commit was made without new files: `git add <paths>` then re-check `git show --name-only`; '
     '`git add -u` skips untracked ones'),
    (r'matches this measurement',
     'a generated ledger is stale - run the generator its own message names (tools/judge_coverage.py, tools/gate_wiring.py, ...) and commit its output'),
    (r'node half reports no drift|i18n.js .* out of sync',
     'build order is python then node: `python tools/build.py && node tools/build.mjs`, '
     'then re-run `node tools/build.mjs check`'),
    (r'steps=0|Could not allocate|waiting for a runner',
     'the job never got a runner: read annotations at '
     '`gh api repos/<slug>/check-runs/<id>/annotations` - it is not a code failure'),
    (r'ABORTED JUDGES',
     'a judge crashed instead of reporting: fix that judge first - while it is aborting, the '
     'evidence of every later judge is lost'),
    (r'assertion.*404|HTTP 404',
     '`gh api` GET parameters belong in the query string; `-f` puts them in the body and turns a '
     'good path into a 404'),
    (r'verify-live|UNVERIFIED',
     'the live probe could not reach production (network) or the deploy is not the probed commit; '
     'UNVERIFIED is not a pass and not a red either'),
    (r'precache revision|service worker',
     'sw.js was generated before its inputs changed - rebuild in order and re-run the determinism '
     'judge (t_deterministic_sw)'),
)


def run(args, timeout=180):
    p = subprocess.run(args, cwd=B.ROOT, capture_output=True, text=True, encoding='utf-8',
                       timeout=timeout)
    return p.returncode, (p.stdout or '') + (p.stderr or '')


def failing_log(sha):
    """(run-id, log tail) for the failed workflow run of `sha`, or (None, '')."""
    rc, out = run(['gh', 'run', 'list', '--limit', '15', '--json',
                   'databaseId,headSha,workflowName,status,conclusion'])
    if rc != 0:
        return None, ''
    try:
        runs = json.loads(out)
    except ValueError:
        return None, ''
    for item in runs:
        if (item.get('headSha') or '').startswith(sha) and item.get('conclusion') == 'failure':
            _rc, log = run(['gh', 'run', 'view', str(item['databaseId']), '--log-failed'], timeout=600)
            return item['databaseId'], log[-4000:]
    return None, ''


def advice(text):
    return [fix for pattern, fix in HINTS if re.search(pattern, text, re.I)]


def exit_for(state):
    """green=0, red=1, everything else=2. `unknown` and `pending` must never look like a pass."""
    return {'green': 0, 'red': 1}.get(state, 2)


def selftest():
    """The three things a hook depends on: the mapping, the signatures, and the non-inert table."""
    red_log = ('Run 12: node half failed\\nError: Cannot find package \'workbox-build\' '
               'ERR_MODULE_NOT_FOUND\\n')
    other_log = ('FAIL: reports/judge-coverage.json matches this measurement: run: python tools/judge_coverage.py')
    cases = [
        ('a missing-dependency log is answered with npm ci, not with a rebuild',
         any('npm ci' in h for h in advice(red_log)), str(advice(red_log))[:60]),
        ('a stale-ledger log names the generator', any('generator' in h for h in advice(other_log)),
         str(advice(other_log))[:60]),
        ('an unmatched log says so and hands over the command, never "looks fine"',
         not advice('some unrelated failure'), str(advice('some unrelated failure'))),
        ('green exits 0, red exits 1, pending and unknown exit 2',
         [exit_for(s) for s in ('green', 'red', 'pending', 'unknown', 'garbage')] == [0, 1, 2, 2, 2],
         str([exit_for(s) for s in ('green', 'red', 'pending', 'unknown', 'garbage')])),
        ('the signature table is not inert (a rule with no patterns cannot fire)',
         len(HINTS) >= 6 and all(fix for _p, fix in HINTS), '%d patterns' % len(HINTS)),
        ('every pattern is a regex that compiles (a typo would silently kill a row)',
         all(_compiles(p) for p, _f in HINTS), 're.compile over HINTS'),
    ]
    bad = sum(1 for _n, ok, _d in cases if not ok)
    for name, ok, detail in cases:
        print('  %s %s (%s)' % ('ok ' if ok else 'SELFTEST-FAIL', name, detail))
    print('ci-watch selftest: %d cases, %d failures' % (len(cases), bad))
    return 1 if bad else 0


def _compiles(pattern):
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


def report(sha, verbose=True):
    """One pass: (state, line). Reuses release.ci_verdict so the two tools can never disagree."""
    state, detail = R.ci_verdict(sha)
    if state != 'red':
        return state, '%s: %s' % (state.upper(), detail)
    run_id, log = failing_log(sha)
    hints = advice(log or detail)
    lines = ['RED: %s (run %s)' % (detail, run_id or 'not found')]
    for h in hints or ['no signature matched - read the log: '
                       'gh run view %s --log-failed' % (run_id or '<id>')]:
        lines.append('  FIX: ' + h)
    if verbose and log:
        tail = [ln for ln in log.splitlines() if re.search(r'(?:FAIL|Error|error:|not found)', ln)]
        for ln in tail[-6:]:
            lines.append('  log: ' + ln.strip()[:200])
    return state, chr(10).join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--sha', default='')
    ap.add_argument('--timeout', type=int, default=600)
    ap.add_argument('--interval', type=int, default=30)
    ap.add_argument('--once', action='store_true')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    sha = args.sha or run(['git', 'rev-parse', 'HEAD'])[1].strip()
    if not sha:
        print('UNVERIFIED: no commit to watch')
        return 2
    budget, waited, state, line = args.timeout, 0, 'pending', ''
    while True:
        state, line = report(sha)
        if args.once or state in ('green', 'red', 'unknown') or waited >= budget:
            break
        time.sleep(args.interval)
        waited += args.interval
    if args.json:
        print(json.dumps({'sha': sha[:9], 'state': state, 'detail': line}, ensure_ascii=False))
    else:
        print(line)
        if state == 'pending':
            print('after %ds the jobs still had not finished - that is not a pass, re-run '
                  'or lower --interval' % waited)
    return exit_for(state)


if __name__ == '__main__':
    sys.exit(main())
