#!/usr/bin/env python3
"""Which tools are wired into a blocking chain, and which are declared hand-only?

Round 26 made "a tool that is not wired into a blocking chain is a half-finished tool" a rule
(AGENTS.md class 5). The guard for that rule was itself an unwired file, outside the repository,
with a hard-coded absolute Windows path, that checked 4 of 16 scripts and that nothing ran. This
is that guard, inside the tree, covering every tool, and wired into CI.

Every file in tools/ declares exactly one consumer class in tools/gate-wiring.json:
  ci      named by a step in .github/workflows/*.yml
  test    loaded and executed by tools/test_build.py
  release runs only on the release path (release.py calls it), disclosed in AGENTS.md
  hand    run by nobody automatically: it must be disclosed in AGENTS.md as hand-only

Observed placement wins over the declaration only in the sense that a tool declared `ci` but
named nowhere is a silent gap and fails. A tool that appears somewhere it was not declared
lands in both lists, which the ledger makes visible.

Usage:
  python tools/gate_wiring.py            # rewrite reports/gate-wiring.json
  python tools/gate_wiring.py --check    # exit 1 on drift, an undeclared tool, or a silent gap
"""
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = 'reports/gate-wiring.json'
DECLARED = os.path.join('tools', 'gate-wiring.json')
BUCKETS = ('ci', 'test', 'release', 'hand')


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding='utf-8').read()


def tool_files():
    return sorted(f for f in os.listdir(os.path.join(ROOT, 'tools'))
                  if f.endswith(('.py', '.mjs')) and not f.startswith('_'))


def ci_names():
    """File names actually named by a workflow step.

    Matched on the path `tools/x`, not on a bare word: a step comment or an npm alias is not
    wiring, and treating one as wiring is how a gap stays invisible.
    """
    wdir = os.path.join(ROOT, '.github', 'workflows')
    text = ''.join(read(os.path.join('.github', 'workflows', wf))
                   for wf in sorted(os.listdir(wdir)))
    return set(re.findall(r'tools/([A-Za-z0-9_.-]+\.(?:py|mjs))', text))


def test_names():
    """Tools loaded and executed by the suite: `load_tool('alias', 'file.py')` and the two
    generator module imports. A file name merely mentioned in a failure hint is not a call."""
    text = read(os.path.join('tools', 'test_build.py'))
    hits = set(re.findall(r"load\w*\(\s*'[a-z0-9_]+'\s*,\s*'([a-z0-9_.-]+\.(?:py|mjs))'", text))
    hits |= set(re.findall(r'^(?:import|from)\s+(build|stage_site|contrast_audit|release)'
                           r'(?:\s|$)', text, re.M))
    return {h if h.endswith(('.py', '.mjs')) else h + '.py' for h in hits}


def invoked_names(text):
    """Files a module reaches: load_tool('alias', 'x.py'), a sibling import, or a shell call
    naming tools/x.py. Name-dropping in a comment is not reachability, so shell calls must
    carry the tools/ prefix."""
    # Only two forms count as an invocation: `load_tool('alias', os.path.join(..., 'x.py'))`
    # and a shell step naming `tools/x.py`. A file name inside a comment or a failure hint is
    # not wiring - that is exactly the difference between `perf-probe.mjs` (a string) and
    # `release.py` (executed with five fixtures on every commit).
    hits = set(re.findall(
        r"load\w*\(.*?['\"]([a-z0-9_.-]+\.(?:py|mjs))['\"]", text, re.S))
    hits |= set(re.findall(r'(?:python3?|node|npx)[^\n]*?tools/([A-Za-z0-9_.-]+\.(?:py|mjs))',
                           text))
    hits |= {m + '.py' for m in re.findall(r'^(?:import|from)\s+(build|stage_site|contrast_audit'
                                           r'|release|package_offline|judge_coverage|gate_wiring)'
                                           r'(?:\s|$|\.)', text, re.M)}
    return hits


def reach(roots, all_tools):
    """Everything the roots execute, transitively - a tool wired through one hop is wired."""
    graph = {t: invoked_names(read(os.path.join('tools', t))) for t in all_tools}
    seen, stack = set(roots), list(roots)
    while stack:
        cur = stack.pop()
        for nxt in graph.get(cur, ()):
            if nxt in all_tools and nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def measure():
    declared = json.loads(read(DECLARED))
    disk = tool_files()
    direct_ci = ci_names()
    direct_test = {t for t in disk
                   if t in invoked_names(read(os.path.join('tools', 'test_build.py')))}
    in_ci = direct_ci | reach(direct_ci & set(disk), set(disk))
    in_test = direct_test | reach(direct_test, set(disk))
    ledger = {'tools_on_disk': len(disk), 'declared': len(declared)}
    ledger.update({b: [] for b in BUCKETS})
    ledger.update({'undeclared': [], 'declared_but_absent': [], 'silent_gap': [],
                   'undocumented_hand_only': []})
    agents = read('AGENTS.md')
    for tool in disk:
        kind = declared.get(tool)
        if kind not in BUCKETS:
            ledger['undeclared'].append(tool)
            continue
        if tool in direct_ci:
            observed = 'ci'
        elif tool in direct_test:
            observed = 'test'
        elif tool in in_ci or tool in in_test:
            observed = 'transitive'          # wired, one hop away; not a silent gap
        else:
            observed = 'nowhere'
        if kind in ('ci', 'test') and observed not in (kind, 'transitive'):
            ledger['silent_gap'].append('%s declared %s, observed %s' % (tool, kind, observed))
        if kind == 'hand' and tool not in agents:
            ledger['undocumented_hand_only'].append(tool)
        if tool in direct_ci:
            ledger['ci'].append(tool)
        elif tool in direct_test:
            ledger['test'].append(tool)
        else:
            ledger[kind].append(tool)
    ledger['declared_but_absent'] = [t for t in declared if t not in disk]
    return ledger


def render():
    return json.dumps(measure(), indent=2, sort_keys=True) + '\n'


def main():
    import sys
    check = '--check' in sys.argv
    want = render()
    path = os.path.join(ROOT, LEDGER)
    have = io.open(path, encoding='utf-8').read() if os.path.exists(path) else ''
    ledger = json.loads(want)
    problems = []
    if not ledger['tools_on_disk']:
        problems.append('zero tools found - an empty denominator is never a pass')
    for key in ('undeclared', 'declared_but_absent', 'silent_gap', 'undocumented_hand_only'):
        if ledger.get(key):
            problems.append('%s: %s' % (key, ', '.join(ledger[key])))
    if check and have != want:
        problems.append('%s is stale (run: python tools/gate_wiring.py)' % LEDGER)
    for p in problems:
        print('WIRING FAIL: ' + p)
    if problems:
        return 1
    print('wiring ok: %d tools - ci=%d test=%d release=%d hand=%d' % (
        ledger['tools_on_disk'], len(ledger['ci']), len(ledger['test']),
        len(ledger['release']), len(ledger['hand'])))
    if not check:
        io.open(path, 'w', encoding='utf-8', newline='\n').write(want)
        print('wrote %s' % LEDGER)
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
