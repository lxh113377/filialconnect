#!/usr/bin/env python3
"""Stamp each generated tutorial page with the date its own content last changed.

Why not the obvious version ("ask git at build time"): `actions/checkout` defaults to
fetch-depth 1, so in CI every file's last commit date collapses to the build day. Measured in
round 13 - a page with 12 real commits shows as 1 commit dated today. A date rendered there would
claim the whole site was updated today, on a site whose promise is trustworthiness.

So the dates are computed here, locally, where full history exists, and committed as
reports/last-updated.json. Each entry is keyed by the sha256 of that tutorial's own content
object: edit one tutorial and only that one gets a fresh date. CI then verifies without git -
recompute the hash and compare - which makes a stale stamp a build failure rather than a slow lie.

Usage:
  python tools/last-updated.py           # report what would change
  python tools/last-updated.py --write   # update the ledger
"""
import hashlib
import io
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = 'reports/last-updated.json'
CONTENT = 'content/tutorials.json'
WRITE = '--write' in sys.argv
REHASH = '--rehash' in sys.argv


def rehash(tuts, ledger):
    """Adopt a new hash basis **without** moving a single date.

    Changing what the hash covers is a tool change, not a content change. Under the old rule the
    whole object was hashed, so adding the library-card fields would have republished all six
    guides as "updated today" while their visible text sat still - the exact false freshness this
    ledger exists to avoid. Refuses to invent an entry, and prints every date it kept.
    """
    fresh = {}
    for t in tuts:
        page = 'pages/' + t['file']
        old = ledger.get(page)
        if not old:
            sys.exit('FAIL: --rehash refuses to invent a stamp for %s (run --write for that)' % page)
        fresh[page] = {'hash': entry_hash(t), 'date': old['date']}
    for page in sorted(fresh):
        print('  %s  %s  date kept' % (page, fresh[page]['date']))
    gone = sorted(set(ledger) - set(fresh))
    if gone:
        print('  dropped (page gone): %s' % gone)
    io.open(os.path.join(ROOT, LEDGER), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(fresh, indent=2, sort_keys=True) + '\n')
    print('REHASH wrote %s: %d stamps, dates unchanged, %d hashes moved'
          % (LEDGER, len(fresh), sum(1 for p in fresh if ledger.get(p, {}).get('hash') != fresh[p]['hash'])))
    return 0


def read(fp):
    return io.open(os.path.join(ROOT, fp), encoding='utf-8').read()


PAGE_VISIBLE_FIELDS = ('title', 'desc', 'h1', 'intro', 'steps', 'related', 'img_alt',
                       'illustration')


def entry_hash(tut):
    """Content identity of one tutorial: the fields that render into its own page, key-sorted.

    Deliberately excludes anything shared (template, nav) - the question asked of this stamp is
    "did this guide's own text move", not "did the site build".

    Round 34 narrowed it further. Field-ordering the whole object used to mean that adding a
    grid-only field (`card_p` / `card_tags`, which appear on the library page, not on the guide)
    moved the stamp of all six guides - six readers would have been told "updated today" about
    pages whose visible text had not moved, on a site whose selling point is trust. Identity
    fields (`slug`, `file`) are excluded too: renaming one already produces a different page.
    """
    visible = {k: tut[k] for k in PAGE_VISIBLE_FIELDS if k in tut}
    blob = json.dumps(visible, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()[:16]


def git_date(fp):
    r = subprocess.run(['git', 'log', '-1', '--format=%cd', '--date=short', '--', fp],
                       cwd=ROOT, capture_output=True, text=True)
    out = (r.stdout or '').strip()
    return out if r.returncode == 0 and out else None


def load_ledger():
    if not os.path.exists(os.path.join(ROOT, LEDGER)):
        return {}
    return json.loads(read(LEDGER))


def main():
    tuts = json.loads(read(CONTENT))['tutorials']
    ledger = load_ledger()
    if REHASH:
        return rehash(tuts, ledger)
    source_date = git_date(CONTENT) or 'unknown'
    changed, rows = [], []
    fresh = {}
    for t in tuts:
        page = 'pages/' + t['file']
        h = entry_hash(t)
        old = ledger.get(page) or {}
        date = old.get('date') if old.get('hash') == h else source_date
        if old.get('hash') != h or old.get('date') != date:
            changed.append(page)
        fresh[page] = {'hash': h, 'date': date}
        rows.append('%s  %s  %s' % (page, date, 'unchanged' if old.get('hash') == h else 'refreshed'))
    dropped = sorted(set(ledger) - set(fresh))
    print('content source date : %s (from git, full history, computed locally)' % source_date)
    for r in sorted(rows):
        print('  ' + r)
    if dropped:
        print('  dropped (page gone): %s' % ', '.join(dropped))
    print('%s %d of %d stamped, %d changed' % ('WRITE' if WRITE else 'dry run:',
                                                len(fresh), len(tuts), len(changed)))
    if WRITE:
        out = json.dumps(fresh, indent=2, sort_keys=True) + '\n'
        os.makedirs(os.path.join(ROOT, 'reports'), exist_ok=True)
        io.open(os.path.join(ROOT, LEDGER), 'w', encoding='utf-8', newline='\n').write(out)
        print('wrote %s' % LEDGER)
    return 0


if __name__ == '__main__':
    sys.exit(main())
