#!/usr/bin/env python3
"""FilialConnect content pipeline (D1-A era tooling; stdlib-only by inheritance, not by policy).

Single source: content/tutorials.json + content/fraud-cases.json (+ templates
in this file). Derived, committed artifacts:
  - pages/tutorial-*.html          (full-page generation)
  - 404.html                       (full-page generation)
  - sitemap.xml                    (generated from the page roster)
  - assets/js/i18n.js              (generated key block per language)
  - nav (<header>) / footer on all pages (marker-delimited partial sync)
  - canonical / og:url / anti-FOUC head script on all pages
  - pages/fraud-database.html items block (between FRAUD-ITEMS markers)

Commands:
  python tools/build.py extract        one-off bootstrap of content JSON + markers
  python tools/build.py build          regenerate derived artifacts
  python tools/build.py check          rebuild in memory; exit 1 on drift (CI gate)
  python tools/build.py pages          print the generated page roster
"""
import io
import json
import os
import re
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, 'content')
SITE_BASE = 'https://lxh113377.github.io/filialconnect'

HEAD_MARK_BEG = '  <!-- BEGIN:HEAD-META (tools/build.py) -->'
HEAD_MARK_END = '  <!-- END:HEAD-META -->'
NAV_MARK_BEG = '  <!-- BEGIN:NAV (tools/build.py) - do not edit, edit tools/build.py NAV_TMPL -->'
NAV_MARK_END = '  <!-- END:NAV -->'
FOOTER_MARK_BEG = '  <!-- BEGIN:FOOTER (tools/build.py) - do not edit, edit tools/build.py FOOTER_TMPL -->'
FOOTER_MARK_END = '  <!-- END:FOOTER -->'

FRAUD_MARK_BEG = '      <!-- BEGIN:FRAUD-ITEMS (tools/build.py) -->'
FRAUD_MARK_END = '      <!-- END:FRAUD-ITEMS -->'

CARDS_MARK_BEG = ('      <!-- BEGIN:TUTORIAL-CARDS (tools/build.py) '
                  '- edit content/tutorial-cards.json + content/card-art/<slug>.svg -->')
CARDS_MARK_END = '      <!-- END:TUTORIAL-CARDS -->'

# The library card grid, generated. Only two things per card are not derivable and therefore live
# in content: the card order plus the invisible `<!-- Tutorial N: label -->` comment
# (content/tutorial-cards.json), and the hand-drawn picture (content/card-art/<slug>.svg).
# Tags, titles, blurbs and links come from the roster + dictionary, which is what lets
# `t_content_roster` assert that adding a tutorial needs no HTML edit at all.
CARD_TMPL = (
    '      <!-- Tutorial %s -->\n'
    '      <div class="tutorial-card" data-category="%s" role="listitem">\n'
    '        <div class="tutorial-card-image">\n%s\n'
    '        </div>\n'
    '        <div class="tutorial-card-body">\n'
    '          <div class="tutorial-card-tags">\n%s\n'
    '          </div>\n'
    '          <h2 data-i18n="tut.%s.h3">%s</h2>\n'
    '          <p data-i18n="tut.%s.p">%s</p>\n'
    '          <a href="tutorial-%s.html" class="card-link">\n'
    '            <span data-i18n="tut.view">%s</span>\n'
    '            <svg width="16" height="16" viewBox="0 0 18 18" fill="none" aria-hidden="true">'
    '<path d="M6 4l5 5-5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round"/></svg>\n'
    '          </a>\n'
    '        </div>\n'
    '      </div>\n')

I18N_BEGIN = '    // BEGIN:GENERATED (tools/build.py) - edit content/*.json instead'
I18N_END = '    // END:GENERATED'

LINE_RE = re.compile(r"^    '([^']+)':\s*'((?:[^'\\]|\\.)*)',?\s*$")

INLINE_JS = '<script>document.documentElement.classList.add("js")</script>'
FOUC_JS = ('<script>document.documentElement.classList.add("js");'
           'try{var f=localStorage.getItem("filialconnect-fontscale");'
           'if(f&&f!=="base"){document.documentElement.setAttribute("data-fontscale",f)}}'
           'catch(e){}</script>')


def load_content():
    """Read the authoritative content JSON once; derive every roster/regex."""
    tuts = json.load(io.open(os.path.join(CONTENT, 'tutorials.json'), encoding='utf-8'))['tutorials']
    cases = json.load(io.open(os.path.join(CONTENT, 'fraud-cases.json'), encoding='utf-8'))['cases']
    return tuts, cases


LEDGER = 'reports/last-updated.json'


def last_updated():
    """{page: {'date': ..., 'hash': ...}}, written by tools/last-updated.py.

    That tool is the only place git dates are read, and it runs locally where the full history
    exists; CI has a shallow checkout (measured: 12 commits of a page collapse to 1). A missing
    ledger simply means no stamp; a *wrong* stamp is what the gate catches.
    """
    return json.loads(read(LEDGER)) if os.path.exists(os.path.join(ROOT, LEDGER)) else {}


def derived_slug_re():
    slugs = [t['slug'] for t in load_content()[0]]
    return re.compile(r"^tut-detail\.(%s)\.(h1|p|img\.alt|step\d+\.title|step\d+\.p|related\d+)$" % '|'.join(slugs))


def derived_fraud_key_re():
    cases = load_content()[1]
    nums = '|'.join(str(c['n']) for c in cases)
    sub = []
    for c in cases:
        sub += ['sign%d' % i for i in range(1, len(c['signs']) + 1)]
        sub += ['do%d' % i for i in range(1, len(c['dos']) + 1)]
    leaf = 'title|how|how\\.p|signs|do|' + '|'.join(sorted(set(sub), key=lambda s: (-len(s), s)))
    return re.compile(r"^fraud\.(%s)\.(%s)$" % (nums, leaf))


def is_generated_key(k):
    return bool(derived_slug_re().match(k) or derived_fraud_key_re().match(k))


# Namespace pattern that does NOT depend on the current content, so keys left behind by a deleted
# tutorial or a shortened step list can still be recognised as derived.
DERIVED_NS_RE = re.compile(r'^(?:tut-detail\.[a-z-]+\.(?:h1|p|img\.alt|step\d+\.(?:title|p)'
                           r'|related\d+)|fraud\.\d+\.[a-z0-9.]+)$')


def locale_outputs():
    """{path: text} for assets/locales/*.json with the content-derived keys synced in.

    Those keys used to be a hand-pasted copy of content/*.json - 19+ per tutorial per language -
    which is both the main cost of adding a tutorial and a standing drift risk (edit the content,
    leave the old string in the dictionary). Hand-written keys (nav, cards, UI) are never touched.
    """
    out = {}
    for lang in ('en', 'zh'):
        fp = 'assets/locales/%s.json' % lang
        pairs = gen_pairs(lang)
        d = json.loads(read(fp))
        for k, v in pairs:
            if d.get(k) != v:
                d[k] = v
        keep = {k for k, _ in pairs}
        for k in [k for k in d if DERIVED_NS_RE.match(k) and k not in keep]:
            del d[k]
        out[fp] = json.dumps(d, ensure_ascii=False, indent=2) + '\n'
    return out



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


# Dictionary values must be plain text (applyTranslations renders them via
# textContent, so a literal &mdash; would show as "&mdash;" on screen).
# HTML named entities are normalized here so the dictionary is canonical.
_ENTITIES = [('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'),
             ('&apos;', "'"), ('&nbsp;', ' '), ('&mdash;', '—'), ('&ndash;', '–'),
             ('&hellip;', '…'), ('&times;', '×'), ('&divide;', '÷')]


def _normalize_entities(v):
    v = v.replace('&amp;', '\x01')
    for src, dst in _ENTITIES[1:]:
        v = v.replace(src, dst)
    return v.replace('\x01', '&')


def _escape(v):
    return v.replace('\\', '\\\\').replace("'", "\\'")


def read(fp):
    return io.open(os.path.join(ROOT, fp), encoding='utf-8').read()


def write(fp, text):
    io.open(os.path.join(ROOT, fp), 'w', encoding='utf-8', newline='\n').write(text)


def parse_dict():
    """{'en': {k: v}, 'zh': {...}} — read from assets/locales/*.json.

    The JSON files are the dictionary's single source since the Node toolchain
    took over assets/js/i18n.js (that file is now a generated runtime bundle),
    so gates read JSON instead of scraping JavaScript for string literals.
    """
    return {lang: json.loads(read('assets/locales/%s.json' % lang)) for lang in ('en', 'zh')}


def gen_pairs(lang):
    """Ordered (key, value) list for one language from content JSON."""
    tuts, cases = load_content()
    L = []
    for t in tuts:
        s = t['slug']
        L.append(('tut-detail.%s.h1' % s, t['h1'][lang]))
        L.append(('tut-detail.%s.p' % s, t['intro'][lang]))
        L.append(('tut-detail.%s.img.alt' % s, t['img_alt'][lang]))
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


NAV_TMPL = NAV_MARK_BEG + '''
  <header class="site-header" role="banner">
    <nav class="nav-container" data-i18n-aria-label="nav.main.aria" aria-label="Main navigation">
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

      <button type="button" class="nav-toggle" data-i18n-aria-label="nav.toggle.aria" aria-label="Toggle navigation menu" aria-expanded="false">
        <span></span><span></span><span></span>
      </button>

      <ul class="nav-links">
        <li><a href="{{R}}index.html" data-i18n="nav.home">Home</a></li>
        <li><a href="{{P}}tutorials.html" data-i18n="nav.tutorials">Tutorials</a></li>
        <li><a href="{{P}}fraud-database.html" data-i18n="nav.fraud">Fraud Alert</a></li>
        <li><a href="{{P}}printable-guides.html" data-i18n="nav.guides">Guides</a></li>
        <li><a href="{{P}}remote-assist.html" data-i18n="nav.remote">Remote Help</a></li>
        <li><a href="{{P}}call-help.html" class="nav-cta" data-i18n="nav.call">Call for Help</a></li>
        <li><button type="button" class="lang-toggle" aria-label="ZH - Switch to Chinese"><span class="lang-toggle-label">ZH</span></button></li>
      </ul>

      <div class="nav-a11y" role="group" data-i18n-aria-label="nav.a11y.group" aria-label="Reading aids">
        <button type="button" class="a11y-btn font-btn" data-fontscale="base" aria-pressed="false" data-i18n="font.base">Standard</button>
        <button type="button" class="a11y-btn font-btn" data-fontscale="lg" aria-pressed="false" data-i18n="font.lg">Large</button>
        <button type="button" class="a11y-btn font-btn" data-fontscale="xl" aria-pressed="false" data-i18n="font.xl">Huge</button>
        <button type="button" class="a11y-btn read-btn" aria-pressed="false" data-i18n="read.btn">Read aloud</button>
      </div>
    </nav>
  </header>''' + '\n' + NAV_MARK_END

FOOTER_TMPL = FOOTER_MARK_BEG + '''
  <footer class="site-footer" role="contentinfo">
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
          <li><a href="{{P}}accessibility-statement.html" data-i18n="footer.link.a11y">Accessibility Statement</a></li>
        </ul>
      </div>
    </div>
    <div class="footer-bottom">
      <p data-i18n="footer.bottom">FilialConnect &mdash; Digital Warmth Across the Miles</p>
      <p class="footer-report"><a href="{{FB}}" rel="noopener" data-i18n="footer.report">Report a problem with this page</a></p>
    </div>
  </footer>''' + '\n' + FOOTER_MARK_END

TUT_PAGE_TMPL = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  ''' + INLINE_JS + '''
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 32 32%27%3E%3Ccircle cx=%2716%27 cy=%2716%27 r=%2715%27 fill=%27%232B5797%27 opacity=%270.12%27/%3E%3Ccircle cx=%2716%27 cy=%2712%27 r=%275%27 fill=%27%232B5797%27/%3E%3Cpath d=%27M8 26c0-5 3.5-8 8-8s8 3 8 8%27 fill=%27%232B5797%27/%3E%3C/svg%3E">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="theme-color" content="#2B5797">
  <meta name="description" content="{{DESC}}">
  <title>{{TITLE}}</title>
  <link rel="stylesheet" href="{{R}}assets/css/main.css">
  <script src="{{R}}assets/vendor/i18next.min.js"></script>
  <script src="{{R}}assets/vendor/i18next-browser-languagedetector.min.js"></script>
  <script src="{{R}}assets/js/i18n.js"></script>
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="FilialConnect 孝心联">
  <meta property="og:title" content="{{TITLE}}">
  <meta property="og:description" content="{{DESC}}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{{TITLE}}">
  <meta name="twitter:description" content="{{DESC}}">
  {{JSONLD}}
</head>
<body>
  <a href="#main-content" class="skip-link" data-i18n="skip-link">Skip to main content</a>

{{NAV}}

  <main id="main-content">
    <nav class="breadcrumb" data-i18n-aria-label="breadcrumb.aria" aria-label="Breadcrumb">
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

    <figure class="tut-illustration">
      <img src="{{R}}{{IMG}}" data-i18n-alt="tut-detail.{{SLUG}}.img.alt" alt="{{IMG_ALT_EN}}" width="960" height="540" loading="lazy">
      <figcaption data-i18n="tut-img.note">Teaching illustration (simplified mock-up, not a real app screenshot).</figcaption>
    </figure>

    <section class="step-list" data-i18n-aria-label="tut.steps.aria" aria-label="Tutorial steps">
{{STEPS}}
    </section>
{{UPDATED}}
    <section class="section" aria-labelledby="related-heading">
      <h2 id="related-heading" data-i18n="tut-detail.related">Related Tutorials</h2>
      <div class="card-grid">
{{RELATED}}
      </div>
    </section>

    {{PREVNEXT}}

    <div style="text-align:center; margin-top:var(--space-lg);">
      <a href="printable-guides.html" class="btn btn-outline" data-i18n="tut-detail.guides-link">View Printable Guide</a>
    </div>
  </main>

{{FOOTER}}

  <button type="button" class="back-to-top" data-i18n-aria-label="back-to-top.aria" aria-label="Back to top">
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
          <h2 class="step-title" data-i18n="tut-detail.{{SLUG}}.step{{N}}.title">{{TITLE}}</h2>
          <p data-i18n="tut-detail.{{SLUG}}.step{{N}}.p">{{BODY}}</p>
        </div>
      </div>'''

PNAV_TMPL = '''    <nav class="page-nav" data-i18n-aria-label="tut.pagenav.aria" aria-label="Tutorial navigation">
{{ITEMS}}
    </nav>'''

PNAV_ITEM = '''      <a href="{{HREF}}" class="page-nav-{{DIR}}"><span class="page-nav-dir" data-i18n="tut.{{DIR}}.label">{{LABEL_EN}}</span><span class="page-nav-title" data-i18n="tut-detail.{{SLUG}}.h1">{{TITLE_EN}}</span></a>'''

RELATE_TMPL = '''        <a href="{{HREF}}" class="card">
          <h2 class="tutorial-card-title" data-i18n="tut-detail.{{SLUG}}.related{{N}}">{{TITLE}}</h2>
        </a>'''

FRAUD_ITEM_TMPL = '''      <!-- Fraud {{N}} (generated) -->
      <div class="fraud-item" role="region" aria-labelledby="fraud-{{N}}-title">
        <div class="fraud-summary" tabindex="0" role="button" aria-expanded="false">
          <span class="fraud-level {{LEVEL}}" data-i18n-aria-label="fraud.risk.{{LEVEL}}.aria" aria-label="{{LEVEL_LABEL}}">!</span>
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


ISSUES_BASE = SITE_BASE.replace('https://', 'https://github.com/').replace('.github.io', '') + '/issues/new'


def feedback_url(fp):
    """Prefilled "report a problem" link naming this page, derived from SITE_BASE so the
    repository is written down once. The accessibility statement promises a footer link on every
    page; before this existed the promise was false (measured: zero issues/new links site-wide)."""
    return '%s?title=%s' % (ISSUES_BASE, urllib.parse.quote('[page] ' + fp))


def footer_for(is_index, fp=None):
    out = FOOTER_TMPL.replace('{{R}}', '' if is_index else '../').replace('{{P}}', 'pages/' if is_index else '')
    return out.replace('{{FB}}', feedback_url(fp or ('index.html' if is_index else 'pages/tutorials.html')))


def canonical_for(fp):
    return SITE_BASE + ('/' if fp == 'index.html' else '/' + fp)


# 2026-09-29: switching to ZH translated the body but left the browser tab English, because no
# page's <title> is localized and applyTranslations never touched document.title. These pages can
# derive the tab title from their translated <h1> + brand (see t_page_title, which re-checks the
# equality and rejects a stale `derived`); the rest keep a hand-authored title that is not
# `h1 + brand`, so derivation would rewrite the English tab -> `manual`.
PAGE_TITLE_MANUAL = {
    'index.html': 'page.title.index',                # 'FilialConnect - Digital Bridge for Seniors'
    '404.html': 'page.title.404',                    # 'Page not found (404) | FilialConnect 孝心联'
    'pages/call-help.html': 'page.title.call-help',  # 'Call for Help' vs h1 'Need Help Right Now?'
    'pages/fraud-database.html': 'page.title.fraud-database',  # 'Fraud Alerts' vs h1 'Fraud Alert Database'
}


def page_title_mode(fp):
    """`derived`, or `manual:<dict key>` for a hand-authored title.

    Round 30 stopped at `manual` and left those four pages - the homepage, the 404, the help page
    and the fraud page - showing an English tab on a Chinese site. Naming the key here lets the
    runtime swap the tab while `t_page_title` keeps asserting the English half is untouched.
    """
    key = PAGE_TITLE_MANUAL.get(fp)
    return 'manual:' + key if key else 'derived'


def dynamic_dict_keys():
    """Dictionary keys the runtime reads by a name no scanner can see as a literal.

    main.js slices the key out of the generated meta tag, so neither the `data-i18n="..."` scan nor
    the `t('a.b')` literal scan finds them and the orphan rule deletes them. The CI tool and the
    local judge both import THIS function instead of restating the list - two copies of "is this key
    used" once disagreed and turned a release commit red.
    """
    return set(PAGE_TITLE_MANUAL.values())


def sync_head(s, fp):
    """Upsert the marker-delimited canonical / og:url / social-image block
    before </head>."""
    OG_BY_PAGE = {
        'pages/tutorials.html': ('og-tutorials.png', 'FilialConnect 孝心联 tutorials - large-print step-by-step guides'),
        'pages/fraud-database.html': ('og-fraud.png', 'FilialConnect 孝心联 fraud alerts - scam patterns, warning signs, what to do'),
        'pages/call-help.html': ('og-call-help.png', 'FilialConnect 孝心联 call for help - one big button to reach family'),
    }
    og_img, og_alt = OG_BY_PAGE.get(fp, ('og-cover.png', 'FilialConnect 孝心联 - bilingual elderly-friendly tech tutorials'))
    og = SITE_BASE + '/assets/images/' + og_img
    up = '../' if fp.startswith('pages/') else ''
    block = '\n'.join([HEAD_MARK_BEG,
                       '  <link rel="manifest" href="%smanifest.json">' % up,
                       '  <link rel="apple-touch-icon" href="%sassets/images/icon-192.png">' % up,
                       '  <link rel="canonical" href="%s">' % canonical_for(fp),
                       '  <meta property="og:url" content="%s">' % canonical_for(fp),
                       '  <meta property="og:image" content="%s">' % og,
                       '  <meta property="og:image:width" content="1200">',
                       '  <meta property="og:image:height" content="630">',
                       '  <meta property="og:image:alt" content="%s">' % og_alt,
                       '  <meta name="twitter:image" content="%s">' % og,
                       '  <meta name="filialconnect:page-title" content="%s">' % page_title_mode(fp),
                       HEAD_MARK_END])
    if HEAD_MARK_BEG in s and HEAD_MARK_END in s:
        s = re.sub(re.escape(HEAD_MARK_BEG) + r'.*?' + re.escape(HEAD_MARK_END),
                   lambda m: block, s, flags=re.S)
    else:
        s = s.replace('</head>', block + '\n</head>', 1)
    s = s.replace('<meta name="twitter:card" content="summary">',
                  '<meta name="twitter:card" content="summary_large_image">')
    return s.replace(INLINE_JS + '\n  ', FOUC_JS + '\n  ').replace(INLINE_JS, FOUC_JS)


def page_nav(tuts, t):
    """Prev/next links following the order of content/tutorials.json.

    Titles reuse the generated `tut-detail.<slug>.h1` key instead of carrying their own copy, so a
    renamed guide cannot leave a stale title behind in its neighbour's footer.
    """
    i = next((n for n, x in enumerate(tuts) if x['slug'] == t['slug']), None)
    if i is None:
        return ''
    items = []
    for direction, other, label in (('prev', i - 1, 'Previous tutorial'), ('next', i + 1, 'Next tutorial')):
        if 0 <= other < len(tuts):
            n = tuts[other]
            items.append(PNAV_ITEM.replace('{{HREF}}', n['file']).replace('{{DIR}}', direction)
                         .replace('{{LABEL_EN}}', esc_text(label)).replace('{{SLUG}}', n['slug'])
                         .replace('{{TITLE_EN}}', esc_text(n['h1']['en'])))
    if not items:
        return ''
    return PNAV_TMPL.replace('{{ITEMS}}', chr(10).join(items))


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
    h = h.replace('{{IMG}}', t['illustration']).replace('{{IMG_ALT_EN}}', esc(t['img_alt']['en']))
    # The stamp comes from reports/last-updated.json (see tools/last-updated.py): a hash of this
    # tutorial's own content decides whether the date moves, so an unrelated edit republishes
    # nothing. Same value feeds the human-visible <time> and the schema.org dateModified.
    stamp = last_updated().get('pages/' + t['file'], {}).get('date')
    h = h.replace('{{PREVNEXT}}', page_nav(load_content()[0], t))
    h = h.replace('{{UPDATED}}',
                  ('    <p class="page-meta"><span data-i18n="meta.updated">Last updated</span>: '
                   '<time datetime="%s">%s</time></p>' % (stamp, stamp)) if stamp else '')
    ld = {'@context': 'https://schema.org', '@type': 'HowTo',
          'name': t['h1']['en'], 'description': t['intro']['en'],
          'step': [{'@type': 'HowToStep', 'position': i, 'name': s['title']['en'], 'text': s['p']['en']}
                   for i, s in enumerate(t['steps'], 1)]}
    if stamp:
        ld['dateModified'] = stamp
    h = h.replace('{{JSONLD}}', '<script type="application/ld+json">'
            + json.dumps(ld, ensure_ascii=True, separators=(',', ':')) + '</script>')
    return h.replace('{{NAV}}', nav_for(False)).replace('{{FOOTER}}', footer_for(False, 'pages/' + t['file']))


FOOTER_404 = '  <script src="assets/js/main.js"></script>'

PAGE_404_TMPL = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  ''' + INLINE_JS + '''
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 32 32%27%3E%3Ccircle cx=%2716%27 cy=%2716%27 r=%2715%27 fill=%27%232B5797%27 opacity=%270.12%27/%3E%3Ccircle cx=%2716%27 cy=%2712%27 r=%275%27 fill=%27%232B5797%27/%3E%3Cpath d=%27M8 26c0-5 3.5-8 8-8s8 3 8 8%27 fill=%27%232B5797%27/%3E%3C/svg%3E">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="theme-color" content="#2B5797">
  <meta name="robots" content="noindex">
  <meta name="description" content="Page not found. FilialConnect 孝心联 - go back home or browse tutorials.">
  <title>Page not found (404) | FilialConnect 孝心联</title>
  <link rel="stylesheet" href="assets/css/main.css">
  <script src="assets/js/i18n.js"></script>
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="FilialConnect 孝心联">
  <meta property="og:title" content="Page not found (404) | FilialConnect 孝心联">
  <meta name="twitter:card" content="summary_large_image">
</head>
<body>
  <a href="#main-content" class="skip-link" data-i18n="skip-link">Skip to main content</a>

{{NAV}}

  <main id="main-content">
    <section class="page-header error-page" aria-labelledby="error-heading">
      <p class="error-code" aria-hidden="true">404</p>
      <h1 id="error-heading" data-i18n="error.h1">This page cannot be found</h1>
      <p data-i18n="error.p">The address may be mistyped, or the page may have moved. Nothing is wrong with your phone or computer.</p>
      <h2 data-i18n="error.where">Where to go next</h2>
      <div class="hero-actions">
        <a href="index.html" class="btn btn-accent btn-lg">
          <span data-i18n="error.home">Go back to the home page</span>
        </a>
        <a href="pages/tutorials.html" class="btn btn-outline btn-lg">
          <span data-i18n="error.tutorials">Browse all tutorials</span>
        </a>
      </div>
      <p class="error-emergency" data-i18n="error.emergency">If this is an emergency, call 120 or 110. Ask a family member for help at any time.</p>
    </section>
  </main>

{{FOOTER}}

''' + FOOTER_404 + '''
</body>
</html>
'''


def render_404_page():
    return PAGE_404_TMPL.replace('{{NAV}}', nav_for(True)).replace('{{FOOTER}}', footer_for(True, '404.html'))


def render_sitemap():
    urls = ['\n  <url><loc>%s/</loc></url>' % SITE_BASE]
    for fp in all_pages():
        if fp in ('index.html', '404.html'):
            continue
        urls.append('\n  <url><loc>%s/%s</loc></url>' % (SITE_BASE, fp))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + ''.join(urls) + '\n</urlset>\n')


# all_pages() is defined once, next to build_outputs() which is its only caller.


# ------------------------------------------------------------------ partials


def sync_nav_footer(s, is_index, fp=None):
    """Marker-delimited where possible; unmarked pages fall back to a single
    non-greedy header/footer swap, and `check` reports any page still unmarked."""
    if NAV_MARK_BEG in s and NAV_MARK_END in s:
        s = re.sub(re.escape(NAV_MARK_BEG) + r'.*?' + re.escape(NAV_MARK_END),
                   lambda m: nav_for(is_index), s, flags=re.S)
    else:
        s = re.sub(r'  <header class="site-header".*?</header>', lambda m: nav_for(is_index), s, count=1, flags=re.S)
    if FOOTER_MARK_BEG in s and FOOTER_MARK_END in s:
        s = re.sub(re.escape(FOOTER_MARK_BEG) + r'.*?' + re.escape(FOOTER_MARK_END),
                   lambda m: footer_for(is_index, fp), s, flags=re.S)
    else:
        s = re.sub(r'  <footer class="site-footer".*?</footer>', lambda m: footer_for(is_index, fp), s, count=1, flags=re.S)
    return s


FALLBACK_TEXT_RE = re.compile(
    r'<([a-z0-9]+)((?:[^>"]|"[^"]*")*?)data-i18n="([^"]+)"((?:[^>"]|"[^"]*")*?)>([^<]*)</\1>')
OPEN_TAG_RE = re.compile(r'<([a-z0-9]+)((?:[^>"]|"[^"]*")*?)>')
ATTR_KEY_RE = re.compile(r'data-i18n-(placeholder|aria-label|alt)="([^"]+)"')


def sync_fallbacks(s, dict_en):
    """One-way dictionary -> HTML fallback sync (SSG for body text).

    Text nodes: replaced with the dictionary EN value (only <br> markup is
    honored, mirroring applyTranslations). Attributes: for elements carrying
    data-i18n-placeholder / data-i18n-aria-label, the *effective* placeholder
    / aria-label attribute is upserted with the dictionary value (the
    data-i18n-* key references themselves are never touched). After this,
    tools/build.py check fails on any hand edit of fallback text.
    """
    def repl_text(m):
        tag, pre, key, post, content = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        val = dict_en.get(key)
        if val is None:
            return m.group(0)
        new = '<br>'.join(esc_text(part) for part in val.split('<br>'))
        if content.strip() == new:
            return m.group(0)
        return '<%s%sdata-i18n="%s"%s>%s</%s>' % (tag, pre, key, post, new, tag)

    def repl_tag(m):
        tag, attrs = m.group(1), m.group(2)
        found = ATTR_KEY_RE.findall(attrs)
        if not found:
            return m.group(0)
        new_attrs = attrs
        for kind, key in found:
            val = dict_en.get(key)
            if val is None:
                continue
            attr_name = kind  # placeholder / aria-label / alt
            # (?<![-\w]) so we never strip the data-i18n-* key attribute itself
            new_attrs = re.sub(r'(?<![-\w])\s*%s="[^"]*"' % attr_name, '', new_attrs)
            new_attrs = new_attrs.rstrip() + ' %s="%s"' % (attr_name, esc(val))
        return '<%s%s>' % (tag, new_attrs)

    s = FALLBACK_TEXT_RE.sub(repl_text, s)
    return OPEN_TAG_RE.sub(repl_tag, s)


# ------------------------------------------------------------------ derived configs
# Lighthouse budgets and the SW pre-cache shell are generated too: a new page
# must never silently miss the quality gates or the offline shell.

LHCI_BASE = 'http://127.0.0.1:8765/filialconnect'
LHCI_ASSERT = {
    'categories:performance': ['error', {'minScore': 0.9}],
    'categories:accessibility': ['error', {'minScore': 0.95}],
    'categories:best-practices': ['warn', {'minScore': 0.9}],
    'categories:seo': ['warn', {'minScore': 0.9}],
}
MOBILE_PRIORITY = ['index.html', 'pages/tutorials.html', 'pages/fraud-database.html', 'pages/call-help.html']


def _lh_urls(pages):
    return ['%s/%s' % (LHCI_BASE, 'index.html' if fp == 'index.html' else fp) if fp != 'index.html' else LHCI_BASE + '/' for fp in pages]


def render_lighthouserc():
    pages = all_pages()[:1] + ['404.html'] + all_pages()[1:]
    cfg = {'ci': {'collect': {'url': _lh_urls(pages), 'numberOfRuns': 2, 'settings': {'preset': 'desktop'}},
                  'assert': {'assertions': LHCI_ASSERT}}}
    return json.dumps(cfg, ensure_ascii=False, indent=2) + '\n'


def render_lighthouserc_mobile():
    cfg = {'ci': {'collect': {'url': _lh_urls(MOBILE_PRIORITY), 'numberOfRuns': 3,
                              'settings': {'formFactor': 'mobile',
                                           'screenEmulation': {'width': 412, 'height': 846, 'deviceScaleFactor': 1.75, 'mobile': True},
                                           'throttlingMethod': 'simulate'}},
                  'assert': {'assertions': dict(LHCI_ASSERT, **{'categories:performance': ['error', {'minScore': 0.85}]})}}}
    return json.dumps(cfg, ensure_ascii=False, indent=2) + '\n'


SW_TEMPLATE = """/* FilialConnect service worker - offline shell with honest freshness rules.
   Strategy (deliberately conservative for an elderly-audience site):
   - HTML pages: network-first, cache fallback (offline keeps working, updates land immediately)
   - scam-domain list: network-first, cache fallback (a stale blocklist must never win)
   - images/manifest: cache-first (content-addressed enough, rarely change)
   - CSS/JS: NOT intercepted - browser HTTP cache handles them, avoids stale-style lock-in
   SHELL below is GENERATED by tools/build.py - add a page and it lands here automatically.
*/
var VERSION = 'filialconnect-v1';
var SHELL = [
@SHELL@
];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(VERSION).then(function (cache) { return cache.addAll(SHELL); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== VERSION; }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

function networkFirst(req) {
  return fetch(req).then(function (res) {
    if (res && res.ok) {
      var clone = res.clone();
      caches.open(VERSION).then(function (c) { c.put(req, clone); });
    }
    return res;
  }).catch(function () { return caches.match(req); });
}

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return;
  var url;
  try { url = new URL(req.url); } catch (err) { return; }
  if (url.origin !== self.location.origin) return;
  var p = url.pathname;
  var isPage = p.slice(-1) === '/' || /\\.html$/.test(p);
  var isData = p.indexOf('/assets/data/') !== -1;
  var isStatic = /\\.(png|jpg|jpeg|webp|svg|ico|json)$/.test(p);
  if (isPage || isData) {
    e.respondWith(networkFirst(req));
  } else if (isStatic) {
    e.respondWith(caches.match(req).then(function (hit) {
      if (hit) return hit;
      return fetch(req).then(function (res) {
        if (res && res.ok) {
          var clone = res.clone();
          caches.open(VERSION).then(function (c) { c.put(req, clone); });
        }
        return res;
      });
    }));
  }
});
"""


def render_sw():
    items = [fp for fp in all_pages()] + ['manifest.json']
    shell = ',\n'.join("  '%s'" % x for x in items)
    return SW_TEMPLATE.replace('@SHELL@', shell)


def load_cards():
    """Ordered card roster: [{slug, label}]. Order is authority here, not in the HTML."""
    data = json.loads(read(os.path.join('content', 'tutorial-cards.json')))
    return data['cards']


def card_tags(slug, dict_en):
    """`tag1` always, `tag2` when the dictionary has it - the accent goes on the second."""
    lines = []
    for n in (1, 2):
        key = 'tut.%s.tag%d' % (slug, n)
        if key in dict_en:
            cls = 'tag' if n == 1 else 'tag tag-accent'
            lines.append('            <span class="%s" data-i18n="%s">%s</span>' % (cls, key, dict_en[key]))
    if not lines:
        sys.exit('FAIL: card %r has no tut.%s.tag1 label to show' % (slug, slug))
    return '\n'.join(lines)


def render_cards(tuts, dict_en):
    roster = {t['slug']: t for t in tuts}
    out, used = [], set()
    for i, card in enumerate(load_cards(), 1):
        slug = card['slug']
        if slug in used:
            sys.exit('FAIL: content/tutorial-cards.json lists %r twice' % slug)
        used.add(slug)
        tut = roster.get(slug)
        if tut is None:
            sys.exit('FAIL: content/tutorial-cards.json names %r, which is not in content/tutorials.json' % slug)
        art_rel = os.path.join('content', 'card-art', slug + '.svg')
        if not os.path.isfile(os.path.join(ROOT, art_rel)):
            sys.exit('FAIL: card %r has no hand-drawn picture at %s - an artless card must be a '
                     'decision, not something the generator ships silently' % (slug, art_rel))
        art = read(art_rel).rstrip('\n')
        out.append(CARD_TMPL % ('%d: %s' % (i, card['label']), tut['category'], art,
                                card_tags(slug, dict_en), slug, dict_en['tut.%s.h3' % slug],
                                slug, dict_en['tut.%s.p' % slug], slug, dict_en['tut.view']))
    missing = sorted(set(roster) - used)
    if missing:
        sys.exit('FAIL: tutorials with no card entry (add them to content/tutorial-cards.json '
                 '+ content/card-art/): %s' % missing)
    return '\n'.join(out)


def build_outputs():
    tuts, cases = load_content()
    dict_en = parse_dict()['en']
    # sitemap.xml, lighthouserc(.mobile).json, sw.js and assets/js/i18n.js are no
    # longer here: tools/build.mjs owns them with xmlbuilder2 / workbox-build /
    # the JSON locales. `node tools/build.mjs check` is that half of the gate.
    out = {}
    tut_by_file = {t['file']: t for t in tuts}
    for t in tuts:
        t['page'] = 'pages/' + t['file']
    out['404.html'] = sync_head(render_404_page(), '404.html')
    for fp in page_roster(tuts):
        base = os.path.basename(fp)
        if base in tut_by_file:
            out[fp] = sync_head(render_tutorial_page(tut_by_file[base]), fp)
            continue
        if fp == '404.html':
            continue
        s = read(fp)
        s = sync_nav_footer(s, fp == 'index.html', fp)
        s = sync_head(s, fp)
        if fp == 'pages/fraud-database.html':
            if FRAUD_MARK_BEG not in s or FRAUD_MARK_END not in s:
                sys.exit('FAIL: fraud markers missing (run: build.py extract)')
            block = FRAUD_MARK_BEG + '\n' + render_fraud_items(cases) + '\n' + FRAUD_MARK_END
            s = re.sub(re.escape(FRAUD_MARK_BEG) + r'.*?' + re.escape(FRAUD_MARK_END),
                       lambda m: block, s, flags=re.S)
        if fp == 'pages/tutorials.html':
            if CARDS_MARK_BEG not in s or CARDS_MARK_END not in s:
                sys.exit('FAIL: tutorial-card markers missing in pages/tutorials.html')
            block = CARDS_MARK_BEG + '\n' + render_cards(tuts, dict_en) + '\n' + CARDS_MARK_END
            s = re.sub(re.escape(CARDS_MARK_BEG) + r'.*?' + re.escape(CARDS_MARK_END),
                       lambda m: block, s, flags=re.S)
        out[fp] = s
    # SSG pass: dictionary is the single source for every fallback text/attr
    html_keys = [k for k in out if k.endswith('.html')] + ['404.html']
    for fp in sorted(set(html_keys)):
        out[fp] = sync_fallbacks(out[fp], dict_en)
    return out


def unmarked_pages():
    """Pages whose nav/footer still rely on the blind regex fallback (they would
    silently stop syncing once a page grows a second <header>)."""
    bad = []
    for fp in all_pages():
        if fp == '404.html' or os.path.basename(fp) in [t['file'] for t in load_content()[0]]:
            continue
        s = read(fp)
        if NAV_MARK_BEG not in s or FOOTER_MARK_BEG not in s:
            bad.append(fp)
    return bad



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
    return (['index.html', '404.html']
            + sorted('pages/' + f for f in os.listdir(pages_dir) if f.endswith('.html')))


def page_roster(tuts):
    """Pages on disk, plus pages the content roster promises but nobody created yet.

    The walk used to come from the filesystem alone, so adding a tutorial to
    content/tutorials.json rebuilt zero files and printed zero warnings: the new entry simply
    was not in the walk. Content is the roster; the disk is what has been rendered.
    """
    roster = list(all_pages())
    for t in tuts:
        fp = 'pages/' + t['file']
        if fp not in roster:
            roster.append(fp)
    return roster


def stale_tutorial_pages(tuts):
    """pages/tutorial-*.html that no content entry claims - a deleted tutorial whose page,
    sitemap entry, precache entry and search shard would otherwise stay published."""
    claimed = set('pages/' + t['file'] for t in tuts)
    return [fp for fp in all_pages()
            if fp.startswith('pages/tutorial-') and fp not in claimed]


# ------------------------------------------------------------------ extract

def extract():
    """One-off bootstrap: HTML + dictionary -> content/*.json. Not part of CI;
    `build`/`check` are the steady state and derive their rosters from the JSON."""
    if not os.path.isdir(CONTENT):
        os.makedirs(CONTENT)
    d = parse_dict()
    slugs = sorted(re.match(r'tutorial-(.+)\.html$', os.path.basename(p)).group(1)
                   for p in all_pages() if '/tutorial-' in p.replace(os.sep, '/'))
    tuts = []
    for slug in slugs:
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
        related, i = [], 1
        while 'tut-detail.%s.related%d' % (slug, i) in d['en']:
            m = re.search(r'<a href="([a-z\-]+\.html)" class="card">\s*<h2 class="tutorial-card-title" data-i18n="tut-detail\.%s\.related%d">' % (slug, i), s)
            if not m:
                sys.exit('FAIL: related%d not found in %s' % (i, fp))
            related.append({'file': m.group(1),
                            'title': {'en': d['en']['tut-detail.%s.related%d' % (slug, i)],
                                      'zh': d['zh']['tut-detail.%s.related%d' % (slug, i)]}})
            i += 1
        tuts.append({'slug': slug, 'file': 'tutorial-%s.html' % slug,
                     'title': title, 'desc': desc,
                     'h1': {'en': d['en']['tut-detail.%s.h1' % slug], 'zh': d['zh']['tut-detail.%s.h1' % slug]},
                     'intro': {'en': d['en']['tut-detail.%s.p' % slug], 'zh': d['zh']['tut-detail.%s.p' % slug]},
                     'steps': steps, 'related': related})
    json.dump({'tutorials': tuts}, io.open(os.path.join(CONTENT, 'tutorials.json'), 'w', encoding='utf-8', newline='\n'),
              ensure_ascii=False, indent=2)

    s = read('pages/fraud-database.html')
    cases, n = [], 1
    while 'fraud.%d.title' % n in d['en']:
        m = re.search(r'aria-labelledby="fraud-%d-title">\s*<div class="fraud-summary"[^>]*>\s*<span class="fraud-level ([a-z]+)"'
                      r'(?: data-i18n-aria-label="[^"]*")? aria-label="([^"]+)">' % n, s)
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
        n += 1
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
    out = locale_outputs()
    out.update(build_outputs())
    for fp, text in out.items():
        write(fp, text)
    # Second pass turns marker-less nav/footer regions into marked ones so that
    # every later edit is caught by `check`.
    out2 = locale_outputs()
    out2.update(build_outputs())
    for fp, text in out2.items():
        if read(fp) != text:
            write(fp, text)
    print('built %d files (%d html, %d locales; node owns i18n.js/sitemap/lighthouserc/sw.js)'
          % (len(out2), sum(1 for fp in out2 if fp.endswith('.html')),
             sum(1 for fp in out2 if fp.startswith('assets/locales/'))))


def do_check():
    tuts, _cases = load_content()
    out = locale_outputs()
    out.update(build_outputs())
    missing = [fp for fp in out if not os.path.exists(os.path.join(ROOT, fp))]
    bad = [fp for fp, text in out.items()
           if os.path.exists(os.path.join(ROOT, fp)) and read(fp) != text]
    stale = stale_tutorial_pages(tuts)
    if missing or bad or stale:
        for fp in sorted(missing):
            print('MISSING (content promises this page but it was never built):', fp)
        for fp in sorted(bad):
            print('DRIFT:', fp)
        for fp in sorted(stale):
            print('STALE (page is published, no content entry claims it):', fp)
        print('Fix with: python tools/build.py build; delete STALE pages by hand')
        sys.exit(1)
    unmarked = unmarked_pages()
    if unmarked:
        for fp in unmarked:
            print('UNMARKED (nav/footer not yet marker-guarded):', fp)
        sys.exit(1)
    print('check: %d derived files in sync, 0 unmarked partials' % len(out))


def do_pages():
    for fp in all_pages():
        print(fp)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'build'
    {'extract': extract, 'build': do_build, 'check': do_check, 'pages': do_pages}[cmd]()
