#!/usr/bin/env python3
"""Refresh the offline scam-domain list from destroylist (MIT).

Writes assets/data/destroylist-domains.txt + fraud-feeds-meta.json.
Run weekly:  python tools/fetch-fraud-feeds.py
Exits non-zero on network failure (leaves old data untouched).

Offline audit (no network):  python tools/fetch-fraud-feeds.py --check
Verifies the committed snapshot against its recorded digest and fails when the
snapshot is older than STALE_MAX_DAYS, so a dead cron shows up as red CI.
"""
import hashlib
import io
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'assets', 'data')
SNAPSHOT = os.path.join(DATA_DIR, 'destroylist-domains.txt')
META = os.path.join(DATA_DIR, 'fraud-feeds-meta.json')
STALE_MAX_DAYS = 30
OWNER_REPO = 'phishdestroy/destroylist'
FEED_PATH = 'rootlist/online_root_domains.txt'
LICENSE = 'MIT'
UA = {'User-Agent': 'FilialConnect-feed-refresh'}
DOMAIN_RE = re.compile(r'^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$')


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=60).read()


def sha256_of(path):
    return hashlib.sha256(io.open(path, 'rb').read()).hexdigest()


def check():
    """Audit the committed snapshot without touching the network."""
    meta = json.load(io.open(META, encoding='utf-8'))
    payload = io.open(SNAPSHOT, 'rb').read()
    actual = hashlib.sha256(payload).hexdigest()
    lines = [l for l in payload.decode('utf-8').splitlines() if l.strip()]
    problems = []
    if actual != meta.get('snapshot_sha256'):
        problems.append('digest mismatch: snapshot=%s meta=%s' % (actual, meta.get('snapshot_sha256')))
    if len(lines) != meta.get('domains'):
        problems.append('count mismatch: snapshot=%d meta=%d' % (len(lines), meta.get('domains')))
    fetched = datetime.strptime(meta['fetched_utc'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - fetched).days
    if age_days > STALE_MAX_DAYS:
        problems.append('snapshot is %d days old (> %d); scheduled refresh may be broken' % (age_days, STALE_MAX_DAYS))
    if problems:
        for p in problems:
            print('FAIL: ' + p)
        return 1
    print('OK: %d domains, digest matches meta, %d days old (limit %d)' % (len(lines), age_days, STALE_MAX_DAYS))
    return 0


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
    os.makedirs(DATA_DIR, exist_ok=True)
    io.open(SNAPSHOT, 'w', encoding='utf-8', newline='\n').write('\n'.join(domains) + '\n')
    meta = {'source': 'https://github.com/' + OWNER_REPO, 'license': LICENSE,
            'feed': FEED_PATH, 'branch': branch, 'commit': sha,
            'fetched_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'domains': len(domains), 'malformed_skipped': bad,
            'coverage_note': 'international phishing roots only; mainland-China domains counted below',
            'mainland_cn_domains': cn,
            'snapshot_sha256': sha256_of(SNAPSHOT),
            'raw_upstream_sha256': hashlib.sha256(raw.encode('utf-8')).hexdigest()}
    json.dump(meta, io.open(META, 'w', encoding='utf-8', newline='\n'), indent=2)
    print('refreshed: %d domains (%d malformed skipped, %d mainland-CN)' % (len(domains), bad, cn))


if __name__ == '__main__':
    if '--check' in sys.argv:
        sys.exit(check())
    main()
