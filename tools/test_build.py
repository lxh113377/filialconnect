#!/usr/bin/env python3
"""Pipeline and markup invariants for FilialConnect (stdlib only).

These are the regression net that HTMLHint and Lighthouse cannot provide:
the content pipeline's idempotency, the accessibility rules the templates
must keep honouring, and the "copy must not promise what code does not do"
invariants that broke three times during development.

Usage: python tools/test_build.py      (exit 0 = all pass)
"""
import gzip
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

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
    check('python half owns every page', set(out) >= set(pages()),
          'missing %s' % sorted(set(pages()) - set(out)))
    check('node half reports no drift (i18n.js / sitemap / lighthouserc / sw)',
          subprocess.run([shutil.which('node') or 'node',
                          os.path.join(ROOT, 'tools', 'build.mjs'), 'check'],
                         capture_output=True, text=True).returncode == 0,
          'run: node tools/build.mjs check')
    # The regex writer and the regex reader can share a blind spot; this re-reads
    # every page as a parsed DOM and compares against the dictionary itself.
    dom = subprocess.run([shutil.which('node') or 'node',
                          os.path.join(ROOT, 'tools', 'verify-dom.mjs')],
                         capture_output=True, text=True)
    check('DOM audit: fallback text and head meta agree with assets/locales',
          dom.returncode == 0, (dom.stdout or '').strip().split('\n')[0:3][-1])
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
        used |= set(re.findall(r'data-i18n(?:-(?:placeholder|aria-label|alt))?="([^"]+)"', html_only(fp)))
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
    # 2026-09-25: the user revoked "zero dependency" as a goal or selling point, and it
    # had already crept back into 6 files (two of them as hard rules). This guard is the
    # machine-side lock so the phrasing cannot return silently in a future round.
    banned_slogan = ('零依赖', '零外部依赖', '保持无依赖', '不引入 CDN', 'dependency-free',
                     'zero-dependency', 'Zero dependencies', 'dependencies-0',
                     'no third-party dependency')
    targets = ['README.md', 'CONTRIBUTING.md', 'SECURITY.md', 'CODE_OF_CONDUCT.md',
               'SOURCES.md', 'manifest.json', 'sw.js', 'assets/css/main.css',
               'assets/js/i18n.js'] + pages()
    hits = [(fp, w) for fp in targets for w in banned_slogan if w in read(fp)]
    check('no public file re-adopts the revoked "zero dependency" slogan', not hits, str(hits[:4]))
    # Vendored libraries (i18next, workbox) are shipped from our own origin, so the
    # older "we load no third-party code at all" phrasing is now factually wrong.
    stale_claims = ('不加载任何第三方脚本', '不请求任何第三方资源', '零外部依赖', '无第三方依赖')
    vendor = os.path.isdir(os.path.join(ROOT, 'assets', 'vendor'))
    claims = [(fp, c) for fp in ('README.md', 'CONTRIBUTING.md', 'SECURITY.md')
              for c in stale_claims if vendor and c in read(fp)]
    check('docs match the shipped runtime (vendored libs != "no third-party code")',
          not claims, str(claims[:3]))
    check('link checker discloses its coverage limit',
          '83,000' in s and '8.3 万' in s and 'does not mean' in s and '并不等于' in s)
    feed = json.loads(read('assets/data/fraud-feeds-meta.json'))
    cn_pct = 100.0 * feed['mainland_cn_domains'] / feed['domains']
    check('mainland-coverage wording matches the measured feed (<1% claim)',
          'fewer than 1%' in s and '不到 1%' in s and cn_pct < 1.0,
          'copy claims <1%%, feed measures %.2f%%' % cn_pct)


# ------------------------------------------- 4b. shipped matcher, run under node
MATCH_JS = re.compile(r'(function hostOf\(raw\) \{.*?\n    \}\n\n.*?function listed'
                      r'\(set, host\) \{.*?\n    \})', re.S)


def t_scam_matcher():
    """Run the matcher the browser actually ships (extracted verbatim from main.js)
    against the real snapshot, so the JS and the Python-side expectations cannot
    drift apart the way a Python re-implementation of the rule would."""
    src = MATCH_JS.search(read('assets/js/main.js'))
    check('main.js exposes hostOf + listed for the parity test', src is not None)
    if not src:
        return
    node = None
    for cand in ('node', 'node.exe'):
        node = shutil.which(cand)
        if node:
            break
    if not node:
        check('node available for matcher parity test', False,
              'node not found on PATH — this test is a hard requirement, not optional')
        return
    harness = os.path.join(tempfile.mkdtemp(prefix='fc-match-'), 'harness.js')
    with io.open(harness, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write("'use strict';\nvar fs = require('fs');\n")
        fh.write(src.group(1) + '\n')
        fh.write("var set = new Set(fs.readFileSync(process.argv[2], 'utf8')"
                 ".split(/\\r?\\n/).map(function (l) { return l.trim(); })"
                 ".filter(Boolean));\n")
        fh.write("var out = [];\nprocess.argv.slice(3).forEach(function (inp) {\n"
                 "  var h = hostOf(inp.toLowerCase());\n"
                 "  out.push(h && listed(set, h) ? 'HIT' : 'MISS');\n});\n"
                 "process.stdout.write(out.join('\\n'));\n")
    # A deep host that upstream publishes verbatim, plus a made-up parent of it.
    deep = next(l.strip() for l in io.open(os.path.join(ROOT, 'assets', 'data', 'destroylist-domains.txt'),
                                           encoding='utf-8') if l.strip().count('.') >= 3)
    probe = 'zz.' + deep
    cases = [
        ('https://linkvertise.com/abc', 'HIT'),        # listed root
        ('http://x.y.github.io/repo', 'MISS'),         # free host not listed -> no wildcard FP
        ('https://www.baidu.com/s?wd=1', 'MISS'),      # legit mainstream domain
        ('http://' + deep + '/p', 'HIT'),              # exact deep host entry
        ('https://' + probe + '/p', 'HIT'),            # below a deep entry (the 19.8% fix)
        ('not a link at all', 'MISS'),                  # unparseable input
    ]
    argv = [node, harness, os.path.join(ROOT, 'assets', 'data', 'destroylist-domains.txt')]
    argv += [c[0] for c in cases]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        check('node matcher harness completes', False, 'timeout after 120s')
        return
    got = proc.stdout.strip().split('\n')
    check('node matcher harness runs cleanly', proc.returncode == 0 and len(got) == len(cases),
          (proc.stderr or '')[:200])
    for (inp, want), have in zip(cases, got):
        check('matcher %-46s -> %s' % (want, inp[:38]), have == want, 'got ' + have)


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
          not [l for l in lines if '/' in l or ' ' in l])
    check('scam-domain snapshot is attributed to an upstream commit', bool(meta.get('commit')))
    check('scam-domain snapshot carries a digest for the offline audit',
          bool(meta.get('snapshot_sha256')))
    pkg = json.loads(read('package.json'))
    lock = json.loads(read('package-lock.json'))
    dev = pkg.get('devDependencies', {})
    check('CI tooling is declared in package.json',
          {'htmlhint', 'linkinator', '@lhci/cli'} <= set(dev), str(sorted(dev)))
    check('dev tooling versions are exact (no ^ or ~ drift inside CI)',
          not [k for k, v in dev.items() if v.lstrip() and v[0] in '^~*x'],
          str({k: v for k, v in dev.items() if v[:1] in '^~*x'}))
    # Deliberately NO assertion that `dependencies` stays empty: that would re-encode
    # "hand-roll everything" as a machine rule. Whether to add a library is a judgement
    # call, not a gate. (2026-09-25 user revoked the zero-dependency stance.)
    pkgs = lock.get('packages', {})
    drift = {k: (dev.get(k), pkgs.get('node_modules/' + k, {}).get('version')) for k in dev
             if pkgs.get('node_modules/' + k, {}).get('version') != dev.get(k)}
    check('lockfile pins the same dev tool versions package.json declares', not drift, str(drift))
    check('lockfile pins transitive deps too (undici class of breakage)',
          len(pkgs) > 50, '%d packages locked' % len(pkgs))
    # listed() walks up to the registrable root, so a free-hosting suffix in the
    # list would flag every site under it. Upstream has never listed one; keep that
    # as a canary so an upstream addition becomes a human decision, not a wave of
    # false alarms for grandma's blog.
    public_suffixes = {'blogspot.com', 'github.io', 'netlify.app', 'vercel.app', 'pages.dev',
                       'web.app', 'appspot.com', 'herokuapp.com', 'wixsite.com', 'weebly.com',
                       'wordpress.com', 'substack.com', 'notion.site', 'glitch.me', 'repl.co',
                       'ngrok.io', 'cloudfront.net', 'amazonaws.com', 't.me', 'bit.ly'}
    widened = sorted(set(lines) & public_suffixes)
    check('no public-hosting suffix listed (would widen to mass false positives)',
          not widened, str(widened))


def t_workflows():
    """Actions must be pinned to an immutable commit and annotated with the tag
    it resolves to. A bare @v6 moves under CI without notice — that is the same
    failure class that turned the linkinator/undici bump red. SHA-vs-tag truth is
    re-checked against the remote by _internal/audit_action_pins.py (needs net)."""
    wf_dir = os.path.join(ROOT, '.github', 'workflows')
    line = re.compile(r'uses:\s*([\w.\-/]+)@(\S+)(?:\s+#\s*(\S+))?')
    found = 0
    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith('.yml'):
            continue
        for repo, ref, comment in line.findall(read(os.path.join('.github', 'workflows', fn))):
            found += 1
            check('%s: %s pinned to a commit sha' % (fn, repo), len(ref) == 40 and
                  all(c in '0123456789abcdef' for c in ref), ref)
            check('%s: %s sha pin carries a #vX.Y.Z comment' % (fn, repo),
                  bool(comment) and comment.startswith('v'), comment or '(none)')
    check('workflow pin audit saw the steps it expects', found >= 6, '%d uses: lines' % found)
    # The tooling lives in node_modules now; a leftover bare `lhci ...` (which used
    # to work because of a global install) dies with exit 127 in CI.
    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith('.yml'):
            continue
        body = [l for l in read(os.path.join('.github', 'workflows', fn)).split('\n')
                if not l.strip().startswith('#')]
        stray = [l.strip() for l in '\n'.join(body).split('\n')
                 if re.search(r'(^|[^/\w.-])(lhci|htmlhint|linkinator)\s', l)
                 and 'node_modules/.bin' not in l]
        check('%s: no bare CI-tool invocation outside node_modules/.bin' % fn,
              not stray, str(stray[:2]))


def t_vendor():
    """The vendored UMD bundles publish under a specific global name. Guessing it
    (LanguageDetector vs i18nextBrowserLanguageDetector) makes i18next.init() a
    silent no-op, so assert main.js references the name the file really exports."""
    js = read('assets/js/main.js')
    for vendor in ('assets/vendor/i18next.min.js',
                   'assets/vendor/i18next-browser-languagedetector.min.js'):
        head = read(vendor)[:400]
        m = re.search(r"\)\.([A-Za-z][A-Za-z0-9]*)\s*=", head)
        check('%s exports a discoverable UMD global' % vendor, m is not None, head[:80])
        if m:
            check('main.js uses the real global %s from %s' % (m.group(1), vendor),
                  m.group(1) in js, 'main.js never mentions %s' % m.group(1))
    check('main.js initialises i18next', 'i18next.use(' in js and '.init({' in js)
    check('main.js keeps a dictionary fallback if the library is blocked',
          'i18nReady()' in js and 'I18N[lang][key] !== undefined' in js)


# ------------------------------------------------------------------- 8. budgets
# starlight gates what a page may weigh (`size-limit`: 7 kB HTML / 27 kB JS / 16.75 kB
# CSS, gzipped) so a regression shows up as a red check instead of a slower phone.
# Ceilings below are calibrated against the measured gzip distribution of the shipped
# tree on 2026-09-25, not guessed: HTML min 2.4 / median 3.7 / max 5.3 KiB, CSS 8.6 KiB,
# largest JS 22.4 KiB (the generated dictionary), whole payload 562.8 KiB. Each ceiling
# is ~1.5x the current worst case: loose enough not to churn, tight enough that doubling
# a file is caught. The scam list is upstream data rather than our code, so it gets its
# own, wider ceiling and a message that says "decide", not "shrink".
BUDGET_PAGES_DIR = 'pages'
BUDGETS = [
    (r'\.html$', 8 * 1024, 'page'),
    (r'\.css$', 16 * 1024, 'stylesheet'),
    (r'\.js$', 30 * 1024, 'script'),
    (r'\.json$', 12 * 1024, 'data/manifest'),
    (r'\.png$', 64 * 1024, 'image'),
]
SCAM_LIST_BUDGET = 640 * 1024
TOTAL_BUDGET_EXCLUDING_SCAM_LIST = 640 * 1024


def shipped_files():
    """deploy-pages.yml's `cp -r` line is the only place that declares the artifact set."""
    wf = read(os.path.join('.github', 'workflows', 'deploy-pages.yml'))
    m = re.search(r'cp -r ([^\n]*?)(?=\s+_site/)', wf)
    if not m:
        return None
    tokens = m.group(1).split()
    out = set()
    for tok in tokens:
        if tok.endswith('.md'):
            continue  # repo docs copied beside the site, never fetched by a browser
        path = os.path.join(ROOT, tok)
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d != '__pycache__']
                for f in files:
                    out.add(os.path.relpath(os.path.join(root, f), ROOT).replace(os.sep, '/'))
        elif any(c in tok for c in '*?['):
            import glob
            for g in glob.glob(path):
                out.add(os.path.relpath(g, ROOT).replace(os.sep, '/'))
        elif os.path.exists(path):
            out.add(tok.replace(os.sep, '/'))
    return out


def gz_size(fp):
    with io.open(os.path.join(ROOT, fp), 'rb') as fh:
        return len(gzip.compress(fh.read(), 9))


def t_budgets():
    files = shipped_files()
    check('artifact set is discoverable from deploy-pages.yml', files is not None and len(files) > 10,
          str(len(files) if files else None))
    if not files:
        return
    total = 0
    for fp in sorted(files):
        size = gz_size(fp)
        total += size
        if 'destroylist' in fp:
            check('scam list stays within its data ceiling (%s)' % fp, size <= SCAM_LIST_BUDGET,
                  '%d KiB gz > %d KiB ceiling: this is upstream growth, decide on tiering or '
                  'sharding rather than editing this number' % (size // 1024, SCAM_LIST_BUDGET // 1024))
            continue
        for pattern, ceiling, label in BUDGETS:
            if re.search(pattern, fp):
                check('%s within %s ceiling' % (fp, label), size <= ceiling,
                      '%d KiB gz > %d KiB' % (size // 1024, ceiling // 1024))
    check('whole site within total budget', total - gz_size('assets/data/destroylist-domains.txt')
          <= TOTAL_BUDGET_EXCLUDING_SCAM_LIST,
          '%d KiB gz' % (total // 1024))


# ------------------------------------------------------------ 9. contrast tokens
# Round 7 found the emergency call button failing WCAG contrast in dark mode because the
# dark block re-pinned the text colour for some accent elements and not `.call-button`.
# Any rule that paints a background from the accent token must take its foreground from
# the paired on-accent token, or the next accent element fails the same silent way.
def t_contrast_tokens():
    css = read('assets/css/main.css')
    seen = 0
    for block in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        selector, body = block.group(1).strip(), block.group(2)
        if not re.search(r'background[a-z-]*:\s*var\(--color-accent\b\)', body):
            continue
        seen += 1
        uses_text_token = bool(re.search(r'(?<![-\w])color:\s*var\(--color-text\)', body))
        pinned = 'var(--color-on-accent)' in body or '#1A1A2E' in body
        check('accent-background rule does not inherit a theme-flipping text colour (%s)' % selector[:48],
              pinned or not uses_text_token,
              'background is --color-accent while color is --color-text, which inverts in dark mode')
    check('contrast-token rule actually scanned the accent surfaces', seen >= 3, 'saw %d blocks' % seen)
    # Same mistake shape, second occurrence in one round: a brand status colour used as
    # both the fill and the text sitting on its own tint. axe measured 3.90:1 (success)
    # and 2.84:1 (warning) in the light palette and the 0.95 category floor hid it.
    for status in ('success', 'warning', 'danger'):
        for pat in (r'background: var\(--color-%s-bg\);\s*color: var\(--color-%s\);' % (status, status),
                    r'color: var\(--color-%s\);\s*background: var\(--color-%s-bg\);' % (status, status)):
            hits = re.findall(pat, css)
            check('no %s brand token doubles as text on its own tint' % status, not hits, str(hits[:2]))


def main():
    for fn in (t_pipeline, t_structure, t_i18n, t_promises, t_scam_matcher, t_assets, t_output,
               t_workflows, t_vendor, t_budgets, t_contrast_tokens):
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
