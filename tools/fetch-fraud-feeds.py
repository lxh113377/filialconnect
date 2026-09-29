#!/usr/bin/env python3
"""Refresh the offline scam-domain list from destroylist (MIT).

Writes assets/data/destroylist-domains.txt + fraud-feeds-meta.json.
The scheduled job fires weekly, so freshness has a deadline instead of a fuse:
refresh_due_by_utc is stamped when the snapshot is written, and --check (a blocking
CI step) goes red the day after that deadline passes. A dead cron used to take thirty
days to show up, which is four missed refreshes of a list whose whole value is being
current.

Offline audit (no network):  python tools/fetch-fraud-feeds.py --check
Self-test (temp fixtures, never opens the real snapshot):  --selftest
"""
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'assets', 'data')
SNAPSHOT = os.path.join(DATA_DIR, 'destroylist-domains.txt')
META = os.path.join(DATA_DIR, 'fraud-feeds-meta.json')
# The schedule itself belongs to .github/workflows/refresh-fraud-feeds.yml (cron 30 4 * * 1).
# These two numbers are this tool's reading of it: one cadence, plus a grace wide enough to
# let a single missed run pass before CI turns red.
REFRESH_CADENCE_DAYS = 7
STALE_GRACE_DAYS = 3
# A feed that moves outside this band is not a refresh, it is an upstream accident or a
# truncated download, so the writer refuses before it can overwrite the good snapshot.
COUNT_BAND = (0.90, 1.15)
MIN_DOMAINS = 10000
OWNER_REPO = 'phishdestroy/destroylist'
FEED_PATH = 'rootlist/online_root_domains.txt'
LICENSE = 'MIT'
UA = {'User-Agent': 'FilialConnect-feed-refresh'}
DOMAIN_RE = re.compile(r'^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$')
TIME_FMT = '%Y-%m-%dT%H:%M:%SZ'
VERDICT = ('FRAUD-SNAPSHOT: state=%s age_days=%d due_utc=%s due_origin=%s domains=%d '
           'cadence=%d+%d detail=%s')
# The whole vocabulary this tool may print, owned here so a document that names a state can be
# checked against the code instead against someone's memory of it.
STATES = ('fresh', 'late', 'overdue', 'digest-mismatch', 'count-mismatch', 'absent', 'unreadable')


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=60).read()


def sha256_of(path):
    return hashlib.sha256(io.open(path, 'rb').read()).hexdigest()


def parse_utc(text):
    return datetime.strptime(text, TIME_FMT).replace(tzinfo=timezone.utc)


def fmt_utc(when):
    return when.strftime(TIME_FMT)


def deadline_from(fetched):
    return fetched + timedelta(days=REFRESH_CADENCE_DAYS + STALE_GRACE_DAYS)


def face(state, age, due, origin, domains, detail):
    return VERDICT % (state, age, due, origin, domains, REFRESH_CADENCE_DAYS,
                      STALE_GRACE_DAYS, detail)


def snapshot_state(fetched, due, now, domains, expected, actual, meta_digest):
    """Pure verdict for one snapshot: (state, rc, detail). Never folds two states.

    due_origin belongs to the verdict because snapshots written before that field existed
    carry a *derived* deadline: honouring a stamped one and computing one are different
    claims, and a reader that cannot tell them apart cannot tell whether the deadline was
    ever agreed to.
    """
    if meta_digest is not None and actual != meta_digest:
        return 'digest-mismatch', 1, 'snapshot=%s meta=%s' % (actual[:12], meta_digest[:12])
    if domains != expected:
        return 'count-mismatch', 1, 'snapshot=%d meta=%d' % (domains, expected)
    age = (now - fetched).days
    origin = 'stamped' if due is not None else 'derived'
    due_at = due if due is not None else deadline_from(fetched)
    if now > due_at:
        return 'overdue', 1, 'past %s (%s) by %d day(s): the scheduled refresh is not landing' % (
            fmt_utc(due_at), origin, (now - due_at).days)
    if age > REFRESH_CADENCE_DAYS:
        return 'late', 0, '%d day(s) of grace left before %s' % ((due_at - now).days, fmt_utc(due_at))
    return 'fresh', 0, 'due %s (%s)' % (fmt_utc(due_at), origin)


def band_ok(old_count, new_count):
    """Pure guard for the write path: a refresh has to stay inside the declared band."""
    if old_count <= 0:
        return True, 'no previous count to compare'
    ratio = float(new_count) / old_count
    if COUNT_BAND[0] <= ratio <= COUNT_BAND[1]:
        return True, 'ratio %.3f within %.2f-%.2f' % (ratio, COUNT_BAND[0], COUNT_BAND[1])
    return False, 'ratio %.3f outside %.2f-%.2f (old=%d new=%d)' % (
        ratio, COUNT_BAND[0], COUNT_BAND[1], old_count, new_count)


def read_meta(path):
    if not os.path.exists(path):
        return {}
    try:
        return json.load(io.open(path, encoding='utf-8'))
    except (ValueError, OSError):
        return {}


def check(data_dir=None, now=None):
    """Audit the committed snapshot with no network, and print exactly one verdict line."""
    data_dir = data_dir or DATA_DIR
    snap = os.path.join(data_dir, 'destroylist-domains.txt')
    meta = read_meta(os.path.join(data_dir, 'fraud-feeds-meta.json'))
    if not meta or not os.path.exists(snap):
        print(face('absent', 0, '-', '-', 0, 'no snapshot or no meta under %s' % data_dir))
        return 1
    now = now or datetime.now(timezone.utc)
    payload = io.open(snap, 'rb').read()
    actual = hashlib.sha256(payload).hexdigest()
    lines = [l for l in payload.decode('utf-8').splitlines() if l.strip()]
    try:
        fetched = parse_utc(meta['fetched_utc'])
    except (KeyError, ValueError):
        print(face('unreadable', 0, '-', '-', len(lines), 'fetched_utc missing or malformed'))
        return 1
    due = None
    if meta.get('refresh_due_by_utc'):
        try:
            due = parse_utc(meta['refresh_due_by_utc'])
        except ValueError:
            due = None
    state, rc, detail = snapshot_state(fetched, due, now, len(lines),
                                       meta.get('domains', -1), actual,
                                       meta.get('snapshot_sha256'))
    print(face(state, (now - fetched).days,
               fmt_utc(due if due is not None else deadline_from(fetched)),
               'stamped' if due is not None else 'derived', len(lines), detail))
    return rc


def plan_write(old_meta, domains):
    """Refuse-before-write: (ok, detail) for a candidate snapshot."""
    if len(domains) < MIN_DOMAINS:
        return False, 'suspiciously small feed (%d < %d), existing data left untouched' % (
            len(domains), MIN_DOMAINS)
    return band_ok(int(old_meta.get('domains') or 0), len(domains))


def main(data_dir=None):
    data_dir = data_dir or DATA_DIR
    snap = os.path.join(data_dir, 'destroylist-domains.txt')
    meta_path = os.path.join(data_dir, 'fraud-feeds-meta.json')
    info = json.loads(fetch('https://api.github.com/repos/' + OWNER_REPO).decode('utf-8'))
    branch = info['default_branch']
    # /repos/{o}/{r} carries no head commit; ask the branch explicitly so the
    # snapshot is attributable to an upstream revision.
    head = json.loads(fetch('https://api.github.com/repos/%s/commits/%s' % (
        OWNER_REPO, branch)).decode('utf-8'))
    raw = fetch('https://raw.githubusercontent.com/%s/%s/%s' % (
        OWNER_REPO, branch, FEED_PATH)).decode('utf-8')
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
    ok, why = plan_write(read_meta(meta_path), domains)
    if not ok:
        # The refusal names its guard: a bare non-zero exit reads as a network failure,
        # and the next round would re-run the fetch instead of looking upstream.
        sys.exit('REFUSED: not writing the snapshot - %s' % why)
    now = datetime.now(timezone.utc)
    os.makedirs(data_dir, exist_ok=True)
    io.open(snap, 'w', encoding='utf-8', newline='\n').write('\n'.join(domains) + '\n')
    meta = {'source': 'https://github.com/' + OWNER_REPO, 'license': LICENSE,
            'feed': FEED_PATH, 'branch': branch, 'commit': head.get('sha', ''),
            'fetched_utc': fmt_utc(now),
            'refresh_due_by_utc': fmt_utc(deadline_from(now)),
            'refresh_cadence_days': REFRESH_CADENCE_DAYS,
            'refresh_grace_days': STALE_GRACE_DAYS,
            'domains': len(domains), 'malformed_skipped': bad,
            'coverage_note': 'international phishing roots only; mainland-China domains counted below',
            'mainland_cn_domains': sum(1 for d in domains if d.endswith('.cn') or d.endswith('.com.cn')),
            'snapshot_sha256': sha256_of(snap),
            'raw_upstream_sha256': hashlib.sha256(raw.encode('utf-8')).hexdigest()}
    json.dump(meta, io.open(meta_path, 'w', encoding='utf-8', newline='\n'), indent=2)
    print('refreshed: %d domains (%d malformed skipped, %d mainland-CN), due %s' % (
        len(domains), bad, meta['mainland_cn_domains'], meta['refresh_due_by_utc']))
    return 0


def decide(argv):
    """Powerless argv predicate: a typo must never reach the writing path."""
    if not argv:
        return 'fetch', []
    if argv == ['--check']:
        return 'check', argv
    if argv == ['--selftest']:
        return 'selftest', argv
    if argv[0] in ('-h', '--help'):
        return 'help', argv
    return 'refuse', argv


def _fixture(dirpath, domains, fetched, due=None, digest=None, count=None):
    body = '\n'.join('d%d.example.com' % i for i in range(domains)) + '\n'
    io.open(os.path.join(dirpath, 'destroylist-domains.txt'), 'w', encoding='utf-8',
            newline='\n').write(body)
    meta = {'fetched_utc': fmt_utc(fetched),
            'domains': domains if count is None else count,
            'snapshot_sha256': digest if digest is not None
            else hashlib.sha256(body.encode('utf-8')).hexdigest()}
    if due is not None:
        meta['refresh_due_by_utc'] = fmt_utc(due)
    json.dump(meta, io.open(os.path.join(dirpath, 'fraud-feeds-meta.json'), 'w',
                            encoding='utf-8', newline='\n'), indent=2)
    return meta


def _run_check(data_dir, now):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = check(data_dir, now=now)
    return rc, buf.getvalue()


def selftest():
    """Both directions, on temp fixtures only. The real snapshot is never opened."""
    now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
    n = MIN_DOMAINS + 5
    results = []
    tmp = tempfile.mkdtemp(prefix='fraud-selftest-')
    try:
        wants = [
            ('fresh', 0, ['state=fresh', 'due_origin=derived'],
             dict(domains=n, fetched=now - timedelta(days=2))),
            ('late', 0, ['state=late', 'of grace left'],
             dict(domains=n, fetched=now - timedelta(days=8))),
            ('overdue', 1, ['state=overdue', 'scheduled refresh is not landing'],
             dict(domains=n, fetched=now - timedelta(days=11))),
            # A 30-day-old snapshot with a stamped deadline two days out is late, not
            # overdue: the writer's own number outranks the derived one in both directions.
            ('stamped', 0, ['state=late', 'due_origin=stamped'],
             dict(domains=n, fetched=now - timedelta(days=30), due=now + timedelta(days=1))),
            ('digest', 1, ['state=digest-mismatch'],
             dict(domains=n, fetched=now - timedelta(days=1), digest='ff' * 32)),
            ('count', 1, ['state=count-mismatch'],
             dict(domains=n, fetched=now - timedelta(days=1), count=n + 1)),
            # The mirror case: two days old would read fresh under the derived deadline,
            # so only a stamped one can make it overdue - proof the stamped number wins
            # in both directions, not just that it exists.
            ('stamped-past', 1, ['state=overdue', 'due_origin=stamped'],
             dict(domains=n, fetched=now - timedelta(days=2), due=now - timedelta(days=1))),
        ]
        for name, want_rc, needles, kw in wants:
            d = os.path.join(tmp, name)
            os.makedirs(d)
            _fixture(d, **kw)
            rc, out = _run_check(d, now)
            results.append(('a %s fixture reads %s and rc=%d' % (name, needles[0], want_rc),
                            rc == want_rc and all(x in out for x in needles),
                            'rc=%d line=%s' % (rc, out.strip()[:150])))
        d = os.path.join(tmp, 'absent')
        os.makedirs(d)
        rc, out = _run_check(d, now)
        results.append(('an empty data dir is absent and red, never zero problems',
                        rc == 1 and 'state=absent' in out, 'rc=%d line=%s' % (rc, out.strip()[:150])))
        d = os.path.join(tmp, 'unreadable')
        os.makedirs(d)
        bad_meta = _fixture(d, n, now)
        bad_meta['fetched_utc'] = 'last tuesday'
        json.dump(bad_meta, io.open(os.path.join(d, 'fraud-feeds-meta.json'), 'w',
                                    encoding='utf-8', newline='\n'))
        rc, out = _run_check(d, now)
        results.append(('a malformed fetched_utc is unreadable and red, not a silent pass',
                        rc == 1 and 'state=unreadable' in out, 'rc=%d line=%s' % (rc, out.strip()[:150])))
    finally:
        shutil.rmtree(tmp)

    ok, why = band_ok(83097, 83100)
    results.append(('the band accepts an ordinary weekly refresh', ok, why))
    ok, why = band_ok(83097, 120000)
    results.append(('a 44 percent jump is refused by name before any write',
                    not ok and 'outside' in why, why))
    ok, why = band_ok(0, 10)
    results.append(('no previous count does not block a first snapshot', ok, why))
    ok, why = plan_write({'domains': 83097}, ['a.example.com'] * 50)
    results.append(('a truncated feed hits the floor as well as the band',
                    not ok and 'suspiciously small' in why, why))
    for argv, want in (([], 'fetch'), (['--check'], 'check'),
                       (['--selftest'], 'selftest'), (['--help'], 'help')):
        got, _ = decide(argv)
        results.append(('argv %s routes to %s' % (' '.join(argv) or '(none)', want),
                        got == want, got))
    action, arg = decide(['--sefltest'])
    results.append(('a misspelled flag refuses instead of fetching and overwriting',
                    action == 'refuse' and arg == ['--sefltest'], str((action, arg))))

    failed = 0
    for label, good, detail in results:
        if not good:
            failed += 1
            print('  ASSERT-FAIL[%s]: %s' % (label, detail))
    print('fetch-fraud-feeds selftest: %d cases, %d failures' % (len(results), failed))
    return 0 if failed == 0 else 1


HELP = __doc__

if __name__ == '__main__':
    action, arg = decide(sys.argv[1:])
    if action == 'check':
        sys.exit(check())
    if action == 'selftest':
        sys.exit(selftest())
    if action == 'help':
        print(HELP)
        sys.exit(0)
    if action == 'refuse':
        sys.stderr.write('REFUSED: unknown argument %r - this tool writes the offline '
                         'scam-domain snapshot, so nothing outside --check / --selftest / '
                         '--help may reach it\n' % arg[0])
        sys.exit(2)
    sys.exit(main())
