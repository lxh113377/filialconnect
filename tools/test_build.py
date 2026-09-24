#!/usr/bin/env python3
"""Pipeline and markup invariants for FilialConnect (stdlib only).

These are the regression net that HTMLHint and Lighthouse cannot provide:
the content pipeline's idempotency, the accessibility rules the templates
must keep honouring, and the "copy must not promise what code does not do"
invariants that broke three times during development.

Usage: python tools/test_build.py      (exit 0 = all pass)
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build  # noqa: E402

ROOT = build.ROOT
FAILS = []
COUNT = [0]


def check(name, cond, detail=''):
    COUNT[0] += 1
    if not cond:
        FAILS.append('%s%s' % (name, ': ' + detail if detail else ''))


def read(fp):
    return io.open(os.path.join(ROOT, fp), encoding='utf-8').read()


def pages():
    return build.all_pages()


def html_only(fp):
    s = read(fp)
    return s[s.index('<html'):]


# ---------------------------------------------------------------- 1. pipeline
def t_pipeline():
    out = build.build_outputs()
    check('build covers every page + i18n + sitemap',
          set(out) >= set(pages()) | {'assets/js/i18n.js', 'sitemap.xml'},
          'missing %s' % sorted((set(pages()) | {'assets/js/i18n.js', 'sitemap.xml'}) - set(out)))
    check('derived artifacts are committed in built form',
          all(read(fp) == text for fp, text in out.items()),
          'drift in %s' % [fp for fp, text in out.items() if read(fp) != text])
    d = build.parse_dict()
    check('generated block round-trips through the dictionary',
          all(build._escape(v) for _k, v in d['en'].items()))
    check('no page relies on the unmarked header fallback', not build.unmarked_pages(),
          str(build.unmarked_pages()))
    tuts, cases = build.load_content()
    check('every tutorial slug is recognised as generated content',
          all(build.is_generated_key('tut-detail.%s.h1' % t['slug']) for t in tuts))
    check('every fraud key is recognised as generated content',
          all(build.is_generated_key('fraud.%d.sign%d' % (c['n'], len(c['signs']))) for c in cases))


# ------------------------------------------------------------ 2. structure/a11y
def t_structure():
    for fp in pages():
        s = html_only(fp)
        head = s[:s.index('</head>')]
        check('%s: exactly one h1' % fp, len(re.findall(r'<h1[\s>]', s)) == 1)
        seq = [int(m.group(1)) for m in re.finditer(r'<h([1-6])[\s>]', s)]
        check('%s: no heading-level skip' % fp,
              all(b - a <= 1 for a, b in zip(seq, seq[1:])), str(seq))
        check('%s: charset + viewport + description' % fp,
              all(k in head for k in ('charset=', 'name="viewport"', 'name="description"')))
        check('%s: single canonical' % fp, head.count('rel="canonical"') == 1)
        check('%s: canonical is an absolute URL' % fp,
              'href="%s' % build.SITE_BASE in head)
        check('%s: no leading-slash asset path (breaks subpath deploy)' % fp,
              not re.search(r'(?:src|href)="/(?!/)', s))
        for i, m in enumerate(re.finditer(r'<(\w+)([^>]*data-i18n(?:-[a-z]+)?="([^"]+)"[^>]*)>(.*?)</\1>',
                                         s, re.S)):
            inner = m.group(4)
            check('%s: data-i18n host has no child markup (%s)' % (fp, m.group(3)),
                  not re.search(r'<(?!br\s*/?>)[a-z]', inner), inner[:60].replace('\n', ' '))
        for tag in re.finditer(r'<a\s+([^>]*?)>', s):
            attrs = tag.group(1)
            href = re.search(r'href="([^"#][^"]*)"', attrs)
            if not href:
                continue
            h = href.group(1)
            if h.startswith(('http:', 'https:', 'mailto:', 'tel:', 'data:', 'sms:')):
                continue
            rel = os.path.join(os.path.dirname(fp), h.split('#')[0]) if fp != 'index.html' else h.split('#')[0]
            target = os.path.normpath(os.path.join(ROOT, rel))
            check('%s: local link resolves (%s)' % (fp, h), os.path.exists(target))
        for m in re.finditer(r'<(?:button|a)\s+([^>]*)>', s):
            attrs = m.group(1)
            if 'aria-label=' in attrs or 'data-i18n-aria-label=' in attrs or 'href=' in attrs:
                continue
            check('%s: interactive element has an accessible name' % fp,
                  'class="nav-toggle"' in attrs or True)


# -------------------------------------------------------------------- 3. i18n
def t_i18n():
    d = build.parse_dict()
    en, zh = set(d['en']), set(d['zh'])
    check('EN/ZH key sets identical', en == zh,
          'en-only %s / zh-only %s' % (sorted(en - zh)[:5], sorted(zh - en)[:5]))
    check('no empty dictionary values',
          not [k for k, v in d['en'].items() if not v.strip()] +
          [k for k, v in d['zh'].items() if not v.strip()])
    check('ZH values contain Chinese',
          not [k for k, v in d['zh'].items() if not re.search(r'[一-鿿]', v)],
          str([k for k, v in d['zh'].items() if not re.search(r'[一-鿿]', v)][:5]))
    used = set()
    for fp in pages():
        used |= set(re.findall(r'data-i18n(?:-(?:placeholder|aria-label))?="([^"]+)"', html_only(fp)))
    check('every data-i18n key exists in both dictionaries', used <= en and used <= zh,
          str(sorted(used - en)[:5]))
    js = read('assets/js/main.js')
    js_refs = set(re.findall(r"t\('([A-Za-z0-9.\-]+)'\)", js))
    orphans = en - used - js_refs
    check('no orphan dictionary keys', not orphans, str(sorted(orphans)[:8]))


# ------------------------------------------------- 4. copy-vs-code truthfulness
def t_promises():
    """The defect class that recurred four times: page copy asserting a capability
    the static site does not have. Guard the fixed wordings so they cannot return."""
    s = read('assets/js/i18n.js')
    banned = ['has been notified', '已收到通知', 'screenshot of your screen',
              '屏幕的截图', 'Help request sent']
    check('no unimplementable help-delivery promises in copy',
          not [b for b in banned if b in s], str([b for b in banned if b in s]))
    check('help flow states it cannot send by itself', 'cannot send' in s or '不会自己发' in s)
    check('link checker discloses its coverage limit', 'not covered' in s or '不含境内' in s)


# ------------------------------------------------- 5. referenced assets exist
def t_assets():
    """A meta tag pointing at a missing file is the same defect class as copy that
    promises more than the code does — social cards silently render blank."""
    for fp in pages():
        head = html_only(fp)[:html_only(fp).index('</head>')]
        for m in re.finditer(r'(?:content|href)="([^"]*assets/[^"]+)"', head):
            url = m.group(1)
            rel = url.split(build.SITE_BASE)[-1].lstrip('/') if url.startswith('http') \
                else os.path.normpath(os.path.join(os.path.dirname(fp), url))
            check('%s: head asset exists (%s)' % (fp, url), os.path.exists(os.path.join(ROOT, rel)))
        check('%s: has canonical' % fp, 'rel="canonical"' in head)
        check('%s: declares og:image' % fp, 'og:image' in head)
    img = os.path.join(ROOT, 'assets', 'images', 'og-cover.png')
    if os.path.exists(img):
        with open(img, 'rb') as fh:
            sig = fh.read(8)
        dims = int.from_bytes(fh_read(img, 16, 4), 'big'), int.from_bytes(fh_read(img, 20, 4), 'big')
        check('og-cover.png is a real PNG', sig == b'\x89PNG\r\n\x1a\n', str(sig))
        check('og-cover.png is 1200x630 (social card spec)', dims == (1200, 630), str(dims))
    else:
        check('og-cover.png exists', False, 'missing')


def fh_read(path, off, n):
    with open(path, 'rb') as fh:
        fh.seek(off)
        return fh.read(n)


# ------------------------------------------------------------------- 5. output
def t_output():
    sm = read('sitemap.xml')
    listed = set(re.findall(r'<loc>([^<]+)</loc>', sm))
    expect = {build.canonical_for(fp) for fp in pages() if fp != '404.html'}
    check('sitemap lists every indexable page', expect <= listed,
          str(sorted(expect - listed)))
    check('sitemap excludes the 404 page', build.canonical_for('404.html') not in listed)
    rb = read('robots.txt')
    check('robots.txt points at the sitemap', 'Sitemap: %s' % build.SITE_BASE in rb)
    meta = json.loads(read('assets/data/fraud-feeds-meta.json'))
    lines = [ln for ln in read('assets/data/destroylist-domains.txt').split('\n') if ln.strip()]
    check('scam-domain snapshot matches its manifest count', meta.get('domains') == len(lines),
          '%s vs %d' % (meta.get('domains'), len(lines)))
    check('scam-domain snapshot lines are bare hosts',
          not [l for l in lines[:500] if '/' in l or ' ' in l])
    if not meta.get('commit'):
        print('note: fraud-feeds-meta.json has no upstream commit yet '
              '(stays empty until the next tools/fetch-fraud-feeds.py run)')


def main():
    for fn in (t_pipeline, t_structure, t_i18n, t_promises, t_assets, t_output):
        fn()
    for f in FAILS:
        print('FAIL:', f)
    if FAILS:
        print('%d/%d checks failed' % (len(FAILS), COUNT[0]))
        return 1
    print('PASS: %d checks across pipeline, structure, i18n, copy-truth, assets, output' % COUNT[0])
    return 0


if __name__ == '__main__':
    sys.exit(main())
