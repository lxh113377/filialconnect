#!/usr/bin/env python3
"""Coverage ledger for the static contrast audit, committed as reports/contrast-coverage.json.

Why a ledger and not just a pass/fail: the audit only judges pairs whose foreground and
background it can resolve. When that set shrinks - a rule gets reworded, a colour becomes
translucent, an ancestor link disappears - a green run silently means less than it used to.
Recording the denominators makes the shrinkage itself a finding.

Usage:
  python tools/contrast_coverage.py            # rewrite the ledger
  python tools/contrast_coverage.py --check    # exit 1 if the committed ledger is stale
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contrast_audit as ca

ROOT = ca.ROOT
LEDGER = 'reports/contrast-coverage.json'


def coverage(css):
    same = ca.pairs(css)
    inh = ca.inherited_pairs(css)
    return {
        'same_block_pairs': len(same),
        'same_block_resolved': sum(1 for e in same if e['opaque']),
        'same_block_below_threshold': len(ca.failures(same)),
        'inherited_pairs': len(inh),
        'inherited_resolved': sum(1 for e in inh if e['opaque']),
        'inherited_below_threshold': len(ca.inherited_failures(inh)),
        'unresolved': sum(1 for e in same + inh if not e['opaque']),
    }


def render(css):
    return json.dumps(coverage(css), indent=2, sort_keys=True) + '\n'


def main():
    check = '--check' in sys.argv
    want = render(ca.read(ca.CSS))
    path = os.path.join(ROOT, LEDGER)
    have = io.open(path, encoding='utf-8').read() if os.path.exists(path) else ''
    if check:
        if have != want:
            print('COVERAGE DRIFT: %s is stale (run: python tools/contrast_coverage.py)' % LEDGER)
            print('  committed: %s' % ' '.join(have.split()) or '(absent)')
            print('  computed : %s' % ' '.join(want.split()))
            return 1
        print('coverage in sync: %s' % ' '.join(want.split()))
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    io.open(path, 'w', encoding='utf-8', newline='\n').write(want)
    print('wrote %s: %s' % (LEDGER, ' '.join(want.split())))
    return 0


if __name__ == '__main__':
    sys.exit(main())
