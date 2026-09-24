#!/usr/bin/env python3
"""i18n symmetry gate: EN/ZH dictionary keys must match exactly, and every
data-i18n attribute used in HTML must exist in the dictionary.
Usage: python tools/check-i18n.py   (exit 0 = pass, 1 = fail)"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY_RE = re.compile(r"^\s*'([^']+)'\s*:", re.M)


def main():
    # The dictionary's single source is assets/locales/*.json since the Node
    # toolchain took over assets/js/i18n.js (now a generated runtime bundle),
    # so read JSON instead of scraping JavaScript for string literals.
    try:
        en_map = json.load(io.open(os.path.join(ROOT, 'assets', 'locales', 'en.json'), encoding='utf-8'))
        zh_map = json.load(io.open(os.path.join(ROOT, 'assets', 'locales', 'zh.json'), encoding='utf-8'))
    except (OSError, ValueError) as exc:
        print('FAIL: cannot read locale JSON: %s' % exc)
        return 1
    en = set(en_map)
    zh = set(zh_map)
    failures = []

    if en != zh:
        for k in sorted(en - zh):
            failures.append('EN-only key: %s' % k)
        for k in sorted(zh - en):
            failures.append('ZH-only key: %s' % k)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import build as _build  # single page roster, keeps 404.html in scope
    pages = [os.path.join(ROOT, fp) for fp in _build.all_pages()]

    used = set()
    for fp in pages:
        s = io.open(fp, encoding='utf-8').read()
        used |= set(re.findall(r'data-i18n(?:-placeholder|-aria-label|-alt)?="([^"]+)"', s))

    main_js = io.open(os.path.join(ROOT, 'assets', 'js', 'main.js'), encoding='utf-8').read()
    js_refs = set(re.findall(r"\bt\('([A-Za-z0-9.\-]+)'\)", main_js))
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
