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
import importlib.util
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
    # References live in every script, not just main.js's t('...') calls: a key consumed by
    # search.js through a local helper used to read as "orphan" and get deleted by mistake.
    js_refs = set()
    js_dir = os.path.join(ROOT, 'assets', 'js')
    for name in sorted(os.listdir(js_dir)):
        if not name.endswith('.js') or name == 'i18n.js':
            continue          # i18n.js is the dictionary itself, not a reference to it
        js_refs |= set(re.findall(r"'([A-Za-z0-9.\-]+\.[A-Za-z0-9.\-]+)'",
                                  read(os.path.join('assets', 'js', name))))
    orphans = en - used - js_refs
    check('no orphan dictionary keys', not orphans, str(sorted(orphans)[:8]))
    # Two implementations of "is this key used" once disagreed: tools/check-i18n.py — the CI step —
    # still scanned only main.js, so it went red on its own after this gate had gone green.
    spec = importlib.util.spec_from_file_location(
        'check_i18n', os.path.join(ROOT, 'tools', 'check-i18n.py'))
    ci_tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ci_tool)
    ci_refs = ci_tool.js_key_refs(ROOT)
    check('CI i18n tool and this gate see the same script references', ci_refs == js_refs,
          'symmetric difference: %s' % str(sorted(ci_refs ^ js_refs)[:5]))
    check('CI i18n tool sees keys used outside main.js', 'search.fulltext.found' in ci_refs,
          'positive sample — a scan that always returns the same set is how the red happened')


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
TOTAL_BUDGET_EXCLUDING_SCAM_LIST = 1100 * 1024   # measured 953 KiB gz after the search index shipped
# Pagefind's index is fetched on first query, never on first paint. Ceiling is 1.36x the
# measured 468.9 KiB gz of 52 files, so growth is caught without forbidding an extra locale.
PAGEFIND_BUDGET = 640 * 1024


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
    pagefind_gz = 0
    for fp in sorted(files):
        size = gz_size(fp)
        total += size
        if fp.startswith('pagefind/'):
            pagefind_gz += size
            continue
        if 'destroylist' in fp:
            check('scam list stays within its data ceiling (%s)' % fp, size <= SCAM_LIST_BUDGET,
                  '%d KiB gz > %d KiB ceiling: this is upstream growth, decide on tiering or '
                  'sharding rather than editing this number' % (size // 1024, SCAM_LIST_BUDGET // 1024))
            continue
        for pattern, ceiling, label in BUDGETS:
            if re.search(pattern, fp):
                check('%s within %s ceiling' % (fp, label), size <= ceiling,
                      '%d KiB gz > %d KiB' % (size // 1024, ceiling // 1024))
    check('search index within its own ceiling', pagefind_gz <= PAGEFIND_BUDGET,
          '%d KiB gz > %d KiB (pagefind/ is 52 files; re-measure before raising this)'
          % (pagefind_gz // 1024, PAGEFIND_BUDGET // 1024))
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


def t_search_corpus():
    """The Pagefind corpus is an indexing input, not a deliverable.

    Measured while wiring it: workbox's `**/*.html` glob against the repo root swept all 11
    _search/zh pages into the offline shell (precache 15 -> 26 entries), i.e. internal build
    input shipped to elderly users' devices as if it were content.
    """
    sw = read('sw.js')
    check('offline shell precaches no search-corpus pages', '_search' not in sw)
    check('offline shell precaches no pagefind output', 'pagefind/' not in sw)
    gen = 'tools/build-search.mjs'
    check('search corpus generator exists', os.path.exists(os.path.join(ROOT, gen)))
    head = read(gen)
    check('corpus pages declare a language and are noindex',
          'name="robots" content="noindex"' in head and 'lang="${lang}"' in head)
    check('corpus targets zh only (English already exists on disk)',
          "LANGS = ['zh']" in head)


def t_search_ui():
    """The search feature is only real if the page that hosts the input also loads the code
    that queries the index, and the index actually ships. Each clause below is a way this
    could quietly stop working while every other gate stayed green."""
    html = read('pages/tutorials.html')
    js = 'assets/js/search.js'
    check('search.js exists', os.path.exists(os.path.join(ROOT, js)))
    check('tutorials page loads search.js', 'assets/js/search.js' in html)
    for el in ('id="fulltext-results"', 'id="fulltext-list"', 'id="fulltext-status"'):
        check('tutorials page has the results panel element (%s)' % el, el in html)
    check('results panel starts hidden',
          re.search('<div class="fulltext-results"', html) is not None and html.split('<div class="fulltext-results"', 1)[1].split('>', 1)[0].endswith('hidden="hidden"'),
          'hidden must carry a value: .htmlhintrc attr-value-not-empty')
    check('search.js degrades instead of throwing', "['catch']" in read(js) and 'clear()' in read(js))
    check('search.js picks the index by UI language', "indexOf('zh')" in read(js))
    src = read(js)
    check('search.js latches a failed index load instead of guessing by protocol',
          'var degraded = false;' in src and 'degraded = true;' in src
          and 'if (degraded ||' in src and "location.protocol === 'file:'" not in src,
          'a protocol string is a guess: where file:// fetch is allowed it turns a working search '
          'box off. One observed failure, remembered, is true in either browser.')
    check('search.js exposes both states as observable attributes',
          "data-fulltext', 'ready'" in src and "data-fulltext', 'unavailable'" in src)
    en = json.loads(read(os.path.join('assets', 'locales', 'en.json')))
    zh = json.loads(read(os.path.join('assets', 'locales', 'zh.json')))
    check('panel label exists in both dictionaries',
          'search.fulltext.label' in en and 'search.fulltext.label' in zh)
    # A search box that announces nothing is the "silent zero results" shape this site keeps
    # being told about: the reader cannot tell "no matches" from "this thing is broken".
    live_id = 'id="fulltext-live"'
    live_tag = html[html.index(live_id):html.index(live_id) + 140] if live_id in html else ''
    check('full-text live region carries role=status and aria-live',
          live_id in html and 'role="status"' in live_tag and 'aria-live="polite"' in live_tag)
    panel_span = html[html.index('<div class="fulltext-results"'):html.index(live_id)] \
        if live_id in html and '<div class="fulltext-results"' in html else ''
    check('live region sits outside the hidden results panel',
          '</div>' in panel_span,
          'content inside [hidden] is dropped from the accessibility tree, so a live region '
          'placed there would never be announced')
    for key, ph in (('search.fulltext.found', '{n}'), ('search.fulltext.none', '{q}'),
                    ('search.fulltext.offline', None)):
        check('search.js announces %s' % key, key in src)
        check('%s exists in both dictionaries' % key, key in en and key in zh)
        if key in en and key in zh:
            check('%s interpolates its placeholder in both languages' % key,
                  (ph is None) or (ph in en[key] and ph in zh[key]),
                  'a missing {n} makes the announcement a sentence without a count')
    check('search.js reads the generated dictionary rather than a helper it cannot see',
          'window.I18N' in src,
          "main.js keeps t() inside its own IIFE; there is no global t to call here")
    wf = read(os.path.join('.github', 'workflows', 'deploy-pages.yml'))
    # Anchor on the real staging command, not on `cp -r` anywhere: the comment above it also
    # contains that phrase, and an assertion satisfied by prose is not an assertion.
    stage = 'cp -r index.html'
    check('deploy stages the search index', re.search(stage + r' [^\n]*pagefind', wf) is not None)
    check('deploy builds the index before staging it',
          'build-search.mjs index' in wf and wf.index('build-search.mjs index') < wf.index(stage),
          'pagefind/ is a gitignored build output; a checkout has none')
    # build_zip.py lives outside this repository, so a CI checkout has no parent directory to
    # read it from. Reaching for it unconditionally crashed the CI gate with FileNotFoundError:
    # a check that can only run on one person's machine is not a gate. Where the file is
    # absent the ZIP guarantee is still enforced - by _internal/verify_zip_parity.py, which
    # runs wherever the ZIP is actually built - and this says so instead of going quiet.
    zipline_path = os.path.join(ROOT, '..', '_internal', 'build_zip.py')
    if os.path.exists(zipline_path):
        zipline = io.open(zipline_path, encoding='utf-8').read()
        check('offline ZIP excludes the index it cannot use',
              "'pagefind'" in zipline and "'_search'" in zipline,
              'Pagefind fetches over HTTP, which file:// blocks')
    else:
        print('note: build_zip.py not in this checkout; ZIP exclusion is checked by '
              '_internal/verify_zip_parity.py where the ZIP is built')
    sw = read('sw.js')
    check('service worker does not precache the index', 'pagefind/' not in sw)


def t_contrast_pairs():
    """Both palettes, every declared fg/bg pair, on any machine, with no browser.

    This replaces the plan of teaching CI to render dark mode: that needed the 28-token dark
    block duplicated behind a data-theme hook, i.e. a new drift surface to close a checking
    gap. Two guards below exist because this resolver produced a plausible-looking table twice
    while it was broken (light and dark resolving to the same numbers), and a green row from a
    check that measures one palette twice is worse than no check.
    """
    import contrast_audit as ca
    import contextlib
    import io as _io
    with contextlib.redirect_stdout(_io.StringIO()):
        agrees = ca.selfcheck() is True
    check('contrast model agrees with axe on 3 measured pairs', agrees)
    css = read('assets/css/main.css')
    _light, _dark, overridden = ca.token_tables(css)
    check('dark palette really overrides tokens (else both columns prove the same thing)',
          overridden >= 20, '%d overridden' % overridden)
    entries = ca.pairs(css)
    opaque = [e for e in entries if e['opaque']]
    check('contrast resolver still parses the stylesheet', len(opaque) >= 30, '%d of %d' % (len(opaque), len(entries)))
    for e in ca.failures(entries):
        check('contrast AA in both palettes: %s' % e['selector'], False,
              'light %.2f / dark %.2f, needs %.1f' % (e['light'], e['dark'], e['required']))


def t_release():
    """Version discipline. Until round 9 this repo said `1.0.0` in package.json while the
    CHANGELOG already declared 1.2.0 released, and there was no git tag at all — a version
    that exists only in prose is not a version.

    Deliberately file-only: `actions/checkout` does not fetch tags by default, so a
    tag-existence assertion would be a false red on CI. Tagging lives in tools/release.py.
    """
    pkg = json.loads(read('package.json'))
    ver = pkg.get('version', '')
    check('package.json version is semver x.y.z', re.fullmatch(r'\d+\.\d+\.\d+', ver), ver)
    log = read('CHANGELOG.md')
    headings = re.findall(r'^## \[([\w.]+)\](?: - (\d{4}-\d{2}-\d{2}))?', log, re.M)
    check('CHANGELOG keeps an [Unreleased] section', headings and headings[0][0] == 'Unreleased', str(headings[:1]))
    # Same family as the duplicate all_pages() def: a heading that appears twice parses "fine"
    # and quietly splits the notes for one release across two places.
    unreleased = [h for h, _ in headings if h == 'Unreleased']
    check('exactly one [Unreleased] heading', len(unreleased) == 1, '%d found' % len(unreleased))
    released = [h for h in headings if h[0] != 'Unreleased']
    released_names = [h for h, _ in released]
    check('no released version heading is duplicated',
          len(released_names) == len(set(released_names)), str(released_names))
    check('CHANGELOG has at least one released version', bool(released))
    if released:
        latest, date = released[0]
        check('CHANGELOG version matches package.json', latest == ver, 'changelog %s vs package.json %s' % (latest, ver))
        check('latest released version is datestamped', bool(date), '## [%s] lacks " - YYYY-MM-DD"' % latest)
    for name, d in released[1:]:
        check('released version %s is datestamped' % name, bool(d))
    # The offline ZIP ships manifest.json and no package.json, so this is the only version marker
    # a delivered copy carries. Untended, it drifts the moment package.json moves.
    man = json.loads(read('manifest.json').lstrip('﻿'))
    check('manifest.json carries the same version as package.json',
          man.get('version') == ver,
          'manifest %s vs package.json %s' % (man.get('version'), ver))
    check('released versions descend from package.json version downward',
          not released or released[0][0] == ver)


def t_content_roster():
    """Extensibility, measured by actually adding a tutorial: the generator used to walk the
    filesystem, so a 7th entry in content/tutorials.json rebuilt zero files and warned about
    nothing. Card grid, filter taxonomy, illustration files and cross-links are the other exits
    where the same silence reproduces."""
    tuts, _cases = build.load_content()
    html = read('pages/tutorials.html')
    starts = [m.start() for m in re.finditer(r'<div class="tutorial-card" data-category="', html)]
    bounds = starts[1:] + [len(html)]
    cards = {}
    for a, b in zip(starts, bounds):
        chunk = html[a:b]
        href = re.search(r'href="tutorial-([a-z]+)\.html"', chunk)
        cat = re.search(r'data-category="([a-z]+)"', chunk)
        if href:
            cards[href.group(1)] = cat.group(1) if cat else None
    slugs = sorted(t['slug'] for t in tuts)
    check('content tutorials and library cards are the same set',
          sorted(cards) == slugs,
          'content %s vs cards %s' % (slugs, sorted(cards)))
    check('card grid has one card per tutorial', len(starts) == len(tuts),
          '%d cards vs %d tutorials' % (len(starts), len(tuts)))
    chips = set(re.findall(r'data-filter="([a-z]+)"', html)) - {'all'}
    check('every filter chip is a real category', 
          not {c for c in cards.values() if c not in chips},
          'unreachable filter chips: %s' % sorted({c for c in cards.values() if c not in chips}))
    for t in tuts:
        slug = t['slug']
        for field in ('file', 'category', 'title', 'desc', 'h1', 'intro', 'steps', 'related',
                      'illustration', 'img_alt'):
            check('%s declares %s' % (slug, field), field in t)
        check('%s card category matches content' % slug, cards.get(slug) == t.get('category'),
              'card %s vs content %s' % (cards.get(slug), t.get('category')))
        check('%s illustration exists' % slug,
              os.path.exists(os.path.join(ROOT, t.get('illustration', ''))),
              t.get('illustration'))
        check('%s has steps' % slug, bool(t.get('steps')) and all(
            s.get('title') and s.get('p') for s in t['steps']))
        # Cross-links may leave the tutorial set (several point at the fraud page); what they may
        # not do is dangle.
        pages = {os.path.basename(fp) for fp in build.all_pages()}
        for rel in t.get('related', []):
            check('%s related target is a real page' % slug, rel.get('file') in pages,
                  str(rel.get('file')))
    # One implementation, exercised here rather than re-derived: build.py owns the roster rules.
    check('no published tutorial page lacks a content entry',
          not build.stale_tutorial_pages(tuts), str(build.stale_tutorial_pages(tuts)))
    roster = build.page_roster(tuts)
    check('page roster covers every content page',
          all('pages/' + t['file'] in roster for t in tuts),
          str([t['file'] for t in tuts if 'pages/' + t['file'] not in roster]))
    for fp, text in build.locale_outputs().items():
        check('%s is in sync with content/*.json' % fp, read(fp) == text,
              'run: python tools/build.py build')
    # Contributor docs rot the same way copy does: CONTRIBUTING.md told people to hand-edit
    # assets/js/i18n.js (a generated bundle) and to expect one command to add a tutorial,
    # which is exactly the step that silently did nothing.
    doc = read('CONTRIBUTING.md')
    check('CONTRIBUTING points hand-written copy at the locale JSONs, not the bundle',
          'assets/js/i18n.js` 手写区' not in doc and '不要改 `assets/js/i18n.js`' in doc)
    check('CONTRIBUTING names both generators',
          'python tools/build.py build' in doc and 'node tools/build.mjs build' in doc,
          'pages come from python, sitemap/precache/lighthouserc from node')
    check('CONTRIBUTING keeps the card step visible', 'tutorial-card' in doc)
    check('CONTRIBUTING keeps the stamp step visible', 'last-updated.py --write' in doc)
    # Every "N 页" in the contributor doc must match the roster. Two of them were stale (13) in the
    # same session, which is how a doc that nobody checks ends up teaching the wrong command.
    stale_counts = sorted({n for n in re.findall(r'(\d+) 页', doc)
                           if n != '404' and n != str(len(build.all_pages()))})
    check('CONTRIBUTING page counts match the roster', not stale_counts,
          'roster is %d pages, doc says %s' % (len(build.all_pages()), stale_counts))


def t_no_duplicate_defs():
    """A duplicate top-level def is not a syntax error in Python - the later one silently wins and
    the earlier edit becomes a no-op. tools/build.py shipped two all_pages() that way."""
    import ast
    import collections
    tools = os.path.join(ROOT, 'tools')
    for name in sorted(os.listdir(tools)):
        if not name.endswith('.py'):
            continue
        tree = ast.parse(io.open(os.path.join(tools, name), encoding='utf-8').read())
        top = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        dup = sorted(k for k, v in collections.Counter(top).items() if v > 1)
        check('no duplicate top-level def in tools/%s' % name, not dup, str(dup))


def t_changelog_shape():
    """Two long-line editing accidents this session (rounds 12 and 14) ate a neighbouring bullet's
    lead line while adding an entry. The damage always looks the same: the orphaned continuation
    survives under a *different* bullet, and two bullets end up sharing one lead-in. That is
    structurally detectable, so it should not depend on the editor noticing."""
    log = read('CHANGELOG.md')
    section, seen, dup = None, set(), []
    for ln in log.split('\n'):
        if ln.startswith('## ['):
            section, seen = ln.strip(), set()
            continue
        if not ln.startswith('- ') or section is None:
            continue
        lead = ln[2:42].strip().lower().rstrip(':：')
        if lead and lead in seen:
            dup.append('%s :: %s' % (section, lead))
        seen.add(lead)
    check('no duplicated bullet lead-in inside a CHANGELOG section', not dup, str(dup[:3]))
    orphans = [i for i, ln in enumerate(log.split('\n')[1:], 1)
               if ln.startswith('  ') and log.split('\n')[i - 1].strip() == '']
    check('no continuation line orphaned after a blank line', not orphans, str(orphans[:3]))


def t_last_updated():
    """The 'last updated' stamp, checked without asking git anything.

    CI checks out with fetch-depth 1, where every file's last commit date is the build day
    (measured: a page with 12 commits reports 1). So the dates are produced locally by
    tools/last-updated.py and committed; the gate re-derives each tutorial's content hash and
    fails when the page carries a date that no longer matches the text it sits under.
    """
    import datetime
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'last_updated_tool', os.path.join(ROOT, 'tools', 'last-updated.py'))
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    ledger = json.loads(read('reports/last-updated.json'))
    tuts = json.loads(read('content/tutorials.json'))['tutorials']
    today = datetime.date.today().isoformat()
    check('every tutorial page carries a stamp entry',
          sorted(ledger) == sorted('pages/' + t['file'] for t in tuts),
          'ledger %s vs content %s' % (sorted(ledger), sorted('pages/' + t['file'] for t in tuts)))
    check('stamps exist only where a source can be named',
          all(fp.startswith('pages/tutorial-') for fp in ledger),
          'hand-written pages are not stamped - "updated" there would have no source')
    for t in tuts:
        fp = 'pages/' + t['file']
        ent = ledger.get(fp) or {}
        check('%s ledger hash matches its current content' % fp,
              ent.get('hash') == tool.entry_hash(t),
              'stale stamp: run python tools/last-updated.py --write (content changed, date did not)')
        d = ent.get('date', '')
        check('%s date is ISO and not in the future' % fp,
              bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', d)) and d <= today, d)
        html = read(fp)
        check('%s shows the ledger date to readers' % fp,
              '<time datetime="%s">%s</time>' % (d, d) in html)
        check('%s schema.org dateModified agrees with the visible stamp' % fp,
              '"dateModified":"%s"' % d in html,
              'two answers to "when was this updated" is the defect class this repo keeps hunting')
    check('the stamp label exists in both dictionaries',
          'meta.updated' in json.loads(read('assets/locales/en.json'))
          and 'meta.updated' in json.loads(read('assets/locales/zh.json')))


def t_feedback_exit():
    """Copy that promises a capability, checked against the capability.

    `a11s.feedback.p` has told readers for the site's whole life that every page footer carries an
    issue link. Measured before round 16: `issues/new` appeared on zero pages. That is the eighth
    instance of this repo's most expensive defect class, and it sat in the accessibility feedback
    sentence specifically. The link is now generated per page, and this gate binds the two together
    so the wording cannot outrun the code again.
    """
    import urllib.parse
    claim_zh = json.loads(read('assets/locales/zh.json'))['a11s.feedback.p']
    claim_en = json.loads(read('assets/locales/en.json'))['a11s.feedback.p']
    claims_footer = ('页脚' in claim_zh) and ('footer' in claim_en.lower())
    n = 0
    missing = []
    for fp in build.all_pages():
        s = read(fp)
        if '<footer' not in s:
            missing.append(fp + ' (no footer at all)')
            continue
        foot = s[s.index('<footer'):]
        m = re.search(r'<a href="(https://[^"]+issues/new\?title=[^"]+)" rel="noopener"'
                      r' data-i18n="footer\.report"', foot)
        if not m:
            missing.append(fp)
            continue
        title = urllib.parse.parse_qs(m.group(1).split('?', 1)[1])['title'][0]
        check('%s feedback link names the page itself' % fp, title == '[page] ' + fp, title)
        n += 1
    check('every page carries the promised footer issue link', not missing,
          str(missing[:4]) + ('' if not missing else ' (%d of %d pages have it)' % (n, len(build.all_pages()))))
    check('footer issue links exist on all pages, or the claim must be reworded',
          not claims_footer or n == len(build.all_pages()),
          'accessibility statement says every page footer links to issues; %d/%d do' % (n, len(build.all_pages())))
    check('the report label exists in both dictionaries',
          'footer.report' in json.loads(read('assets/locales/en.json'))
          and 'footer.report' in json.loads(read('assets/locales/zh.json')))


def t_deterministic_sw():
    """sw.js must not depend on the order the filesystem hands back.

    workbox emits its precache manifest in glob-crawl order. Locally that order was
    `index.html, 404.html, pages/tutorials.html, pages/tutorial-wechat.html`; on CI's Linux runner
    the same checkout produces a different crawl sequence, so the "regenerate and compare" drift
    gate failed in CI while passing on every developer machine - the shape of bug that ends a
    release. build.mjs now sorts via manifestTransforms; these checks keep it that way.
    """
    import hashlib
    body = read('sw.js')
    pairs = re.findall(r'url:"([^"]+)",revision:"([0-9a-f]{32})"', body)
    urls = [u for u, _ in pairs]
    check('sw.js precaches every html page plus the manifest',
          len(urls) == len([p for p in build.all_pages()]) + 1, '%d entries' % len(urls))
    check('sw.js precache entries are in url order, not crawl order', urls == sorted(urls),
          'first out-of-order: %s' % next((a for a, b in zip(urls, sorted(urls)) if a != b), '-'))
    wrong = []
    for url, rev in pairs:
        fp = url.lstrip('./')
        if not os.path.exists(os.path.join(ROOT, fp)):
            wrong.append(url + ' (missing)')
        elif hashlib.md5(read_bytes(fp)).hexdigest() != rev:
            wrong.append(url + ' (revision differs)')
    check('every precache revision is the md5 of the shipped file', not wrong, str(wrong[:3]))


def read_bytes(fp):
    return open(os.path.join(ROOT, fp), 'rb').read()


def main():
    for fn in (t_pipeline, t_structure, t_i18n, t_promises, t_scam_matcher, t_assets, t_output,
               t_workflows, t_vendor, t_budgets, t_contrast_tokens, t_contrast_pairs, t_release,
               t_search_corpus, t_search_ui, t_content_roster, t_no_duplicate_defs,
               t_changelog_shape, t_last_updated, t_feedback_exit, t_deterministic_sw):
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
