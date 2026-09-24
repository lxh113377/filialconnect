#!/usr/bin/env python3
"""Refresh the offline scam-domain list from destroylist (MIT).

Writes assets/data/destroylist-domains.txt + fraud-feeds-meta.json.
Run weekly:  python tools/fetch-fraud-feeds.py
Exits non-zero on network failure (leaves old data untouched).
"""
import io
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OWNER_REPO = 'phishdestroy/destroylist'
FEED_PATH = 'rootlist/online_root_domains.txt'
LICENSE = 'MIT'
UA = {'User-Agent': 'FilialConnect-feed-refresh'}
DOMAIN_RE = re.compile(r'^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$')


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=60).read()


def main():
    info = json.loads(fetch('https://api.github.com/repos/' + OWNER_REPO).decode('utf-8'))
    branch = info['default_branch']
    # /repos/{o}/{r} carries no head commit; ask the branch explicitly so the
    # snapshot is attributable to an upstream revision.
    head = json.loads(fetch('https://api.github.com/repos/%s/commits/%s' % (OWNER_REPO, branch)).decode('utf-8'))
    sha = head.get('sha', '')
    raw = fetch('https://raw.githubusercontent.com/%s/%s/%s' % (OWNER_REPO, branch, FEED_PATH)).decode('utf-8')
    seen, bad = set(), 0
    for line in raw.splitlines():
        d = line.strip().lower()
        if not d or d.startswith('#'):
            continue
        if DOMAIN_RE.match(d):
            seen.add(d)
        else:
            bad += 1
    domains = sorted(seen)
    if len(domains) < 10000:
        sys.exit('FAIL: suspiciously small feed (%d), aborting to protect existing data' % len(domains))
    cn = sum(1 for d in domains if d.endswith('.cn') or d.endswith('.com.cn'))
    out = os.path.join(ROOT, 'assets', 'data')
    os.makedirs(out, exist_ok=True)
    io.open(os.path.join(out, 'destroylist-domains.txt'), 'w', encoding='utf-8', newline='\n').write('\n'.join(domains) + '\n')
    meta = {'source': 'https://github.com/' + OWNER_REPO, 'license': LICENSE,
            'feed': FEED_PATH, 'branch': branch, 'commit': sha,
            'fetched_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'domains': len(domains), 'malformed_skipped': bad,
            'coverage_note': 'international phishing roots only; mainland-China domains counted below',
            'mainland_cn_domains': cn}
    json.dump(meta, io.open(os.path.join(out, 'fraud-feeds-meta.json'), 'w', encoding='utf-8', newline='\n'), indent=2)
    print('refreshed: %d domains (%d malformed skipped, %d mainland-CN)' % (len(domains), bad, cn))


if __name__ == '__main__':
    main()
