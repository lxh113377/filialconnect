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

# The triage rows, and the only place they are written. `AGENTS.md` renders this table through
# `tools/triage.py --write` and CI verifies it with `--check`, because in round 36 it was a hand
# copy and by round 37 it had drifted: both sides had nine rows (so a length comparison stays green)
# while three rows lived only in the code and three only in the document - including two document
# rows that are not log signatures and therefore can never fire. `sig` is what a reader greps for,
# `pattern` is what this tool matches, and `cause`/`action` are shared by the CLI and the document.
HINTS = (
    {'sig': '`ERR_MODULE_NOT_FOUND` / `Cannot find package`',
     'pattern': r'ERR_MODULE_NOT_FOUND|Cannot find (?:package|module)',
     'cause': '缺依赖，**不是**产物漂移',
     'action': 'run `npm ci` - dependencies are missing, this is not artifact drift; a worktree '
               'must never link node_modules from the live repo (t_no_link_code)'},
    {'sig': '`no build input is untracked` / `Did you mean --force?`',
     'pattern': r'no build input is untracked|Did you mean --force|pathspec .* did not match any files',
     'cause': '上一笔提交用了 `git add -u`（漏新文件）',
     'action': 'a commit was made without new files: `git add <paths>` then re-check '
               '`git show --name-only`; `git add -u` skips untracked ones'},
    {'sig': '`matches this measurement: run: python tools/…`',
     'pattern': r'matches this measurement',
     'cause': '生成物/台账过期',
     'action': 'a generated ledger is stale - run the generator its own message names '
               '(tools/judge_coverage.py, tools/gate_wiring.py, ...) and commit its output'},
    {'sig': '`node half reports no drift` / `i18n.js … out of sync`',
     'pattern': r'node half reports no drift|i18n.js .* out of sync',
     'cause': '构建顺序反了：node 侧派生件早于 python 侧',
     'action': 'build order is python then node: `python tools/build.py && node tools/build.mjs`, '
               'then re-run `node tools/build.mjs check`'},
    {'sig': 'job 数秒失败且 `steps=0`',
     'pattern': r'steps=0|Could not allocate|waiting for a runner',
     'cause': '没拿到 runner（配额/环境），不是代码错',
     'action': 'the job never got a runner: read annotations at '
               '`gh api repos/<slug>/check-runs/<id>/annotations` - it is not a code failure'},
    {'sig': '`ABORTED JUDGES: t_xxx`',
     'pattern': r'ABORTED JUDGES',
     'cause': '某判据崩了 ⇒ 它之后所有判据的结论丢失（含已收集失败的打印）',
     'action': 'a judge crashed instead of reporting: fix that judge first - while it is aborting, '
               'the evidence of every later judge is lost'},
    {'sig': '`HTTP 404` / `assertion … 404`',
     'pattern': r'assertion.*404|HTTP 404',
     'cause': '`gh api` 的 GET 参数被当 body 发了',
     'action': '`gh api` GET parameters belong in the query string; `-f` puts them in the body and '
               'turns a good path into a 404'},
    {'sig': '`verify-live … UNVERIFIED`',
     'pattern': r'verify-live|UNVERIFIED',
     'cause': '网络不可达，或线上部署不是被探针的那笔提交',
     'action': 'the live probe could not reach production (network) or the deploy is not the '
               'probed commit; UNVERIFIED is not a pass and not a red either'},
    {'sig': '`precache revision` / `service worker`',
     'pattern': r'precache revision|service worker',
     'cause': 'sw.js 早于它的输入生成',
     'action': 'sw.js was generated before its inputs changed - rebuild in order and re-run the '
               'determinism judge (t_deterministic_sw)'},
    # Round 37's own two new failure shapes, added the round they were measured (a signature table
    # that never grows is a table that stopped describing this repository).
    {'sig': '`hand drift: N row(s) differ`',
     'pattern': r'hand drift: \d+ row',
     'cause': 'AGENTS.md 的 Triage 表被手改，或 `HINTS` 改了没重生成',
     'action': 'run `python tools/triage.py --write` and commit it; the section between the markers '
               'is generated, so hand edits there are not a second opinion (t_triage_copy)'},
    {'sig': '`stale receipt` / `malformed receipt`',
     'pattern': r'stale receipt|malformed receipt',
     'cause': '报告里的收尾回执不是本次实测（或字段残缺）',
     'action': 're-run `python _internal/closeout_round.py --emit` and paste the whole block again; '
               'a receipt from last round is not evidence this round closed'},
    # Round 43's shape: the hygiene judge went from "one green" to "four legs with sample counts",
    # so a red here means the workflow text or the report itself is inconsistent, not that CI broke.
    {'sig': '`unknown permission key` / `declared untested`',
     'pattern': r'unknown permission key|declared untested|permissions block parsed empty',
     'cause': '工作流里写了 GitHub 不认识的权限键（拼错即静默失权），或判据报告自称某腿无样本却与'
              '样本数矛盾（块锚定把 `runs-on` 之类误当权限项）',
     'action': '按 `tools/ci_hygiene.py` 的 `KNOWN_SCOPES` 改键名或删掉那行；若是锚定问题，'
               '修 `job_blocks()` 的缩进回引用，不要放宽判据或把键加进豁免名单'},
)

# One synthetic log line per row, in the words the real failure actually printed. This is the
# positive control the table never had: a pattern whose spelling no longer matches anything is a
# dead row, and a dead row cannot be told apart from an absent one unless something fires it.
FIXTURES = {
    '`ERR_MODULE_NOT_FOUND` / `Cannot find package`':
        "Error: Cannot find package 'workbox-build' imported from tools/build.mjs",
    '`no build input is untracked` / `Did you mean --force?`':
        "The following paths are ignored by one of your .gitignore files: reports\nhint: Use -f if "
        "you really want to add them.\nno build input is untracked",
    '`matches this measurement: run: python tools/…`':
        'FAIL: reports/judge-coverage.json matches this measurement: run: python '
        'tools/judge_coverage.py',
    '`node half reports no drift` / `i18n.js … out of sync`':
        'node half reports no drift but assets/i18n.js is out of sync with the locales',
    'job 数秒失败且 `steps=0`':
        'Run 4812 failed in 3s with steps=0 - the job was waiting for a runner',
    '`ABORTED JUDGES: t_xxx`':
        'ABORTED JUDGES: t_offline_package',
    '`HTTP 404` / `assertion … 404`':
        'gh api repos/x/y/pulls returned HTTP 404; assertion failed on a 404 body',
    '`verify-live … UNVERIFIED`':
        'verify-live: UNVERIFIED - could not reach lxh113377.github.io (curl 000)',
    '`precache revision` / `service worker`':
        'the precache revision is stale: the service worker was built before its inputs changed',
    '`hand drift: N row(s) differ`':
        'DRIFT: hand drift: 2 row(s) differ (only in HINTS: a; only in the document: b)',
    '`stale receipt` / `malformed receipt`':
        'RED  the report carries the close-out receipt  stale receipt: inner says f7fd452ab, '
        'measured 6999601',
    # Round 43's row: the sample text is a real judge line, so the row cannot be added without a
    # signature that actually fires (that is what the selftest below enforces for every row).
    '`unknown permission key` / `declared untested`':
        'FAIL: no workflow grants a wildcard scope, write-all, or a job wider than its header: '
        "[\'deploy.yml: top-level permissions has contets (unknown permission key)\'] | every "
        'hygiene leg is judged or declared untested: declared untested [job_within_header] != '
        "zero-sample legs []",
}


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
    return [row['action'] for row in HINTS if re.search(row['pattern'], text, re.I)]


def exit_for(state):
    """green=0, red=1, everything else=2. `unknown` and `pending` must never look like a pass."""
    return {'green': 0, 'red': 1}.get(state, 2)


def selftest():
    """The three things a hook depends on: the mapping, the signatures, and the non-inert table."""
    red_log = ('Run 12: node half failed\\nError: Cannot find package \'workbox-build\' '
               'ERR_MODULE_NOT_FOUND\\n')
    other_log = ('FAIL: reports/judge-coverage.json matches this measurement: '
                 'run: python tools/judge_coverage.py')
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
         len(HINTS) >= 6 and all(row['action'] for row in HINTS), '%d patterns' % len(HINTS)),
        ('every pattern is a regex that compiles (a typo would silently kill a row)',
         all(_compiles(row['pattern']) for row in HINTS), 're.compile over HINTS'),
        # Round 37: the row is four fields now because the document renders three of them, and a
        # missing or pipe-carrying field would render a broken table rather than a red run.
        ('every row carries sig/cause/action/pattern, all non-empty',
         all(all(row.get(k) for k in ('sig', 'cause', 'action', 'pattern')) for row in HINTS),
         '%d rows shaped' % len(HINTS)),
        ('no rendered cell can contain a pipe or newline (it would add a column to the document)',
         not any(ch in row[k] for row in HINTS for k in ('sig', 'cause', 'action')
                 for ch in ('|', '\n')), 'cell shape'),
        ('every signature is distinctive enough to name a row (no row is the empty string)',
         len(set(row['sig'] for row in HINTS)) == len(HINTS),
         '%d distinct signatures' % len(set(row['sig'] for row in HINTS))),
        ('every row can still fire: a fixture log line per signature, %d for %d'
         % (len(HINTS), len(FIXTURES)),
         [row['sig'] for row in HINTS if row['action'] not in advice(FIXTURES[row['sig']])] == [],
         'dead rows: %s' % [row['sig'] for row in HINTS
                             if row['action'] not in advice(FIXTURES[row['sig']])][:70]),
        ('the fixture set covers exactly the rows that exist (a new row must ship its own probe)',
         set(FIXTURES) == set(row['sig'] for row in HINTS),
         '%d fixtures / %d rows' % (len(FIXTURES), len(HINTS))),
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
