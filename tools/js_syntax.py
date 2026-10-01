# -*- coding: utf-8 -*-
"""First-party JavaScript is judged by something that speaks JavaScript.

Round 75 wrote the rule this tool applies: *a file a machine executes must be judged by something
that speaks that machine's language, or the green is a green about our regex*. It caught a workflow
that was not YAML while 2,122 text-readers reported pass. The same shape sits one language over:
every reader this repository has for `.js` and `.mjs` is a text reader - `build.py` reads
`assets/js/i18n.js`, `stage-site.py` greps `sw.js` for precache entries, `check-i18n.py` scans the
scripts for `t('...')` calls - and none of them can notice that a shipped script stopped being a
program.

That is not hypothetical. On 2026-10-01 this round appended `function ( {` to `assets/js/search.js`
(the bytes came back, verified by blob oid before and after) and ran the chain:
`PASS: 2123 checks`, rc=0, and the string `search.js` appeared zero times in the output. A
syntactically dead script - one where the browser throws before line 1, so the search panel that
page exists for never loads - was invisible to every judge here. Node is the only reader in this
toolchain that speaks the language, and CI only executes `tools/*.mjs`, never the files that ship
to a phone.

The population is enumerated from `git ls-files`, never hand-listed (round 42: a hand-counted zero
became three documents), and never taken from the working tree, which regenerates. Each unit gets
one of three outcomes - `ok`, `bad`, `blind` (the probe could not run against it) - and the
identity `ok + bad + blind == units` is printed and enforced, so a branch that forgets to count
cannot turn "did not look" into a green.

Usage:
    python tools/js_syntax.py                 # judge the real tree, print the face line
    python tools/js_syntax.py --json          # the same measurement as one JSON object
    python tools/js_syntax.py --selftest      # both directions, in a sandbox; no shipped file touched
Exit: 0 clean | 1 an unparsable unit, an empty population, or the identity does not close
      2 the judgement could not be made (no node, or git cannot list the population) - not a pass
"""
import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTENSIONS = ('.js', '.mjs')
#: Tracked sources are the population, so these only guard against a build output being committed
#: into the tree later; naming them keeps the reason readable instead of a silent drop.
SKIP_DIRS = ('node_modules', 'dist', 'pagefind')
#: node's own message for this mismatch is a parse error mentioning `import`, which reads like a
#: broken file rather than a wrong goal - so the goal is stated before node is trusted.
TOP_LEVEL_MODULE_SYNTAX = re.compile(r'^(?:import|export)\s', re.M)
#: The exact bytes this round appended to `assets/js/search.js` to prove the chain could not see it.
BROKEN = "var panel = document.getElementById('search');\nfunction ( {\n"
GOOD_SCRIPT = "var panel = document.getElementById('search');\nif (panel) { panel.hidden = false; }\n"
GOOD_MODULE = "import fs from 'fs';\nexport function build(x) { return x; }\n"


def _git(args, cwd):
    return subprocess.run(['git', '-c', 'core.quotePath=false'] + list(args), cwd=cwd,
                          capture_output=True, text=True, encoding='utf-8', errors='replace',
                          timeout=120)


def tracked_js(root=None):
    """(paths, state): the population git decides, or why it could not be decided.

    An empty list with state 'ok' means the repository really has no JavaScript; 'git-unavailable'
    means nothing was seen. Those two are different facts and only the first may lead to a verdict.
    """
    root = root or ROOT
    try:
        r = _git(['ls-files', '-z', '--'] + ['*%s' % e for e in EXTENSIONS], root)
    except (OSError, subprocess.SubprocessError) as exc:
        return [], 'git-unavailable(%s)' % type(exc).__name__
    if r.returncode != 0:
        return [], 'git-failed(rc=%d)' % r.returncode
    paths = []
    for rel in (r.stdout or '').split('\0'):
        rel = rel.strip().replace('\\', '/')
        if not rel or not rel.endswith(EXTENSIONS):
            continue
        if any(part in SKIP_DIRS for part in rel.split('/')[:-1]):
            continue
        paths.append(os.path.join(root, rel.replace('/', os.sep)))
    return sorted(paths), 'ok'


def goal_of(path):
    return 'module' if path.endswith('.mjs') else 'script'


def node_version(node):
    p = subprocess.run([node, '--version'], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=60)
    return (p.stdout or '').strip() or 'unknown'


def parse_one(node, path):
    """(outcome, note): outcome is 'ok', 'bad' or 'blind' - the third is never folded into either."""
    if not os.path.isfile(path):
        return 'blind', 'named by the enumerator but not on disk'
    try:
        p = subprocess.run([node, '--check', path], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return 'blind', 'probe failed (%s)' % type(exc).__name__
    if p.returncode == 0:
        return 'ok', ''
    lines = [ln.strip() for ln in (p.stderr or p.stdout or '').splitlines() if ln.strip()]
    #: node prints the offending path first; the reason a human needs is the `...Error:` line.
    note = next((ln for ln in lines if 'Error:' in ln), lines[0] if lines else '')
    return 'bad', (note[:160] or 'node --check refused it without a message')


def goal_findings(path, goal):
    """ESM syntax sitting in a script-goal file: say it plainly instead of quoting node."""
    if goal != 'script':
        return []
    try:
        text = io.open(path, encoding='utf-8', errors='replace').read()
    except OSError as exc:
        return ['unreadable (%s)' % type(exc).__name__]
    return ['ESM syntax in a script-goal file'] if TOP_LEVEL_MODULE_SYNTAX.search(text) else []


def scan(root=None, paths=None, node=None):
    """The measurement, or None when there is no parser to make it."""
    node = node or shutil.which('node')
    if not node:
        return None
    state = 'ok'
    if paths is None:
        paths, state = tracked_js(root)
    root = root or ROOT
    counts = {'ok': 0, 'bad': 0, 'blind': 0}
    goals = {'script': 0, 'module': 0}
    findings = []
    for path in sorted(paths):
        rel = os.path.relpath(path, root).replace('\\', '/')
        goal = goal_of(path)
        goals[goal] += 1
        outcome, note = parse_one(node, path)
        counts[outcome] += 1
        if outcome != 'ok':
            findings.append('%s [%s]: %s' % (rel, goal, note or '%s does not parse' % outcome))
        for extra in goal_findings(path, goal):
            findings.append('%s [%s]: %s' % (rel, goal, extra))
    return {'units': len(paths), 'population_state': state, 'ok': counts['ok'],
            'bad': counts['bad'], 'blind_units': counts['blind'], 'goals': goals,
            'findings': findings, 'node': node_version(node)}


def identity_issues(rep):
    """Names every way the report can contradict its own counts. Empty means it closes."""
    if rep is None:
        return ['report missing (blind)']
    issues = []
    parts = rep['ok'] + rep['bad'] + rep['blind_units']
    if parts != rep['units']:
        issues.append('ok+bad+blind=%d != units=%d' % (parts, rep['units']))
    judged = rep['ok'] + rep['bad']
    if judged != rep['units'] - rep['blind_units']:
        issues.append('judged=%d != units-blind=%d' % (judged, rep['units'] - rep['blind_units']))
    if sum(rep['goals'].values()) != rep['units']:
        issues.append('goal counts %d != units %d' % (sum(rep['goals'].values()), rep['units']))
    return issues


def verdict(rep):
    """(ok, detail) - a blind unit, an empty population or a lying identity is never a pass."""
    if rep is None:
        return False, 'blind(no-node-parser)'
    if rep['population_state'] != 'ok':
        return False, 'population unreadable(%s)' % rep['population_state']
    if rep['units'] == 0:
        return False, 'empty population - nothing was read, so nothing is claimed'
    issues = identity_issues(rep)
    if issues:
        return False, 'identity does not close: %s' % issues[:2]
    if rep['blind_units']:
        return False, '%d unit(s) could not be probed' % rep['blind_units']
    if rep['findings']:
        return False, '%d finding(s): %s' % (len(rep['findings']), rep['findings'][:3])
    return True, 'units=%d all parsed' % rep['units']


def face(rep):
    """The line a human pastes: verdict plus its own denominator, so a green states what it read."""
    if rep is None:
        return 'JS-PARSE: blind(no-node-parser) units=? - this is not a pass'
    return ('JS-PARSE: units=%(u)d ok=%(ok)d bad=%(bad)d blind=%(blind)d '
            'goal=script:%(s)d/module:%(m)d population=%(pop)s node=%(node)s '
            'identity=%(id)s' % {
                'u': rep['units'], 'ok': rep['ok'], 'bad': rep['bad'], 'blind': rep['blind_units'],
                's': rep['goals']['script'], 'm': rep['goals']['module'],
                'pop': rep['population_state'], 'node': rep['node'],
                'id': '%d+%d+%d=%d' % (rep['ok'], rep['bad'], rep['blind_units'], rep['units'])})


def selftest():
    """Both directions against fixtures in a sandbox: the shipped tree is only ever read."""
    results = []
    tmp = tempfile.mkdtemp(prefix='js_syntax_')
    try:
        os.makedirs(os.path.join(tmp, 'assets'))
        good_js = os.path.join(tmp, 'assets', 'good.js')
        good_mjs = os.path.join(tmp, 'assets', 'good.mjs')
        _write(good_js, GOOD_SCRIPT)
        _write(good_mjs, GOOD_MODULE)
        rep = scan(tmp, [good_js, good_mjs])
        results.append(('control: a clean pair parses and the face names its own denominator',
                        rep['units'] == 2 and rep['ok'] == 2 and not rep['findings'], face(rep)))

        broken = os.path.join(tmp, 'assets', 'broken.js')
        _write(broken, BROKEN)
        rep = scan(tmp, [good_js, good_mjs, broken])
        results.append(('mutation: the bytes 2,123 checks could not see are named by unit and goal',
                        rep['bad'] == 1 and any('broken.js [script]' in f for f in rep['findings']),
                        str(rep['findings'][:1])))

        _write(broken, GOOD_SCRIPT)
        esm = os.path.join(tmp, 'assets', 'esm_in_script.js')
        _write(esm, "import x from 'y';\nconsole.log(x);\n")
        rep = scan(tmp, [good_js, good_mjs, esm])
        results.append(('goal leg: ESM syntax under a script goal is its own finding',
                        any('ESM syntax' in f for f in rep['findings']), str(rep['findings'][:1])))

        os.remove(broken)
        rep = scan(tmp, [good_js, esm, broken])
        issues = identity_issues(rep)
        results.append(('blind leg: a vanished unit is counted blind, and the identity still closes',
                        rep['blind_units'] == 1 and not issues and not verdict(rep)[0],
                        face(rep)))

        ok, detail = verdict(scan(tmp, []))
        results.append(('boundary: an empty population is refused, not read as clean',
                        not ok and 'empty' in detail, detail))

        ok, detail = verdict(None)
        results.append(('blindness: a missing parser gets its own state, not a zero',
                        not ok and 'blind' in detail, detail))

        paths, state = tracked_js(os.path.join(tmp, 'assets'))
        results.append(('population leg: git cannot list here, and that is reported as unreadable',
                        state != 'ok' and paths == [], state))

        rep = scan(ROOT)
        ok, detail = verdict(rep)
        results.append(('live tree: the real population closes on its own measurement',
                        rep is not None and rep['units'] >= 8 and ok,
                        '%s | %s' % (face(rep), detail)))
    finally:
        shutil.rmtree(tmp)
    passed = sum(1 for _, ok, _ in results if ok)
    for name, ok, detail in results:
        print('%s %s | %s' % ('ok  ' if ok else 'FAIL', name, detail))
    print('js_syntax selftest: %d/%d' % (passed, len(results)))
    return 0 if passed == len(results) else 1


def _write(path, text):
    io.open(path, 'w', encoding='utf-8', newline='\n').write(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Parse every tracked first-party .js/.mjs with node.')
    ap.add_argument('--json', action='store_true', help='print the measurement as one JSON object')
    ap.add_argument('--selftest', action='store_true', help='both directions in a sandbox')
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    rep = scan()
    print(face(rep))
    for line in (rep or {}).get('findings', []):
        print('  FINDING %s' % line)
    ok, detail = verdict(rep)
    print('%s js_syntax: %s' % ('PASS' if ok else 'FAIL', detail))
    if args.json:
        print(json.dumps(rep if rep else {'state': 'blind(no-node-parser)'},
                         ensure_ascii=False, sort_keys=True))
    if rep is None:
        return 2
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
