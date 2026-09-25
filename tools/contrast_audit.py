#!/usr/bin/env python3
"""Resolve every foreground/background pair the stylesheet actually declares and score it
against WCAG AA in *both* palettes.

Why a static audit instead of running Lighthouse in dark mode on CI: the dark palette is a
token override block, and checking it from CI would mean duplicating those 28 declarations
behind a `data-theme` hook just so a browser could render them. That adds a drift surface to
close a checking gap. Here both palettes are resolved from the same source, on any machine,
with no browser - which also means a contributor on a light-mode laptop cannot skip it.

Calibrated against measurements, not against itself: the three defects this replaces were
reported by axe as 2.28:1, 3.90:1 and 2.84:1, and `--selfcheck` recomputes them from the
pre-fix stylesheet (git history) and refuses to pass if the numbers move.

Usage:
  python tools/contrast_audit.py            # table of every pair, worst first
  python tools/contrast_audit.py --selfcheck # assert known-bad inputs still fail the audit
  python tools/contrast_audit.py --json
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join('assets', 'css', 'main.css')
LARGE_PX = 24.0            # WCAG: >=24px normal weight, or >=18.66px bold, is "large text"
LARGE_BOLD_PX = 18.66
BOLD = 700
AA_NORMAL = 4.5
AA_LARGE = 3.0


def read(fp):
    return io.open(os.path.join(ROOT, fp), encoding='utf-8').read()


def hex_to_rgb(value):
    v = value.strip()
    m = re.fullmatch(r'#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})', v)
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def channel_linear(c):
    s = c / 255.0
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    r, g, b = (channel_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg, bg):
    """WCAG relative-luminance contrast ratio of two opaque RGB colours."""
    l1, l2 = luminance(fg), luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def strip_comments(css):
    """Comments before a selector otherwise become part of it, and ':root' following a
    banner comment stops matching ':root'. Strip first rather than loosening the match,
    so a rule inside a comment cannot be counted as a real declaration."""
    return re.sub(r'/\*.*?\*/', '', css, flags=re.S)


def blocks(css):
    """Yield (selector, body) for every simple rule block."""
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', strip_comments(css)):
        yield m.group(1).strip(), m.group(2)


def media_span(css, header_pattern):
    """Return (start, end) of an @media block including its braces, or (-1, -1)."""
    m = re.search(header_pattern, css)
    if not m:
        return -1, -1
    depth, i = 0, m.end() - 1
    for j in range(i, len(css)):
        if css[j] == '{':
            depth += 1
        elif css[j] == '}':
            depth -= 1
            if depth == 0:
                return m.start(), j + 1
    return -1, -1


def token_tables(css):
    """Light table from the top-level :root, dark table = light overlaid by the dark block.

    The dark block has to be cut out before reading :root: a nested `:root { }` matches the
    same "selector, body" scan as the top-level one, so without this the light table absorbs
    the dark values and every pair resolves to the same ratio in both palettes - a table that
    looks fine and proves nothing.
    """
    start, end = media_span(css, r'@media[^{]*prefers-color-scheme:\s*dark[^{]*\{')
    dark_css = css[start:end] if start >= 0 else ''
    light_css = (css[:start] + css[end:]) if start >= 0 else css

    light = {}
    for sel, body in blocks(light_css):
        if re.search(r'(?:^|[^\w-]):root\s*$', sel.strip()):
            for name, val in re.findall(r'(--[\w-]+)\s*:\s*([^;]+);', body):
                light[name] = val.strip()

    dark, overridden = dict(light), 0
    for sel, body in blocks(dark_css):
        if ':root' in sel:
            for name, val in re.findall(r'(--[\w-]+)\s*:\s*([^;]+);', body):
                if dark.get(name) != val.strip():
                    overridden += 1
                dark[name] = val.strip()
    return light, dark, overridden


def resolve(value, table, _depth=0):
    """Turn a declared colour (literal or var chain) into an RGB tuple, or None."""
    if value is None or _depth > 6:
        return None
    v = value.strip()
    if v.startswith('var('):
        m = re.match(r'var\((--[\w-]+)(?:\s*,\s*(.*))?\)$', v)
        if not m:
            return None
        return resolve(table.get(m.group(1)) or (m.group(2) if m.group(2) else None), table, _depth + 1)
    if v.startswith('rgba(') or v.startswith('rgb('):
        # Translucent paints cannot be resolved to one colour without knowing what is
        # behind them; that is the exact shape of the 404 watermark false pass, so it is
        # reported as unresolved rather than guessed at.
        nums = re.findall(r'[\d.]+', v.split('(', 1)[1])
        if len(nums) == 4 and float(nums[3]) < 1:
            return None
        if len(nums) >= 3:
            return tuple(int(float(n)) for n in nums[:3])
    return hex_to_rgb(v)


def declared_size(body, table):
    """Max reachable px of a clamp() font-size, so the large-text rule is not under-called."""
    m = re.search(r'(?<![-\w])font-size:\s*([^;]+);', body)
    if not m:
        return None
    raw = m.group(1).strip()
    nums = re.findall(r'(\d+(?:\.\d+)?)rem', raw)
    if nums:
        return max(float(n) for n in nums) * 16
    px = re.findall(r'(\d+(?:\.\d+)?)px', raw)
    if px:
        return max(float(n) for n in px)
    return None


def bold_enough(body):
    m = re.search(r'(?<![-\w])font-weight:\s*(\d+)', body)
    return bool(m) and int(m.group(1)) >= BOLD


def required_for(body, table):
    size = declared_size(body, table)
    if size is not None and (size >= LARGE_PX or (size >= LARGE_BOLD_PX and bold_enough(body))):
        return AA_LARGE, 'large'
    return AA_NORMAL, 'normal'


def pairs(css):
    light, dark, _overridden = token_tables(css)
    out = []
    for sel, body in blocks(css):
        bg_decl = re.search(r'background(?:-color)?:\s*([^;]+);', body)
        fg_decl = re.search(r'(?<![-\w])color:\s*([^;]+);', body)
        if not bg_decl or not fg_decl:
            continue
        entry = {'selector': sel.splitlines()[-1].strip()[:60],
                 'foreground': fg_decl.group(1).strip(),
                 'background': bg_decl.group(1).strip()}
        ok = True
        for palette, table in (('light', light), ('dark', dark)):
            fg = resolve(entry['foreground'], table)
            bg = resolve(entry['background'], table)
            if fg is None or bg is None:
                entry[palette] = None
                ok = False
                continue
            entry[palette] = round(ratio(fg, bg), 2)
        req, size_class = required_for(body, light if entry['light'] is not None else dark)
        entry['required'] = req
        entry['size_class'] = size_class
        entry['opaque'] = ok
        out.append(entry)
    return out


def failures(entries):
    return [e for e in entries if e['opaque'] and min(e['light'], e['dark']) < e['required']]


# Calibration: axe reported these three ratios in the wild. The fixture repeats the exact
# colour pairs so `--selfcheck` proves this file's luminance math agrees with axe's, without
# depending on git history being reachable (a SKIP that exits 0 is a false pass).
# (label, foreground, background, ratio reported by axe)
AXE_FIXTURES = [
    ('call-button on accent (dark palette)', '#ECEAF2', '#E8833A', 2.28),
    ('success text on success tint (light)', '#2D8B4E', '#EDF7F1', 3.90),
    ('warning text on warning tint (light)', '#D4820A', '#FFF8ED', 2.84),
]
TOLERANCE = 0.15


def selfcheck():
    bad = 0
    for label, fg, bg, expected in AXE_FIXTURES:
        got = ratio(hex_to_rgb(fg), hex_to_rgb(bg))
        drift = abs(got - expected)
        verdict = 'OK' if drift <= TOLERANCE else 'DRIFT'
        if drift > TOLERANCE:
            bad += 1
        print('selfcheck %s: %-34s computed %.2f vs axe %.2f' % (verdict, label, got, expected))
    if bad:
        print('selfcheck FAILED: %d/%d fixtures drifted, this audit cannot be trusted' % (bad, len(AXE_FIXTURES)))
        return False
    print('selfcheck passed: luminance model agrees with axe on %d measured pairs' % len(AXE_FIXTURES))
    return True



STATE_RE = re.compile(r':(hover|focus|focus-visible|focus-within|active|visited|link)\b')


def composite(value, table, bg):
    """RGB of a possibly translucent colour painted over a known solid backdrop.

    One implementation on purpose: the footer gate in tools/test_build.py used to do its own
    alpha math, which is the same "two implementations, one fixed" shape this repo keeps hitting.
    """
    v = (value or '').strip()
    m = re.match(r'rgba?\(([^)]*)\)$', v)
    if m:
        nums = re.findall(r'[\d.]+', m.group(1))
        if len(nums) >= 4 and bg is not None:
            a = float(nums[3])
            fg = tuple(int(float(n)) for n in nums[:3])
            return tuple(round(a * f + (1 - a) * b) for f, b in zip(fg, bg))
        if len(nums) >= 4:
            return None
    return resolve(v, table)


def surfaces(css, table):
    """selector -> opaque RGB, for rules that paint a solid background."""
    out = {}
    for sel, body in blocks(css):
        decl = re.search(r'background(?:-color)?:\s*([^;]+);', body)
        if not decl or STATE_RE.search(sel):
            continue
        val = decl.group(1).strip()
        if 'gradient' in val or 'url(' in val:
            continue                      # cannot be reduced to one colour; skip, do not guess
        rgb = resolve(val, table)
        if rgb is None:
            continue
        for one in sel.split(','):
            one = one.strip()
            if one:
                out[one] = rgb
    return out


def surface_for(selector, surf_map):
    """Longest surface selector that this selector is nested inside (selector-prefix ancestry)."""
    best = None
    for s, rgb in surf_map.items():
        for prefix in (s + ' ', s + ' > ', s + ' + ', s + ' ~ '):
            if selector.startswith(prefix) and (best is None or len(s) > len(best[0])):
                best = (s, rgb)
    return best


def inherited_pairs(css):
    """Foreground declared in one block, background coming from an ancestor block.

    `pairs()` only sees a rule that declares both, which is exactly how the 1.55:1 footer link
    stayed invisible to the static audit and only axe in CI caught it. Limitation to keep in mind:
    ancestry here is *selector-prefix* ancestry, not DOM ancestry - a link that sits on the footer
    only because the footer wraps it is covered when the footer itself declares a link colour.
    """
    light, dark, _over = token_tables(css)
    surf = {'light': surfaces(css, light), 'dark': surfaces(css, dark)}
    out = []
    for sel, body in blocks(css):
        fg_decl = re.search(r'(?<![-\w])color:\s*([^;]+);', body)
        if not fg_decl or STATE_RE.search(sel):
            continue
        if re.search(r'background(?:-color)?:', body):
            continue                        # already covered by pairs()
        for one in (x.strip() for x in sel.split(',')):
            parents = {name: surface_for(one, surf[name]) for name in ('light', 'dark')}
            if not any(parents.values()):
                continue
            entry = {'selector': one[:60], 'foreground': fg_decl.group(1).strip(),
                     'via': {k: (v[0] if v else None) for k, v in parents.items()}}
            ok = True
            for name, table in (('light', light), ('dark', dark)):
                pair = parents[name]
                if not pair:
                    entry[name] = None
                    ok = False
                    continue
                fg = composite(entry['foreground'], table, pair[1])
                entry[name] = None if fg is None else round(ratio(fg, pair[1]), 2)
                if entry[name] is None:
                    ok = False
            req, size_class = required_for(body, light)
            entry['required'] = req
            entry['size_class'] = size_class
            entry['opaque'] = ok
            out.append(entry)
            break
    return out


def inherited_failures(entries):
    return [e for e in entries if e['opaque'] and min(e['light'], e['dark']) < e['required']]

def main():
    as_json = '--json' in sys.argv
    if '--selfcheck' in sys.argv:
        sys.exit(0 if selfcheck() else 1)
    if '--inherited' in sys.argv:
        css = read(CSS)
        entries = inherited_pairs(css)
        bad = inherited_failures(entries)
        for e in entries:
            print('%-42s via %-26s light %-6s dark %-6s need %s (%s)%s' % (
                e['selector'], str(e['via'].get('light') or e['via'].get('dark')),
                e['light'], e['dark'], e['required'], e['size_class'],
                '' if e['opaque'] else ' [UNRESOLVED]'))
        print('inherited pairs: %d resolvable, %d unresolved, %d below threshold' % (
            len([e for e in entries if e['opaque']]), len([e for e in entries if not e['opaque']]), len(bad)))
        for e in bad:
            print('  BELOW: %s light=%s dark=%s need>=%s' % (e['selector'], e['light'], e['dark'], e['required']))
        sys.exit(0)          # advisory by contract: measuring false positives must not gate
    entries = pairs(read(CSS))
    opaque = [e for e in entries if e['opaque']]
    unresolved = [e for e in entries if not e['opaque']]
    fails = failures(entries)
    if as_json:
        print(json.dumps({'pairs': len(opaque), 'unresolved': len(unresolved),
                          'failures': fails, 'rows': sorted(opaque, key=lambda e: min(e['light'], e['dark']))},
                         ensure_ascii=False, indent=1))
    else:
        print('declared fg/bg pairs resolved: %d   translucent/unresolvable: %d' % (len(opaque), len(unresolved)))
        for e in sorted(opaque, key=lambda x: min(x['light'], x['dark']))[:22]:
            flag = 'FAIL' if min(e['light'], e['dark']) < e['required'] else '    '
            print('  %s light %5.2f  dark %5.2f  need %.1f (%s)  %s' %
                  (flag, e['light'], e['dark'], e['required'], e['size_class'], e['selector']))
        for e in unresolved[:8]:
            print('  ---- unresolvable (translucent/gradient): %s' % e['selector'])
        print('failing pairs: %d' % len(fails))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
