#!/usr/bin/env python3
"""One ledger of judge denominators, generated from the same functions the judges call.

The round-26 file this replaces was hand-copied and had already drifted: it recorded an offline
package of 77 entries / 28 source files while the packager today returns 82 / 33. A coverage
ledger nobody can regenerate is a second copy of a number - the defect it was written to catch.

Everything recorded here must be machine-independent. A count of a regenerable artifact is not:
the first version stored `pagefind_shards_local`, was green locally with 52 and went red in CI,
where the index is built by a later step. Removing only that key did not fix it:
`deploy_profile_files` was 101 with the index on disk and 49 without, the same disease in a
different field. Measured both ways before touching anything. What git decides (the committed
set) is portable; what my working tree happens to contain is not.

Usage:
  python tools/judge_coverage.py            # rewrite reports/judge-coverage.json
  python tools/judge_coverage.py --check    # exit 1 if the committed ledger is stale
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build  # noqa: E402

ROOT = build.ROOT
LEDGER = 'reports/judge-coverage.json'
ALLOWED_FIELDS = frozenset([
    "build_output_dirs_declared", "checks_last_run", "judge_functions",
    "judge_functions_registered", "judges_defined_but_unregistered", "notes"])


def _sibling(alias, fname):
    import importlib.util
    spec = importlib.util.spec_from_file_location(alias, os.path.join(ROOT, 'tools', fname))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def judge_functions():
    text = io.open(os.path.join(ROOT, 'tools', 'test_build.py'), encoding='utf-8').read()
    defined = sorted(set(re.findall(r'^def (t_[a-z0-9_]+)\(', text, re.M)))
    registered_block = re.search(r'for fn in \(([^)]*)\):', text, re.S)
    registered = sorted(set(re.findall(r'\bt_[a-z0-9_]+', registered_block.group(1))))
    return defined, registered


def measure():
    defined, registered = judge_functions()
    stager = _sibling('stage_site', 'stage-site.py')   # declarations only, never its sets
    return {
        'checks_last_run': None,
        'judge_functions': len(defined),
        'judge_functions_registered': len(registered),
        'judges_defined_but_unregistered': sorted(set(defined) - set(registered)),
        'notes': (
            'Deliberately NOT recorded here: any count owned by another authority. '
            'deploy/probe file counts belong to reports/deploy-staging.json (and to git itself), '
            'offline package membership belongs to package-offline.members(), and the check total '
            'belongs to the line tools/test_build.py prints. Each of those was copied here once and '
            'each copy went stale - three CI reds in one day. Field set is pinned by '
            't_judge_ledger; adding a number needs a reason and a removal.'),
        'build_output_dirs_declared': sorted(stager.BUILD_OUTPUT_DIRS),

    }


def render():
    return json.dumps(measure(), indent=2, sort_keys=True) + '\n'



def selftest():
    """`measure()` may not derive a ledger value from git state, the filesystem, or another
    tool\'s membership - those are quantities owned elsewhere, and freezing a copy of one into a
    committed report is what made CI red three times on 2026-09-26.

    The rule reads the AST, not the text. It must not: the first version scanned raw source and
    matched the prose in `notes` that names the very calls it forbids, so it reported a violation
    that did not exist. Code and sentences about code need different instruments.

    Three cases: the rule must fire on a fixture that really calls git; it must stay silent on
    this file; and it must not be inert (a rule with no positive case is a decoration).
    """
    import ast

    src = io.open(os.path.join(ROOT, 'tools', 'judge_coverage.py'), encoding='utf-8').read()
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'measure')
    forbidden_calls = {'members', 'staging_sets', 'listdir', 'run', 'check_output', 'popen'}
    forbidden_mods = {'subprocess'}
    used_calls, used_mods = set(), set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else '')
            if name:
                used_calls.add(name)
            base = f.value if isinstance(f, ast.Attribute) else None
            if isinstance(base, ast.Name):
                used_mods.add(base.id)
        elif isinstance(node, ast.Name) and node.id in forbidden_mods:
            used_mods.add(node.id)
    problems = sorted((used_calls & forbidden_calls) | (used_mods & forbidden_mods))

    fixture = ast.parse("def measure():\n    import subprocess\n"
                        "    return {'n': len(pkg.members()) + len(__import__('os').listdir('.'))}")
    fx = next(n for n in ast.walk(fixture) if isinstance(n, ast.FunctionDef) and n.name == 'measure')
    fx_calls = {((n.func.attr if isinstance(n.func, ast.Attribute)
                  else n.func.id) if isinstance(n, ast.Call) else '')
                for n in ast.walk(fx)} - {''}
    fx_mods = {n.id for n in ast.walk(fx) if isinstance(n, ast.Name) and n.id in forbidden_mods}
    fired = sorted((fx_calls & forbidden_calls) | (fx_mods & forbidden_mods))

    cases = [
        ('the fixture trips the rule (positive control)', len(fired) >= 2, fired),
        ('this file\'s measure() is clean (real run)', not problems, problems),
        ('the forbidden vocabulary is non-empty (rule is not inert)',
         bool(forbidden_calls & {'members', 'staging_sets', 'listdir'}), sorted(forbidden_calls)),
    ]
    failed = ['%s -> %s' % (name, detail) for name, ok, detail in cases if not ok]
    print('judge_coverage selftest: %d cases, %d violations in measure(), %d case failures'
          % (len(cases), len(problems), len(failed)))
    for f in failed:
        print('  SELFTEST-FAIL ' + f)
    return 1 if failed else 0
def main():
    if '--selftest' in sys.argv:
        return selftest()
    check = '--check' in sys.argv
    want = render()
    path = os.path.join(ROOT, LEDGER)
    have = io.open(path, encoding='utf-8').read() if os.path.exists(path) else ''
    ledger = json.loads(want)
    problems = []
    if not ledger['judge_functions']:
        problems.append('zero judges enumerated - the scanner is not working')
    if ledger['judges_defined_but_unregistered']:
        problems.append('defined but never run: %s'
                        % ', '.join(ledger['judges_defined_but_unregistered']))
    if set(ledger) != ALLOWED_FIELDS:
        problems.append('field set changed: extra=%s missing=%s'
                        % (sorted(set(ledger) - set(ALLOWED_FIELDS)),
                           sorted(set(ALLOWED_FIELDS) - set(ledger))))
    if ledger['judge_functions'] != ledger['judge_functions_registered']:
        problems.append('judge inventory disagrees with itself')
    if check and have != want:
        problems.append('%s is stale (run: python tools/judge_coverage.py)\n  committed: %s'
                        '\n  computed : %s'
                        % (LEDGER, ' '.join(have.split()) or '(absent)', ' '.join(want.split())))
    for p in problems:
        print('LEDGER FAIL: ' + p)
    if problems:
        return 1
    print('ledger ok: %s' % ' '.join(want.split()))
    if not check:
        io.open(path, 'w', encoding='utf-8', newline='\n').write(want)
        print('wrote %s' % LEDGER)
    return 0


if __name__ == '__main__':
    sys.exit(main())
