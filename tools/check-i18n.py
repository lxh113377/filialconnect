#!/usr/bin/env python3
"""i18n symmetry gate: EN/ZH dictionary keys must match exactly, and every
data-i18n attribute used in HTML must exist in the dictionary.
Usage: python tools/check-i18n.py   (exit 0 = pass, 1 = fail)"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY_RE = re.compile(r"^\s*'([^']+)'\s*:", re.M)


def main():
    js = io.open(os.path.join(ROOT, 'assets', 'js', 'i18n.js'), encoding='utf-8').read()
    en_m = re.search(r"en:\s*\{(.*?)\n  \}", js, re.S)
    zh_m = re.search(r"zh:\s*\{(.*?)\n  \}", js, re.S)
    if not en_m or not zh_m:
        print('FAIL: en/zh dictionary blocks not found')
        return 1

    en = set(KEY_RE.findall(en_m.group(1)))
    zh = set(KEY_RE.findall(zh_m.group(1)))
    failures = []

    if en != zh:
        for k in sorted(en - zh):
            failures.append('EN-only key: %s' % k)
        for k in sorted(zh - en):
            failures.append('ZH-only key: %s' % k)

    pages = [os.path.join(ROOT, 'index.html')]
    pages_dir = os.path.join(ROOT, 'pages')
    pages += [os.path.join(pages_dir, f) for f in sorted(os.listdir(pages_dir)) if f.endswith('.html')]

    used = set()
    for fp in pages:
        s = io.open(fp, encoding='utf-8').read()
        used |= set(re.findall(r'data-i18n(?:-placeholder|-aria-label)?="([^"]+)"', s))

    main_js = io.open(os.path.join(ROOT, 'assets', 'js', 'main.js'), encoding='utf-8').read()
    js_refs = set(re.findall(r"'([A-Za-z0-9.\-]+)'", main_js))
    for k in sorted(used - en):
        failures.append('data-i18n key missing from dict: %s' % k)
    for k in sorted(en - used - js_refs):
        failures.append('orphan key (unused in HTML and JS): %s' % k)

    if failures:
        for f in failures:
            print('FAIL:', f)
        return 1
    print('PASS: %d keys EN/ZH symmetric, %d HTML keys covered, 0 orphans' % (len(en), len(used)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
