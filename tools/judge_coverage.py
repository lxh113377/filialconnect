#!/usr/bin/env python3
"""One ledger of judge denominators, generated from the same functions the judges call.

The round-26 file this replaces was hand-copied and had already drifted: it recorded an offline
package of 77 entries / 28 source files while the packager today returns 82 / 33. A coverage
ledger nobody can regenerate is a second copy of a number - the defect it was written to catch.

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
    pkg = _sibling('package_offline', 'package-offline.py')
    stager = _sibling('stage_site', 'stage-site.py')
    _entries, counts = pkg.members()
    sets, _audit = stager.staging_sets()
    return {
        'checks_last_run': None,
        'deploy_profile_files': len(sets['deploy']),
        'judge_functions': len(defined),
        'judge_functions_registered': len(registered),
        'judges_defined_but_unregistered': sorted(set(defined) - set(registered)),
        'offline_package_entries': counts['total'],
        'offline_package_site_files': counts['site'],
        'offline_package_source_files': counts['source'],
        'pagefind_shards_local': len([p for p in sets['deploy'] if p.startswith('pagefind/')]),
        'probe_profile_files': len(sets['probe']),
    }


def render():
    return json.dumps(measure(), indent=2, sort_keys=True) + '\n'


def main():
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
