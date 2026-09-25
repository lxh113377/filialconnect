#!/usr/bin/env python3
"""Print the axe nodes behind every failing Lighthouse audit in a run.

Exists because `lhci assert` only says "color-contrast failure": a CI-only contrast defect stayed
unreproducible for three rounds while the reports on the same runner already named the element.
Exits non-zero when there is nothing to inspect, so the diagnostic cannot pass by measuring nothing.
"""
import glob
import json
import os
import sys

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else '.lighthouseci'
    files = sorted(glob.glob(os.path.join(target, 'lhr-*.report.json')))
    inspected = 0
    reported = 0
    for fp in files:
        try:
            with open(fp, encoding='utf-8') as f:
                report = json.load(f)
        except Exception as exc:
            print('unreadable report %s: %s' % (fp, exc))
            continue
        inspected += 1
        url = report.get('finalUrl') or report.get('requestedUrl') or '?'
        for key, audit in sorted((report.get('audits') or {}).items()):
            score = audit.get('score')
            if score is None or score >= 1:
                continue
            reported += 1
            print('FAIL %s | %s | score=%s | %s' % (os.path.basename(fp), key, score, url))
            for item in ((audit.get('details') or {}).get('items') or [])[:6]:
                node = item.get('node') or {}
                print('   node: %s | %s' % (node.get('target'), (node.get('explanation') or '')[:220]))
                if node.get('html'):
                    print('   html: %s' % node['html'][:200])
    print('reports inspected: %d | failing audits reported: %d' % (inspected, reported))
    if inspected == 0:
        print('DIAGNOSTIC FAILED: no Lighthouse reports under %s' % target)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
