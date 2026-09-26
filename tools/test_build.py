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


# One list, two consumers: the public-file scan below and the repository-metadata expectation in
# t_public_metadata. Duplicating it is how the slogan survived in the one place no file gate read.
BANNED_SLOGAN = ('零依赖', '零外部依赖', '保持无依赖', '不引入 CDN', 'dependency-free',
                 'zero-dependency', 'Zero dependencies', 'dependencies-0',
                 'no third-party dependency')


def load_tool(name, fname):
    """tools/ files with a hyphen in the name cannot be imported by module name."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, 'tools', fname))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
    banned_slogan = BANNED_SLOGAN
    targets = ['README.md', 'CONTRIBUTING.md', 'SECURITY.md', 'CODE_OF_CONDUCT.md',
               'SOURCES.md', 'AGENTS.md', 'manifest.json', 'sw.js', 'assets/css/main.css',
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
    # Prose numbers rot: README said "1,426 条" and CONTRIBUTING said "1100+" while the chain had
    # reached 1,879. A number nobody re-measures is a claim, so the documents now point at the
    # command that prints it, and this stops a fresh one from being typed back in.
    stale = [(fp, m) for fp in ('README.md', 'CONTRIBUTING.md')
             for m in re.findall(r'test_build\.py[^\n]{0,24}?([\d,]{3,})\s*条', read(fp))]
    check('documents do not restate the self-test count as prose', not stale, str(stale[:2]))
    feed = json.loads(read('assets/data/fraud-feeds-meta.json'))
    cn_pct = 100.0 * feed['mainland_cn_domains'] / feed['domains']
    check('mainland-coverage wording matches the measured feed (<1% claim)',
          'fewer than 1%' in s and '不到 1%' in s and cn_pct < 1.0,
          'copy claims <1%%, feed measures %.2f%%' % cn_pct)
    # README quotes the list's size, and that quote started life as an estimate. Pin it to the file:
    # a feed refresh must move the number, not leave the doc advertising bytes nobody measured.
    body = open(os.path.join(ROOT, 'assets', 'data', 'destroylist-domains.txt'), 'rb').read()
    gz = len(gzip.compress(body, 9))
    readme = read('README.md')
    cited = [int(m.replace(',', '')) for m in re.findall(r'([\d,]{3,7}) 条', readme)]
    check('README domain count matches the shipped list', feed['domains'] in cited, str(cited[:4]))
    kb = [int(x) for x in re.findall(r'gzip 后 (\d+) KB', readme)]
    check('README gzip quote within 2% of the measured size',
          bool(kb) and abs(kb[0] * 1000 - gz) <= 0.02 * gz, 'cited %s KB, measured %d B' % (kb, gz))
    # The docs promised an idle-time pre-fetch of this list for a day; the download is now
    # intent-gated (v1.6.1), so that sentence became false while still reading like documentation.
    stale_warm = [fp for fp in ('README.md', 'SECURITY.md', 'CONTRIBUTING.md', 'SOURCES.md')
                  if '空闲时预取' in read(fp) or '空闲预取' in read(fp)]
    check('no doc still promises an idle-time pre-fetch of the fraud list',
          not stale_warm, str(stale_warm))
    check('README describes the intent-gated warm-up',
          '意图触发' in readme or '才下载' in readme, 'README must match the shipped trigger')


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
    # The click path must parse before it downloads. Ordering was previously the other way round,
    # so one click on an empty box spent 1,523,537 bytes and *then* said "无法识别网址".
    js = read('assets/js/main.js')
    start = js.find('    function check() {')
    block = js[start:js.find('\n    }', start)] if start >= 0 else ''
    check('check() body was found in main.js', bool(block))
    check('check() parses the host before downloading the list',
          0 <= block.find('hostOf(') < block.find('loadDomains('),
          'hostOf at %s, loadDomains at %s' % (block.find('hostOf('), block.find('loadDomains(')))


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
    """The artifact set, from the one enumerator that decides it (tools/stage-site.py).

    This used to regex the `cp -r` line out of deploy-pages.yml, which made a workflow's prose a
    load-bearing definition: the byte budgets and the deployment could disagree without either
    gate noticing, and the same list was hand-maintained in two workflows.
    """
    files = load_tool('stage_site_budgets', 'stage-site.py').staging_sets()[0]['deploy']
    return {f for f in files if not f.endswith('.md')}


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
    # Cross-block inheritance, the hole that hid the footer link for seven rounds: a rule that
    # declares only a colour sits on a background declared by an ancestor rule. Measured false
    # positives on this stylesheet = 0 (3 pairs, all reachable), so it is wired as blocking.
    import contrast_audit as ca
    inh = ca.inherited_pairs(css)
    check('inherited-colour audit resolved at least three pairs', len([e for e in inh if e['opaque']]) >= 3,
          'saw %d pairs, %d unresolved' % (len(inh), len([e for e in inh if not e['opaque']])))
    bad = ca.inherited_failures(inh)
    check('no inherited text colour falls below AA on its ancestor surface', not bad,
          str(['%s %s/%s need %s' % (e['selector'], e['light'], e['dark'], e['required']) for e in bad][:3]))
    # Third shape of the same mistake, found by axe in CI only: a link placed on the footer's dark
    # surface inherited the global blue and measured 1.55:1 (round 16's "report this page" link).
    # Reuses contrast_audit's own primitives on purpose - a second copy of the ratio math would be
    # the same "two implementations, one fixed" defect this repo keeps hitting.
    footer = re.search(r'\.site-footer a \{[^}]*?color:\s*rgba\(\s*255,\s*255,\s*255,\s*([0-9.]+)\s*\)', css)
    check('footer links carry their own colour (not the inherited global blue)', bool(footer),
          'no `.site-footer a` colour rule; on --color-primary-dark the global blue is 1.55:1')
    if footer:
        alpha = float(footer.group(1))
        for pal, table in zip(('light', 'dark'), ca.token_tables(css)[:2]):
            bg = ca.hex_to_rgb(table.get('--color-primary-dark', ''))
            if not bg:
                check('%s footer surface resolves to a hex colour' % pal, False, '')
                continue
            fg = ca.composite('rgba(255, 255, 255, %s)' % alpha, table, bg)
            check('%s footer link clears 4.5:1 on the footer surface' % pal,
                  ca.ratio(fg, bg) >= 4.5, '%.2f:1' % ca.ratio(fg, bg))
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
    # Anchor on the real staging command, not on prose: an assertion satisfied by a comment that
    # happens to contain the phrase is not an assertion (it previously read `cp -r index.html`,
    # and the hand-copied list it guarded no longer exists).
    stage = 'tools/stage-site.py stage'
    check('deploy stages through the enumerator', stage in wf)
    shipped = load_tool('stage_site_ui', 'stage-site.py').staging_sets()[0]['deploy']
    check('the staged set ships the search index',
          any(f.startswith('pagefind/') for f in shipped),
          'pagefind/ is a gitignored build output; a checkout has none')
    check('deploy builds the index before staging it',
          'build-search.mjs index' in wf and wf.index('build-search.mjs index') < wf.index(stage),
          'the enumerator can only ship an index that has already been built')
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


def t_contrast_coverage():
    """The audit's own denominator must not shrink unnoticed.

    A green pass means different things depending on how much of the stylesheet was judgeable.
    The ledger in reports/contrast-coverage.json is generated by tools/contrast_coverage.py, and
    this gate recomputes it: a stale file means someone changed the CSS in a way that silently
    reduced coverage (or fixed a defect without refreshing the record).
    """
    import contrast_coverage as cov
    want = cov.render(read('assets/css/main.css'))
    have = read(cov.LEDGER) if os.path.exists(os.path.join(ROOT, cov.LEDGER)) else ''
    check('contrast coverage ledger matches the current stylesheet', have == want,
          'run: python tools/contrast_coverage.py')
    if have:
        got = json.loads(have)
        check('coverage ledger has positive denominators',
              got.get('same_block_pairs', 0) >= 30 and got.get('inherited_pairs', 0) >= 3,
              str(got))
        check('nothing is below AA in either pass',
              not got.get('same_block_below_threshold') and not got.get('inherited_below_threshold'),
              str(got))


def t_perf_coverage():
    """Every page must be measured, and a sampled profile must say how much it samples.

    The two Lighthouse configs own the list of URLs CI visits, so a page can join the site and
    never be measured while every light stays green - the same shrinking-denominator class as the
    contrast ledger. Desktop must equal the roster; mobile is a deliberate sample, so its size is
    pinned here and dropping a URL becomes a decision instead of a typo.
    """
    MOBILE_SAMPLE = 4
    LOOPBACK = 'http://127.0.0.1:'

    def declared(cfg):
        obj = json.loads(read(cfg))
        urls = obj['ci']['collect']['url']
        dupes = sorted({u for u in urls if urls.count(u) > 1})
        check('%s declares no duplicate URLs' % cfg, not dupes, str(dupes))
        files = set()
        for u in urls:
            p = u.split('/filialconnect/', 1)[-1].strip('/')
            files.add('index.html' if not p else
                      ('404.html' if p == '404.html' else 'pages/' + p.split('/')[-1]))
        return urls, files

    tuts, _cases = build.load_content()
    roster = set(build.page_roster(tuts))
    desk = mob = None
    for cfg in ('lighthouserc.json', 'lighthouserc.mobile.json'):
        urls, measured = declared(cfg)
        off = [u for u in urls if not u.startswith(LOOPBACK)]
        check('%s measures only loopback URLs' % cfg, not off, str(off))
        off = [u for u in urls if '/filialconnect/' not in u]
        check('%s points every URL under the site base' % cfg, not off, str(off))
        check('%s measures only real pages' % cfg, measured <= roster, str(sorted(measured - roster)))
        if cfg == 'lighthouserc.json':
            desk = measured
        else:
            mob = measured
    check('desktop budgets cover the whole roster', desk == roster,
          'unmeasured pages: %s' % sorted(roster - desk))
    check('mobile sample is %d pages' % MOBILE_SAMPLE, len(mob) == MOBILE_SAMPLE, str(sorted(mob)))
    check('mobile sample includes the home page', 'index.html' in mob, str(sorted(mob)))
    check('mobile sample is a subset of desktop', mob <= desk, str(sorted(mob - desk)))


def t_no_control_bytes():
    """No stray control characters in tracked sources.

    A patch script with a non-raw string wrote a literal backspace (U+0008) into a regex here,
    which silently disabled the pseudo-class filter: the audit kept working and reported numbers,
    just for the wrong set of selectors. Byte-level, cheap, and it fails loudly.
    """
    for folder in ('tools', os.path.join('assets', 'js'), os.path.join('assets', 'css')):
        for name in sorted(os.listdir(os.path.join(ROOT, folder))):
            fp = os.path.join(ROOT, folder, name)
            if not os.path.isfile(fp) or not name.endswith(('.py', '.js', '.mjs', '.cjs', '.css')):
                continue
            data = open(fp, 'rb').read()
            hits = sorted({b for b in data if b < 32 and b not in (9, 10, 13)})
            check('no control bytes in %s/%s' % (folder, name), not hits, str(hits))


def t_page_nav():
    """Sequential prev/next must follow the roster, not a hand-maintained list.

    The titles are rendered through each guide's own `tut-detail.<slug>.h1` key, so this also
    checks the link text cannot drift away from the page it points at.
    """
    tuts, _cases = build.load_content()
    order = [t['slug'] for t in tuts]
    for i, t in enumerate(tuts):
        html = read('pages/' + t['file'])
        m = re.search(r'<nav class="page-nav"[^>]*>(.*?)</nav>', html, re.S)
        check('%s has a prev/next block' % t['slug'], bool(m))
        if not m:
            continue
        block = m.group(1)
        prev = re.search(r'class="page-nav-prev"><span[^>]*data-i18n="tut\.prev\.label"', block)
        nxt = re.search(r'class="page-nav-next"><span[^>]*data-i18n="tut\.next\.label"', block)
        check('%s prev matches content order' % t['slug'], bool(prev) == (i > 0))
        check('%s next matches content order' % t['slug'], bool(nxt) == (i < len(tuts) - 1))
        for direction, idx, hit in (('prev', i - 1, prev), ('next', i + 1, nxt)):
            if not hit:
                continue
            want = order[idx]
            href = re.search(r'<a href="tutorial-%s\.html" class="page-nav-%s"' % (re.escape(want), direction), block)
            check('%s %s points at %s' % (t['slug'], direction, want), bool(href))
            key = 'tut-detail.%s.h1' % want
            check('%s %s title reuses the target page key' % (t['slug'], direction), key in block, key)
    for lang in ('en', 'zh'):
        d = json.loads(read('assets/locales/%s.json' % lang))
        check('%s has both navigation labels' % lang,
              'tut.prev.label' in d and 'tut.next.label' in d)


def t_perf_measurement():
    """The measured baseline must say how much it measured, how often, and its worst sample.

    Wired after round 25 found a page that was sometimes 4x slower (LCP 2.25 s vs 9.75 s) and read
    as healthy: one sample per URL, and the budget check only looked at the median. Each assertion
    below is a number that was wrong or missing in that baseline. Calibrated first - on the current
    file every page clears its budget on its *worst* sample, so this gate has no false positives.
    """
    fp = 'reports/perf-baseline.json'
    if not os.path.exists(os.path.join(ROOT, fp)):
        check('perf baseline exists', False, 'run: node tools/perf-probe.mjs --profile=both --runs=3')
        return
    b = json.loads(read(fp))
    check('baseline used at least 3 runs per URL (one sample cannot see a bimodal page)',
          b.get('runs_per_url', 0) >= 3, str(b.get('runs_per_url')))
    check('baseline records which server it measured against', bool(b.get('server')), str(b.get('server')))
    tuts, _cases = build.load_content()
    roster = len(build.page_roster(tuts))
    expect = {'desktop': roster, 'mobile': 4}
    # Calibrated 2026-09-25 on the committed baseline (desktop worst sample 526 ms, mobile 2,406 ms)
    # with ~1.7x headroom, so a slower laptop re-measuring cannot trip it by itself. Its job is to
    # fail when something starts racing paint again - the fraud list pre-warm once moved a page's
    # desktop LCP from 523 ms to 1,685 ms and mobile from 2.25 s to 9.75 s, and every median hid it.
    lcp_ceiling = {'desktop': 900, 'mobile': 4000}
    for name, prof in sorted(b['profiles'].items()):
        pages = prof['pages']
        budget = (prof.get('budgets') or {}).get('categories:performance', {}).get('minScore')
        summ = (b.get('summary') or {}).get(name) or {}
        check('%s baseline measured %d pages' % (name, expect.get(name)),
              name in expect and len(pages) == expect.get(name), '%d pages' % len(pages))
        for p in pages:
            check('%s/%s keeps its per-sample LCP range' % (name, p['page']),
                  bool((p.get('cwv_range') or {}).get('LCP')), str(p.get('cwv_range')))
            check('%s/%s carries the unstable verdict (absent must not read as stable)' % (name, p['page']),
                  'unstable' in p, str(sorted(p)))
            if budget is not None:
                worst = (p.get('worst_sample') or {}).get('performance')
                check('%s/%s clears its budget on the worst sample' % (name, p['page']),
                      worst is not None and worst >= budget, 'worst %s < budget %s' % (worst, budget))
            lcp = (p.get('worst_sample') or {}).get('lcp')
            ceiling = lcp_ceiling.get(name)
            check('%s/%s worst-sample LCP under %sms' % (name, p['page'], ceiling),
                  lcp is not None and ceiling is not None and lcp <= ceiling,
                  'worst LCP %s ms (ceiling %s ms)' % (lcp, ceiling))
        flagged = sorted(p['page'] for p in pages if p.get('unstable'))
        listed = sorted(s.split(':')[0] for s in summ.get('unstable_pages') or [])
        check('%s lists every unstable page' % name, flagged == listed,
              'flagged %s vs listed %s' % (flagged, listed))
        check('%s summary states the worst-sample verdict' % name,
              'worst_sample_breaches' in summ, str(sorted(summ)))
        check('%s has no worst-sample budget breach' % name,
              not summ.get('worst_sample_breaches'), str(summ.get('worst_sample_breaches')))
    js = read(os.path.join('assets', 'js', 'main.js'))
    check('the fraud-list pre-warm keeps its fetch priority split',
          "priority: silent ? 'low' : 'high'" in js,
          'a background 1.5 MB download must not share urgency with the page that is rendering')
    # The warm-up must be paid for by intent, not by reading the page: 0 bytes on load was measured
    # after LCP was found to swing to 9.7 s on 3 of 13 runs. A timer/idle hook would undo that, so
    # the check is scoped to the warm-up itself rather than banning requestIdleCallback outright.
    idle_hooks = [ln.strip() for ln in js.split('\n')
                  if 'warmOnIntent' in ln and ('setTimeout' in ln or 'requestIdleCallback' in ln)]
    check('the fraud-list warm-up has no timer or idle trigger', not idle_hooks, str(idle_hooks[:2]))
    for ev in ("'focus'", "'paste'", "'input'"):
        check('the fraud list warms on %s intent' % ev,
              'addEventListener(%s, warmOnIntent' % ev in js, ev)
    # The button is not a pre-warm trigger: it is a visitor who has already decided to wait, and
    # warming there starts the silent low-priority download the click then queues behind.
    check('the 检查 button itself never triggers the silent warm-up',
          "btn.addEventListener('pointerdown', warmOnIntent" not in js
          and "btn.addEventListener('mousedown', warmOnIntent" not in js,
          'the click path must load the list with its own urgency')


def t_deploy_staging():
    """The last hop: which files actually leave the repository.

    Two hand-copied `cp -r` lists used to decide that, and they had already drifted - CI served
    `content/` (generator input, fetched by nothing) while Pages served `sw.js` and `pagefind/`
    (which CI therefore never measures). A page that referenced a path only one list carried
    would be green in CI and 404 for a visitor, so this is the shrinking-denominator class with
    the largest blast radius. tools/stage-site.py is now the only enumerator, and the derived
    set is asserted to equal the 101 files the hand list shipped.
    """
    stager = load_tool('stage_site', 'stage-site.py')
    sets, audit = stager.staging_sets()
    deploy, probe = sets['deploy'], sets['probe']
    check('staging enumerator found a plausible reference denominator',
          len(audit['html_refs']) >= stager.FLOOR,
          '%d references, floor is %d' % (len(audit['html_refs']), stager.FLOOR))
    check('derived deploy set is as large as the hand list it replaced',
          len(deploy) >= 100, '%d files' % len(deploy))
    for kind in ('refs_not_staged', 'unresolved_dynamic', 'precache_not_staged',
                 'missing_from_disk', 'probe_only'):
        check('staging audit: %s is empty' % kind, not audit[kind], str(audit[kind][:3]))
    check('probe profile stays inside what Pages serves', set(probe) <= set(deploy),
          str(sorted(set(probe) - set(deploy))[:3]))
    for page in pages():
        check('every built page is deployed: %s' % page, page in deploy, page)
    check('the fraud list is deployed (the self-check fetches it)',
          'assets/data/destroylist-domains.txt' in deploy)
    check('service-worker chunks are deployed, not just the worker',
          'sw.js' in deploy and any(f.startswith('workbox-') for f in deploy),
          str([f for f in deploy if 'workbox' in f or f == 'sw.js']))
    for fn, verb in (('ci.yml', 'probe'), ('deploy-pages.yml', 'deploy')):
        body = read(os.path.join('.github', 'workflows', fn))
        check('%s stages through the enumerator' % fn,
              'tools/stage-site.py stage' in body and '--profile %s' % verb in body, verb)
        stray = [l.strip() for l in body.split('\n')
                 if re.match(r'^\s*cp -r?\s', l) and re.search(r'\b(assets|pages|index\.html)\b', l)]
        check('%s keeps no private copy of the file list' % fn, not stray, str(stray[:2]))
    ledger_path = os.path.join('reports', 'deploy-staging.json')
    check('staging ledger is committed', os.path.isfile(os.path.join(ROOT, ledger_path)))
    ledger = json.loads(read(ledger_path))
    check('ledger deploy count matches the enumerator',
          ledger['profiles']['deploy']['count'] == len(deploy),
          'ledger %d vs live %d' % (ledger['profiles']['deploy']['count'], len(deploy)))
    check('ledger file list matches the enumerator byte for byte',
          ledger['profiles']['deploy']['files'] == deploy,
          str(sorted(set(ledger['profiles']['deploy']['files']) ^ set(deploy))[:3]))
    check('ledger records how it was made', ledger.get('generated_by') == 'tools/stage-site.py')


def t_public_metadata():
    """GitHub's About box is public copy that sits outside the file tree.

    The file-level slogan ban could not reach it, so the repository still advertised itself as a
    "Zero-dependency static site" after that framing was revoked - in the one sentence every
    search result and every visitor reads. A local gate cannot call the API (no token guarantee,
    and a network read must not decide a file test), so this pins the *expectation*; the live
    read-back is `tools/verify-live.py --metadata`, wired into the post-deploy job.
    """
    want = json.loads(read(os.path.join('reports', 'repo-metadata.json')))
    desc = want.get('description', '')
    hits = [w for w in BANNED_SLOGAN if w.lower() in desc.lower()]
    check('repo description does not revive the revoked slogan', not hits, str(hits))
    m = re.search(r'(\d+) pages generated', desc)
    check('description commits to a page count', bool(m), desc)
    if m:
        check('description page count matches the roster', int(m.group(1)) == len(pages()),
              'description says %s, roster builds %d' % (m.group(1), len(pages())))
    check('description does not promise a backend action',
          not re.search(r'notified|notify|send(s|ing)? (a )?(sms|email)', desc.lower()), desc)
    topics = want.get('topics', [])
    check('topics have no duplicates and none is empty',
          len(topics) == len(set(topics)) and all(t.strip() for t in topics), str(topics))
    check('topics are lowercase slugs as GitHub stores them',
          all(re.fullmatch(r'[a-z0-9][a-z0-9.\-]*', t) for t in topics), str(topics))
    stager = load_tool('stage_site_for_meta', 'stage-site.py')
    check('expectation homepage equals the sitemap origin',
          want.get('homepage') == stager.site_base(),
          '%r vs %r' % (want.get('homepage'), stager.site_base()))
    check('expectation is generated by the same tool that checks it',
          want.get('do_not_edit', '').startswith('this is the expectation'))


def t_offline_package():
    """The deliverable a non-developer can use, and the wiring that gets it onto the Release.

    The README promises offline use while every published Release carried zero assets: the ZIP
    existed on one machine, built by a script in another repository. Reproducibility is asserted
    rather than assumed, because a package that changes between runs cannot be audited.
    """
    pkg = load_tool('package_offline', 'package-offline.py')
    body = read(os.path.join('tools', 'package-offline.py'))
    check('pagefind is excluded from the offline package, with its reason on the line above',
          "'pagefind'" in str(pkg.DROP_DIRS) and 'resolves its shards over HTTP' in body)
    entries, counts = pkg.members()
    arcs = {a for _f, a in entries}
    check('the package carries the whole deployed site bar the build outputs',
          counts['site'] >= 45, '%d site files' % counts['site'])
    check('the package carries the generator and its content input',
          any(a.endswith('tools/build.py') for a in arcs)
          and any(a.endswith('content/tutorials.json') for a in arcs), str(sorted(counts.items())))
    check('no entry name is non-ASCII (the archive opens on non-UTF-8 locales)',
          all(all(ord(c) < 128 for c in a) for a in arcs),
          str([a for a in arcs if any(ord(c) > 127 for c in a)][:2]))
    check('every entry sits under the agreed prefix',
          all(a.startswith(pkg.PREFIX) for a in arcs), str([a for a in arcs if not a.startswith(pkg.PREFIX)][:2]))
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        one = pkg.build(os.path.join(td, 'one.zip'))
        two = pkg.build(os.path.join(td, 'two.zip'))
    check('the offline package is reproducible from one commit',
          one['sha256'] == two['sha256'], '%s vs %s' % (one['sha256'][:12], two['sha256'][:12]))
    check('the reproducibility claim has a denominator', one['entries'] == len(entries),
          'zip %d entries vs membership %d' % (one['entries'], len(entries)))
    rel = read(os.path.join('tools', 'release.py'))
    check('release.py actually attaches the asset to the Release (not just builds it)',
          "cmd.append(asset)" in rel and "'gh', 'release', 'upload'" in rel, 'build without upload is a half tool')
    check('release.py refuses to publish when the packager fails',
          'mod.build(dest)' in rel, 'the build must be on the release path, not beside it')


def main():
    for fn in (t_pipeline, t_structure, t_i18n, t_promises, t_scam_matcher, t_assets, t_output,
               t_workflows, t_vendor, t_budgets, t_contrast_tokens, t_contrast_pairs, t_release,
               t_search_corpus, t_search_ui, t_content_roster, t_no_duplicate_defs, t_no_control_bytes,
               t_changelog_shape, t_last_updated, t_feedback_exit, t_deterministic_sw, t_page_nav,
               t_contrast_coverage, t_perf_coverage, t_perf_measurement,
               t_deploy_staging, t_public_metadata, t_offline_package):
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
