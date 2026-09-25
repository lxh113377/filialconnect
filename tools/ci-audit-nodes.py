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

def find_reports(target):
    """Every json under target that actually looks like a Lighthouse result.

    Deliberately not a filename pattern: the first version globbed `lhr-*.report.json` and read 0
    files in CI, because the stored name is lhci's business, not ours. Content sniffing survives
    that, and the directory listing below makes the assumption auditable in the log itself.
    """
    found = []
    for root, _dirs, names in os.walk(target):
        for name in sorted(names):
            if not name.endswith('.json'):
                continue
            fp = os.path.join(root, name)
            try:
                with open(fp, encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                continue
            if isinstance(data, dict) and isinstance(data.get('audits'), dict):
                found.append((fp, data))
    return found


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else '.lighthouseci'
    print('storage dir : %s (exists=%s)' % (target, os.path.isdir(target)))
    if os.path.isdir(target):
        listing = sorted(os.listdir(target))
        print('contents    : %d entries: %s' % (len(listing), ', '.join(listing[:12])))
    reports = find_reports(target)
    failures = 0
    for fp, report in reports:
        url = report.get('finalUrl') or report.get('requestedUrl') or '?'
        for key, audit in sorted(report['audits'].items()):
            score = audit.get('score')
            if score is None or score >= 1:
                continue
            failures += 1
            print('FAIL %s | %s | score=%s | %s' % (os.path.basename(fp), key, score, url))
            for item in ((audit.get('details') or {}).get('items') or [])[:6]:
                node = item.get('node') or {}
                print('   node: %s | %s' % (node.get('target') or node.get('selector'),
                                            (node.get('explanation') or node.get('failureSummary') or '')[:220]))
                # Shape varies by Lighthouse version, and guessing it cost three rounds: dump the
                # item verbatim (capped) so the element is identifiable whatever the schema is.
                print('   item: %s' % json.dumps(item, ensure_ascii=False)[:600])
    print('reports inspected: %d | failing audits reported: %d' % (len(reports), failures))
    if not reports:
        print('DIAGNOSTIC FAILED: no Lighthouse result json under %s' % target)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
