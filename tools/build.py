#!/usr/bin/env python3
"""FilialConnect content pipeline (D1-A, zero-dependency build).

Single source: content/tutorials.json + content/fraud-cases.json (+ templates
in this file). Derived, committed artifacts:
  - pages/tutorial-*.html          (full-page generation)
  - assets/js/i18n.js              (generated key block per language)
  - nav (<header>) / footer on all 12 pages (partial sync)
  - pages/fraud-database.html items block (between FRAUD-ITEMS markers)

Commands:
  python tools/build.py extract        one-off bootstrap of content JSON + markers
  python tools/build.py build          regenerate derived artifacts
  python tools/build.py check          rebuild in memory; exit 1 on drift (CI gate)
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, 'content')
SLUGS = ['hospital', 'train', 'wechat', 'medical', 'banking', 'ride']

TUT_KEY_RE = re.compile(r"^tut-detail\.(%s)\.(h1|p|step\d+\.title|step\d+\.p|related\d+)$" % '|'.join(SLUGS))
FRAUD_KEY_RE = re.compile(r"^fraud\.([1-5])\.(title|how|how\.p|signs|sign[1-4]|do|do[1-3])$")

I18N_BEGIN = '    // BEGIN:GENERATED (tools/build.py) - edit content/*.json instead'
I18N_END = '    // END:GENERATED'
FRAUD_MARK_BEG = '      <!-- BEGIN:FRAUD-ITEMS (tools/build.py) -->'
FRAUD_MARK_END = '      <!-- END:FRAUD-ITEMS -->'

LINE_RE = re.compile(r"^    '([^']+)':\s*'((?:[^'\\]|\\.)*)',?\s*$")


def _unescape(v):
    out, i = [], 0
    while i < len(v):
        c = v[i]
        if c == '\\' and i + 1 < len(v):
            n = v[i + 1]
            if n == 'u':
                out.append(chr(int(v[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append(n)
            i += 2
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def _escape(v):
    return v.replace('\\', '\\\\').replace("'", "\\'")


def read(fp):
    return io.open(os.path.join(ROOT, fp), encoding='utf-8').read()


def write(fp, text):
    io.open(os.path.join(ROOT, fp), 'w', encoding='utf-8', newline='\n').write(text)


def parse_dict():
    """{'en': {k: v}, 'zh': {...}} from the current i18n.js (incl. generated)."""
    d = {'en': {}, 'zh': {}}
    cur = None
    for ln in read('assets/js/i18n.js').split('\n'):
        m = re.match(r"^  (en|zh):\s*\{", ln)
        if m:
            cur = m.group(1)
            continue
        if cur and re.match(r"^  \},?\s*$", ln):
            cur = None
            continue
        if cur:
            mk = LINE_RE.match(ln)
            if mk:
                d[cur][mk.group(1)] = _unescape(mk.group(2))
    return d


def is_generated_key(k):
    return bool(TUT_KEY_RE.match(k) or FRAUD_KEY_RE.match(k))


def gen_pairs(lang):
    """Ordered (key, value) list for one language from content JSON."""
    d = parse_dict() if not os.path.isdir(CONTENT) else None
    tuts = json.load(io.open(os.path.join(CONTENT, 'tutorials.json'), encoding='utf-8'))['tutorials']
    cases = json.load(io.open(os.path.join(CONTENT, 'fraud-cases.json'), encoding='utf-8'))['cases']
    L = []
    for t in tuts:
        s = t['slug']
        L.append(('tut-detail.%s.h1' % s, t['h1'][lang]))
        L.append(('tut-detail.%s.p' % s, t['intro'][lang]))
        for i, st in enumerate(t['steps'], 1):
            L.append(('tut-detail.%s.step%d.title' % (s, i), st['title'][lang]))
            L.append(('tut-detail.%s.step%d.p' % (s, i), st['p'][lang]))
        for i, r in enumerate(t['related'], 1):
            L.append(('tut-detail.%s.related%d' % (s, i), r['title'][lang]))
    for c in cases:
        n = c['n']
        L.append(('fraud.%d.title' % n, c['title'][lang]))
        L.append(('fraud.%d.how' % n, c['how'][lang]))
        L.append(('fraud.%d.how.p' % n, c['howp'][lang]))
        L.append(('fraud.%d.signs' % n, c['signs_h'][lang]))
        for i, x in enumerate(c['signs'], 1):
            L.append(('fraud.%d.sign%d' % (n, i), x[lang]))
        L.append(('fraud.%d.do' % n, c['do_h'][lang]))
        for i, x in enumerate(c['dos'], 1):
            L.append(('fraud.%d.do%d' % (n, i), x[lang]))
    return L


def render_i18n():
    src = read('assets/js/i18n.js')
    # drop existing generated block(s)
    src = re.sub(r'\n *// BEGIN:GENERATED.*?// END:GENERATED\n', '\n', src, flags=re.S)
    # drop any generated key lines left in the handwritten sections
    kept = [ln for ln in src.split('\n')
            if not (is_generated_key(LINE_RE.match(ln).group(1)) if LINE_RE.match(ln) else False)]
    out, lang = [], None
    for ln in kept:
        m = re.match(r"^  (en|zh):\s*\{", ln)
        if m:
            lang = m.group(1)
        if lang and re.match(r"^  \},?\s*$", ln):
            out.append(I18N_BEGIN)
            out.extend("    '%s': '%s'," % (k, _escape(v)) for k, v in gen_pairs(lang))
            out.append(I18N_END)
            lang = None
        out.append(ln)
    return '\n'.join(out)


# ------------------------------------------------------------------ templates

def esc(t):
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def esc_text(t):
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


NAV_TMPL = '''  <header class="site-header" role="banner">
    <nav class="nav-container" aria-label="Main navigation">
      <a href="{{R}}index.html" class="nav-brand" data-i18n-aria-label="nav.brand.aria" aria-label="FilialConnect Home">
        <svg class="nav-logo" viewBox="0 0 42 42" fill="none" aria-hidden="true">
          <circle cx="21" cy="21" r="20" fill="#2B5797" opacity="0.12"/>
          <path d="M21 8c-4 0-8 3-8 8 0 5 3 9 5 12h6c2-3 5-7 5-12 0-5-4-8-8-8z" fill="#2B5797" opacity="0.3"/>
          <path d="M15 26h12v3a2 2 0 01-2 2H17a2 2 0 01-2-2v-3z" fill="#2B5797"/>
          <circle cx="18" cy="18" r="2" fill="#2B5797"/>
          <circle cx="24" cy="18" r="2" fill="#2B5797"/>
          <path d="M17 22c0 0 2 2 4 2s4-2 4-2" stroke="#2B5797" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
        <span class="nav-title" data-i18n="nav.brand">FilialConnect</span>
      </a>

      <button class="nav-toggle" aria-label="Toggle navigation menu" aria-expanded="false">
        <span></span><span></span><span></span>
      </button>

      <ul class="nav-links">
        <li><a href="{{R}}index.html" data-i18n="nav.home">Home</a></li>
        <li><a href="{{P}}tutorials.html" data-i18n="nav.tutorials">Tutorials</a></li>
        <li><a href="{{P}}fraud-database.html" data-i18n="nav.fraud">Fraud Alert</a></li>
        <li><a href="{{P}}printable-guides.html" data-i18n="nav.guides">Guides</a></li>
        <li><a href="{{P}}remote-assist.html" data-i18n="nav.remote">Remote Help</a></li>
        <li><a href="{{P}}call-help.html" class="nav-cta" data-i18n="nav.call">Call for Help</a></li>
        <li><button class="lang-toggle" aria-label="ZH - Switch to Chinese"><span class="lang-toggle-label">ZH</span></button></li>
      </ul>
    </nav>
  </header>'''

FOOTER_TMPL = '''  <footer class="site-footer" role="contentinfo">
    <div class="footer-content">
      <div class="footer-brand">
        <h3 data-i18n="footer.brand.h3">FilialConnect</h3>
        <p data-i18n="footer.brand.p">Bridging generations through thoughtful technology. Designed for seniors, built with care.</p>
      </div>
      <div class="footer-links">
        <h4 data-i18n="footer.features.h4">Features</h4>
        <ul>
          <li><a href="{{P}}tutorials.html" data-i18n="footer.link.tutorials">Tutorial Library</a></li>
          <li><a href="{{P}}call-help.html" data-i18n="footer.link.call">Call for Help</a></li>
          <li><a href="{{P}}remote-assist.html" data-i18n="footer.link.remote">Remote Assistance</a></li>
          <li><a href="{{P}}fraud-database.html" data-i18n="footer.link.fraud">Fraud Alerts</a></li>
          <li><a href="{{P}}printable-guides.html" data-i18n="footer.link.guides">Printable Guides</a></li>
        </ul>
      </div>
      <div class="footer-links">
        <h4 data-i18n="footer.about.h4">About</h4>
        <ul>
          <li><a href="{{P}}tutorials.html" data-i18n="footer.link.getting-started">Getting Started</a></li>
          <li><a href="{{P}}fraud-database.html" data-i18n="footer.link.safety">Safety Tips</a></li>
        </ul>
      </div>
    </div>
    <div class="footer-bottom">
      <p data-i18n="footer.bottom">FilialConnect &mdash; Digital Warmth Across the Miles</p>
    </div>
  </footer>'''

TUT_PAGE_TMPL = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <script>document.documentElement.classList.add("js")</script>
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 32 32%27%3E%3Ccircle cx=%2716%27 cy=%2716%27 r=%2715%27 fill=%27%232B5797%27 opacity=%270.12%27/%3E%3Ccircle cx=%2716%27 cy=%2712%27 r=%275%27 fill=%27%232B5797%27/%3E%3Cpath d=%27M8 26c0-5 3.5-8 8-8s8 3 8 8%27 fill=%27%232B5797%27/%3E%3C/svg%3E">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="theme-color" content="#2B5797">
  <meta name="description" content="{{DESC}}">
  <title>{{TITLE}}</title>
  <link rel="stylesheet" href="{{R}}assets/css/main.css">
  <script src="{{R}}assets/js/i18n.js"></script>
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="FilialConnect 孝心联">
  <meta property="og:title" content="{{TITLE}}">
  <meta property="og:description" content="{{DESC}}">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="{{TITLE}}">
  <meta name="twitter:description" content="{{DESC}}">
</head>
<body>
  <a href="#main-content" class="skip-link" data-i18n="skip-link">Skip to main content</a>

{{NAV}}

  <main id="main-content">
    <nav class="breadcrumb" aria-label="Breadcrumb">
      <a href="{{R}}index.html" data-i18n="breadcrumb.home">Home</a>
      <span class="separator" aria-hidden="true">/</span>
      <a href="tutorials.html" data-i18n="breadcrumb.tutorials">Tutorials</a>
      <span class="separator" aria-hidden="true">/</span>
      <span class="current" aria-current="page" data-i18n="tut-detail.{{SLUG}}.h1">{{H1_EN}}</span>
    </nav>

    <section class="page-header" aria-labelledby="tutorial-heading">
      <h1 id="tutorial-heading" data-i18n="tut-detail.{{SLUG}}.h1">{{H1_EN}}</h1>
      <p data-i18n="tut-detail.{{SLUG}}.p">{{INTRO_EN}}</p>
    </section>

    <section class="step-list" aria-label="Tutorial steps">
{{STEPS}}
    </section>

    <section class="section" aria-labelledby="related-heading">
      <h2 id="related-heading" data-i18n="tut-detail.related">Related Tutorials</h2>
      <div class="card-grid">
{{RELATED}}
      </div>
    </section>

    <div style="text-align:center; margin-top:var(--space-lg);">
      <a href="printable-guides.html" class="btn btn-outline" data-i18n="tut-detail.guides-link">View Printable Guide</a>
    </div>
  </main>

{{FOOTER}}

  <button class="back-to-top" aria-label="Back to top" data-i18n="back-to-top" title="Back to top">
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M10 16V4M10 4L5 9M10 4l5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
  </button>

  <script src="{{R}}assets/js/main.js"></script>
</body>
</html>
'''

STEP_TMPL = '''      <div class="step-item">
        <div class="step-number"><span data-i18n="tut-detail.step">Step</span></div>
        <div class="step-number-value">{{N}}</div>
        <div class="step-content">
          <h4 data-i18n="tut-detail.{{SLUG}}.step{{N}}.title">{{TITLE}}</h4>
          <p data-i18n="tut-detail.{{SLUG}}.step{{N}}.p">{{BODY}}</p>
        </div>
      </div>'''

RELATE_TMPL = '''        <a href="{{HREF}}" class="card">
          <h3 data-i18n="tut-detail.{{SLUG}}.related{{N}}">{{TITLE}}</h3>
        </a>'''

FRAUD_ITEM_TMPL = '''      <!-- Fraud {{N}} (generated) -->
      <div class="fraud-item" role="region" aria-labelledby="fraud-{{N}}-title">
        <div class="fraud-summary" tabindex="0" role="button" aria-expanded="false">
          <span class="fraud-level {{LEVEL}}" aria-label="{{LEVEL_LABEL}}">!</span>
          <span class="fraud-title" id="fraud-{{N}}-title" data-i18n="fraud.{{N}}.title">{{TITLE}}</span>
          <svg class="fraud-arrow" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
        <div class="fraud-detail">
          <div class="fraud-detail-inner">
            <h2 data-i18n="fraud.{{N}}.how">How It Works</h2>
            <p style="margin-bottom: var(--space-md);" data-i18n="fraud.{{N}}.how.p">{{HOWP}}</p>
            <h2 data-i18n="fraud.{{N}}.signs">Warning Signs</h2>
            <ul>
{{SIGNS}}
            </ul>
            <h2 data-i18n="fraud.{{N}}.do">What to Do</h2>
            <ul>
{{DOS}}
            </ul>
          </div>
        </div>
      </div>'''

SIGN_LI = '              <li data-i18n="fraud.{{N}}.sign{{I}}">{{TEXT}}</li>'
DO_LI = '              <li data-i18n="fraud.{{N}}.do{{I}}">{{TEXT}}</li>'


def nav_for(is_index):
    return NAV_TMPL.replace('{{R}}', '' if is_index else '../').replace('{{P}}', 'pages/' if is_index else '')


def footer_for(is_index):
    return FOOTER_TMPL.replace('{{R}}', '' if is_index else '../').replace('{{P}}', 'pages/' if is_index else '')


def render_tutorial_page(t):
    steps = '\n'.join(
        STEP_TMPL.replace('{{N}}', str(i)).replace('{{SLUG}}', t['slug'])
                 .replace('{{TITLE}}', esc_text(s['title']['en'])).replace('{{BODY}}', esc_text(s['p']['en']))
        for i, s in enumerate(t['steps'], 1))
    rel = '\n'.join(
        RELATE_TMPL.replace('{{HREF}}', r['file']).replace('{{SLUG}}', t['slug'])
                   .replace('{{N}}', str(i)).replace('{{TITLE}}', esc_text(r['title']['en']))
        for i, r in enumerate(t['related'], 1))
    h = TUT_PAGE_TMPL
    h = h.replace('{{R}}', '../')
    h = h.replace('{{TITLE}}', esc(t['title'])).replace('{{DESC}}', esc(t['desc']))
    h = h.replace('{{SLUG}}', t['slug'])
    h = h.replace('{{H1_EN}}', esc_text(t['h1']['en'])).replace('{{INTRO_EN}}', esc_text(t['intro']['en']))
    h = h.replace('{{STEPS}}', steps).replace('{{RELATED}}', rel)
    h = h.replace('{{NAV}}', nav_for(False)).replace('{{FOOTER}}', footer_for(False))
    return h


def render_fraud_items(cases):
    out = []
    for c in cases:
        h = FRAUD_ITEM_TMPL.replace('{{N}}', str(c['n'])).replace('{{LEVEL}}', c['level']).replace('{{LEVEL_LABEL}}', c['level_label'])
        h = h.replace('{{TITLE}}', esc_text(c['title']['en'])).replace('{{HOWP}}', esc_text(c['howp']['en']))
        h = h.replace('{{SIGNS}}', '\n'.join(SIGN_LI.replace('{{N}}', str(c['n'])).replace('{{I}}', str(i)).replace('{{TEXT}}', esc_text(x['en'])) for i, x in enumerate(c['signs'], 1)))
        h = h.replace('{{DOS}}', '\n'.join(DO_LI.replace('{{N}}', str(c['n'])).replace('{{I}}', str(i)).replace('{{TEXT}}', esc_text(x['en'])) for i, x in enumerate(c['dos'], 1)))
        out.append(h)
    return '\n'.join(out)


def all_pages():
    pages_dir = os.path.join(ROOT, 'pages')
    return ['index.html'] + sorted('pages/' + f for f in os.listdir(pages_dir) if f.endswith('.html'))


def sync_nav_footer(s, is_index):
    s = re.sub(r'  <header class="site-header".*?</header>', lambda m: nav_for(is_index), s, flags=re.S)
    s = re.sub(r'  <footer class="site-footer".*?</footer>', lambda m: footer_for(is_index), s, flags=re.S)
    return s


def build_outputs():
    tuts = json.load(io.open(os.path.join(CONTENT, 'tutorials.json'), encoding='utf-8'))['tutorials']
    cases = json.load(io.open(os.path.join(CONTENT, 'fraud-cases.json'), encoding='utf-8'))['cases']
    out = {'assets/js/i18n.js': render_i18n()}
    tut_by_file = {t['file']: t for t in tuts}
    for fp in all_pages():
        base = os.path.basename(fp)
        if base in tut_by_file:
            out[fp] = render_tutorial_page(tut_by_file[base])
            continue
        s = read(fp)
        s = sync_nav_footer(s, fp == 'index.html')
        if fp == 'pages/fraud-database.html':
            if FRAUD_MARK_BEG not in s or FRAUD_MARK_END not in s:
                sys.exit('FAIL: fraud markers missing (run: build.py extract)')
            block = FRAUD_MARK_BEG + '\n' + render_fraud_items(cases) + '\n' + FRAUD_MARK_END
            s = re.sub(re.escape(FRAUD_MARK_BEG) + r'.*?' + re.escape(FRAUD_MARK_END),
                       lambda m: block, s, flags=re.S)
        out[fp] = s
    return out


# ------------------------------------------------------------------ extract

def extract():
    if not os.path.isdir(CONTENT):
        os.makedirs(CONTENT)
    d = parse_dict()
    tuts = []
    for slug in SLUGS:
        fp = 'pages/tutorial-%s.html' % slug
        s = read(fp)
        title = re.search(r'<title>(.*?)</title>', s).group(1)
        desc = re.search(r'<meta name="description" content="(.*?)"', s).group(1)
        n = len(re.findall(r'class="step-number-value"', s))
        steps = [{'title': {'en': d['en']['tut-detail.%s.step%d.title' % (slug, i)],
                            'zh': d['zh']['tut-detail.%s.step%d.title' % (slug, i)]},
                  'p': {'en': d['en']['tut-detail.%s.step%d.p' % (slug, i)],
                        'zh': d['zh']['tut-detail.%s.step%d.p' % (slug, i)]}}
                 for i in range(1, n + 1)]
        related = []
        for i in (1, 2):
            m = re.search(r'<a href="([a-z\-]+\.html)" class="card">\s*<h3 data-i18n="tut-detail\.%s\.related%d">' % (slug, i), s)
            if not m:
                sys.exit('FAIL: related%d not found in %s' % (i, fp))
            related.append({'file': m.group(1),
                            'title': {'en': d['en']['tut-detail.%s.related%d' % (slug, i)],
                                      'zh': d['zh']['tut-detail.%s.related%d' % (slug, i)]}})
        tuts.append({'slug': slug, 'file': 'tutorial-%s.html' % slug,
                     'title': title, 'desc': desc,
                     'h1': {'en': d['en']['tut-detail.%s.h1' % slug], 'zh': d['zh']['tut-detail.%s.h1' % slug]},
                     'intro': {'en': d['en']['tut-detail.%s.p' % slug], 'zh': d['zh']['tut-detail.%s.p' % slug]},
                     'steps': steps, 'related': related})
    json.dump({'tutorials': tuts}, io.open(os.path.join(CONTENT, 'tutorials.json'), 'w', encoding='utf-8', newline='\n'),
              ensure_ascii=False, indent=2)

    s = read('pages/fraud-database.html')
    cases = []
    for n in range(1, 6):
        m = re.search(r'aria-labelledby="fraud-%d-title">\s*<div class="fraud-summary"[^>]*>\s*<span class="fraud-level ([a-z]+)" aria-label="([^"]+)">' % n, s)
        if not m:
            sys.exit('FAIL: fraud item %d level not found' % n)
        ns = 1
        while 'fraud.%d.sign%d' % (n, ns + 1) in d['en']:
            ns += 1
        nd = 1
        while 'fraud.%d.do%d' % (n, nd + 1) in d['en']:
            nd += 1
        cases.append({'n': n, 'level': m.group(1), 'level_label': m.group(2),
                      'title': {'en': d['en']['fraud.%d.title' % n], 'zh': d['zh']['fraud.%d.title' % n]},
                      'how': {'en': d['en']['fraud.%d.how' % n], 'zh': d['zh']['fraud.%d.how' % n]},
                      'howp': {'en': d['en']['fraud.%d.how.p' % n], 'zh': d['zh']['fraud.%d.how.p' % n]},
                      'signs_h': {'en': d['en']['fraud.%d.signs' % n], 'zh': d['zh']['fraud.%d.signs' % n]},
                      'signs': [{'en': d['en']['fraud.%d.sign%d' % (n, i)], 'zh': d['zh']['fraud.%d.sign%d' % (n, i)]} for i in range(1, ns + 1)],
                      'do_h': {'en': d['en']['fraud.%d.do' % n], 'zh': d['zh']['fraud.%d.do' % n]},
                      'dos': [{'en': d['en']['fraud.%d.do%d' % (n, i)], 'zh': d['zh']['fraud.%d.do%d' % (n, i)]} for i in range(1, nd + 1)]})
    json.dump({'cases': cases}, io.open(os.path.join(CONTENT, 'fraud-cases.json'), 'w', encoding='utf-8', newline='\n'),
              ensure_ascii=False, indent=2)

    if FRAUD_MARK_BEG not in s:
        m = re.search(r'(    <div class="fraud-list">\n)(      <!-- Fraud 1)', s)
        if not m:
            sys.exit('FAIL: fraud-list anchor not found')
        s = s[:m.end(1)] + FRAUD_MARK_BEG + '\n' + s[m.end(1):]
        i = s.index(FRAUD_MARK_BEG)
        c = re.search(r'\n    </div>', s[i:])
        pos = i + c.start() + 1
        s = s[:pos] + FRAUD_MARK_END + '\n' + s[pos:]
        write('pages/fraud-database.html', s)
        print('fraud markers inserted')
    print('extract: content/tutorials.json (%d) + content/fraud-cases.json (%d)' % (len(tuts), len(cases)))


def do_build():
    out = build_outputs()
    for fp, text in out.items():
        write(fp, text)
    print('built %d files' % len(out))


def do_check():
    bad = []
    for fp, text in build_outputs().items():
        if read(fp) != text:
            bad.append(fp)
    for fp in bad:
        print('DRIFT:', fp)
    if bad:
        sys.exit(1)
    print('check: %d derived files in sync' % len(build_outputs()))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'build'
    {'extract': extract, 'build': do_build, 'check': do_check}[cmd]()
