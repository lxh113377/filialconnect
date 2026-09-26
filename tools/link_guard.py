# -*- coding: utf-8 -*-
"""Find code that would create a link back into a live repository.

Why this exists: on 2026-09-26 a verification harness linked a throwaway `git worktree` to the real
repo's `node_modules` via a junction, and `git worktree remove --force` followed the link and deleted
the target. The same shape recurred the same day with no `git clean` involved, so the rule is about
the link itself, not one command. A rule that lives only in prose recurs; this one is machine-checked.

Scanning is AST-based, not text-based: the harnesses deliberately *mention* junctions in comments
while explaining why they must not be used. A text grep would either flag that explanation (false
positive that trains people to ignore the gate) or need an exemption list (a hole). Comments are not
code, so they are not read.

What this cannot see, stated because a gate that hides its blind spot gets trusted too much: the
string rule reads the constants of Call / Assign / AnnAssign nodes and joins them with one space, so
a marker split across two literals, or parked in an `assert`, `return` or an `if` condition, does
not match. Widening it to every string in the tree would also read the docstrings that explain this
rule. The call rule (`os.symlink(...)`) and the import rule (`_winapi`, `win32file`) do not depend on
string spelling at all, and a harness that wants to link a worktree has to execute something.
"""
import argparse
import ast
import io
import json
import os
import shutil
import sys
import tempfile
import warnings

# Markers are command-shaped on purpose: a bare word like "junction" belongs in the comments and
# docstrings that explain this rule, and flagging those would train people to switch the gate off.
LINK_MARKERS = ("mklink", "-ItemType Junction", "-ItemType SymbolicLink", "New-Item -ItemType",
                "SHCreateSymbolicLink", "symbolic-link")
LINK_ATTRS = {"symlink", "symlink_to", "hardlink", "mkdir_junction"}
MODULE_IMPORTS = {"_winapi", "win32file", "win32api", "ctypes.wintypes"}


def _str_consts(node):
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            yield sub.value


COMMENT_PREFIXES = ('#', '//', '*', '/*', '%%')


def _py_hits(text, strings=True):
    """Python file: read the syntax tree, so comments and docstring-free prose never count.

    `strings=False` stands the marker-table rule down (used for this file only, where those literals
    are data). Call and import detection is unaffected, so `os.symlink(...)` written here would still
    be caught.
    """
    tree = ast.parse(text)
    raw = []
    for node in ast.walk(tree):
        if strings and isinstance(node, (ast.Call, ast.Assign, ast.AnnAssign)):
            for marker in LINK_MARKERS:
                if marker in ' '.join(_str_consts(node)):
                    raw.append((getattr(node, 'lineno', 0), marker))
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in LINK_ATTRS:
                raw.append((node.lineno, 'call to %s()' % f.attr))
            elif isinstance(f, ast.Name) and f.id in LINK_ATTRS:
                raw.append((node.lineno, 'call to %s()' % f.id))
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in MODULE_IMPORTS:
                    raw.append((node.lineno, 'import %s' % alias.name))
    return raw


def _line_hits(text):
    """Non-Python source: no parser available here, so scan lines and skip comment-leading ones.

    Weaker than the AST path on purpose: it can be fooled by a comment that is not at line start.
    The rule it guards is rare enough that a false positive costs one look, while a blind spot cost
    744 packages twice.
    """
    raw = []
    for num, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(COMMENT_PREFIXES):
            continue
        for marker in LINK_MARKERS:
            if marker in stripped:
                raw.append((num, marker))
        for attr in LINK_ATTRS:
            if attr + '(' in stripped.replace(' ', ''):
                raw.append((num, 'call to %s()' % attr))
    return raw


def scan_source(path, text, is_self=False):
    """(line, marker) pairs for one file, plus 'fallback' when the strong detector did not apply.

    A file that does not parse is never skipped: it is scanned line by line, which is the weaker
    detector but still sees a junction command sitting in the code. Skipping would hand back a clean
    verdict for text nobody looked at; silently downgrading would hide that it happened.
    """
    note = None
    if path.endswith('.py'):
        try:
            with warnings.catch_warnings():
                # Parsing somebody else's text for markers must not spray SyntaxWarnings about
                # escape sequences that belong to that file's own copy.
                warnings.simplefilter('ignore')
                raw = _py_hits(text, strings=not is_self)
        except SyntaxError:
            raw = _line_hits(text)
            note = 'fallback'
    else:
        raw = _line_hits(text)
    per_line = {}
    for line, marker in raw:
        per_line.setdefault(line, set()).add(marker)
    return [(line, ', '.join(sorted(per_line[line]))) for line in sorted(per_line)], note


def read_source(path):
    """(text, lossy): a non-UTF-8 byte is replaced rather than excused, because every marker here
    is ASCII and a file with one bad byte is still a file that could be hiding a junction command.
    An `OSError` propagates - that is the one case where nothing was read."""
    try:
        return io.open(path, encoding='utf-8').read(), False
    except UnicodeDecodeError:
        return io.open(path, encoding='utf-8', errors='replace').read(), True


SKIP_DIRS = ('node_modules', '.git', '__pycache__', 'pagefind', 'reports')


def scan_paths(root, patterns=('.py', '.mjs', '.js')):
    """The population the scan reads, as forward-slash paths relative to `root`.

    Its own function because a coverage claim needs the denominator the scan actually walked; a
    caller that re-derived it with a different glob is how a gate starts quietly reading less.
    """
    paths = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if fn.endswith(patterns):
                paths.append(os.path.relpath(os.path.join(dirpath, fn), root).replace(chr(92), '/'))
    return sorted(paths)


def scan_tree(root, patterns=('.py', '.mjs', '.js'), self_path=None):
    """Scan every source file under `root`.

    Returns (findings, files_scanned, notes). A finding is (kind, relpath, line, marker); 'link' is
    the rule, 'unreadable' is a file that could not be opened at all - the only kind of blind spot
    left, since a parse error falls back to the line detector and a non-UTF-8 byte is read lossily
    (markers are ASCII, so lossy still sees them). Both degradations are named in `notes`.
    """
    findings, notes, scanned = [], [], 0
    self_rel = None
    if self_path:
        rel = os.path.relpath(os.path.abspath(self_path), os.path.abspath(root))
        if not os.path.isabs(rel) and rel.split(os.sep)[0] != '..':
            self_rel = rel.replace(chr(92), '/')
            notes.append('self-exclusion active: %s (marker strings only; calls and imports '
                         'are still checked)' % self_rel)
    for rel in scan_paths(root, patterns):
        scanned += 1
        try:
            text, lossy = read_source(os.path.join(root, rel))
        except OSError as exc:
            findings.append(('unreadable', rel, 0, 'cannot open: %s' % exc))
            continue
        if lossy:
            notes.append('lossy read (non-UTF-8 bytes replaced): %s' % rel)
        hits, fallback = scan_source(os.path.join(root, rel), text, is_self=(rel == self_rel))
        if fallback:
            notes.append('line fallback: %s does not parse as Python' % rel)
        for line, marker in hits:
            findings.append(('link', rel, line, marker))
    return findings, scanned, notes


def verdict(findings, scanned):
    """(ok, exit_code, lines). Zero scanned files is UNVERIFIED, never a clean bill."""
    if scanned == 0:
        return False, 2, ['UNVERIFIED: 0 source files were read - a scan that saw nothing '
                          'cannot claim the tree is clean']
    lines = []
    links = [f for f in findings if f[0] == 'link']
    unread = [f for f in findings if f[0] == 'unreadable']
    if links:
        lines.append('FAIL: nothing here may create a filesystem link; a link aimed at a live tree '
                     'is followed by `git worktree remove --force` and deletes the target')
        lines += ['  %s:%d links via %s' % (f, ln, m) for _, f, ln, m in links]
    if unread:
        lines.append('FAIL: %d file(s) could not be opened, so the scan cannot claim they are clean'
                     % len(unread))
        lines += ['  %s %s' % (f, m) for _, f, _ln, m in unread]
    if lines:
        return False, 1, lines
    return True, 0, ['OK: %d source files read, no link-creating code' % scanned]


def selftest():
    """Both directions plus the boundaries: the pattern must fire on real code, stay quiet on a
    comment that merely talks about junctions, refuse to call an empty tree clean, not report its own
    marker table, and still catch that same table's text when it appears in somebody else's file."""
    guilty = ("import subprocess\n"
              "subprocess.run(['powershell', '-Command',\n"
              "                \"New-Item -ItemType Junction -Path x -Target y\"])\n")
    comment_only = "# do not use `New-Item -ItemType Junction` here; it deleted node_modules once\n"
    symlink_call = "import os\nos.symlink('a', 'b')\n"
    cases = []
    tmp = tempfile.mkdtemp(prefix='linkguard_')
    try:
        for name, body, expect in (('comment mentioning a junction', comment_only, 0),
                                   ('a subprocess line that builds a junction', guilty, 1),
                                   ('a direct os.symlink call', symlink_call, 1)):
            d = os.path.join(tmp, name.replace(' ', '_'))
            os.makedirs(d)
            io.open(os.path.join(d, 'harness.py'), 'w', encoding='utf-8').write(body)
            findings, scanned, _notes = scan_tree(d)
            flagged = {ln for kind, _f, ln, _m in findings if kind == 'link'}
            cases.append((name, len(flagged) == expect and scanned == 1,
                          'scanned=%d flagged_lines=%d' % (scanned, len(flagged))))
        jsdir = os.path.join(tmp, 'a_js_script')
        os.makedirs(jsdir)
        io.open(os.path.join(jsdir, 'build.mjs'), 'w', encoding='utf-8').write(
            "// a comment naming New-Item -ItemType Junction is not code\n"
            "const ok = 1;\n")
        findings, scanned, _n = scan_tree(jsdir)
        js_lines, js_note = scan_source('x.mjs', io.open(
            os.path.join(jsdir, 'build.mjs'), encoding='utf-8').read())
        cases.append(('a JS comment naming the marker is not a finding, and JS parses no more',
                      scanned == 1 and not js_note and not js_lines,
                      'findings=%d' % len(findings)))
        # A file that does not parse is degraded to the line detector, never skipped - so both
        # halves have to hold: real code inside it is still caught, and the weaker scan is said out
        # loud. A third case keeps the must-not-fire half honest about comments.
        for name, body, want_hit in (
                ('non-parsing file with the command in code',
                 "x = (\nCMD = 'New-Item -ItemType Junction -Path a -Target b'\n", True),
                ('non-parsing file with the command only in a comment',
                 "def broken(:\n# New-Item -ItemType Junction here\n", False)):
            d = os.path.join(tmp, name.replace(' ', '_'))
            os.makedirs(d)
            io.open(os.path.join(d, 'dead.py'), 'w', encoding='utf-8').write(body)
            findings, scanned, notes = scan_tree(d)
            hit = [f for f in findings if f[0] == 'link']
            cases.append((name + (' is still caught' if want_hit else ' is not a false positive'),
                          bool(hit) == want_hit and scanned == 1,
                          'findings=%d' % len(hit)))
            cases.append((name + ' announces the line fallback',
                          any('line fallback' in n for n in notes), 'notes=%d' % len(notes)))
        # A file that is not valid UTF-8 is still scanned (lossily), and the population the scan
        # reports is the population `scan_paths` enumerated - otherwise a coverage claim would be
        # derived from a second, different walk of the tree.
        odd = os.path.join(tmp, 'lossy_case')
        os.makedirs(odd)
        with open(os.path.join(odd, 'mixed.py'), 'wb') as fh:
            fh.write(b"# caf\xe9 in latin-1\nCMD = 'New-Item -ItemType Junction -Path a -Target b'\n")
        findings, scanned, notes = scan_tree(odd)
        cases.append(('a non-UTF-8 file is scanned anyway and its command still counts',
                      len([f for f in findings if f[0] == 'link']) == 1
                      and any('lossy read' in n for n in notes),
                      'findings=%d notes=%d' % (len(findings), len(notes))))
        nested = os.path.join(tmp, 'population')
        os.makedirs(os.path.join(nested, 'sub', 'deeper'))
        io.open(os.path.join(nested, 'sub', 'deeper', 'deep.mjs'), 'w', encoding='utf-8').write('1\n')
        paths = scan_paths(nested)
        cases.append(('the reported file count is the enumerated population, incl. nested dirs',
                      paths == ['sub/deeper/deep.mjs'] and scan_tree(nested)[1] == len(paths),
                      str(paths)))
        empty = os.path.join(tmp, 'nothing_here')
        os.makedirs(empty)
        findings, scanned, notes = scan_tree(empty, self_path=os.path.abspath(__file__))
        ok, code, lines = verdict(findings, scanned)
        cases.append(('an empty tree is UNVERIFIED, never a pass', code == 2 and not ok,
                      'code=%d' % code))
        # A root that does not contain this file must not claim the file is exempt from it.
        cases.append(('no self-exclusion is announced for an unrelated root', not notes,
                      'notes=%d' % len(notes)))
        # Symmetric exclusion: the marker table here is data, but the identical text in another
        # file is a command. Both halves have to hold or "spare the scanner" becomes "spare anyone".
        here = os.path.dirname(os.path.abspath(__file__))
        own, _own_scanned, own_notes = scan_tree(here, patterns=('.py',),
                                                self_path=os.path.abspath(__file__))
        own_flagged = [f for f in own if f[0] == 'link' and f[1].endswith('link_guard.py')]
        cases.append(('the scanner does not report its own marker table', not own_flagged,
                      'own findings=%d' % len(own_flagged)))
        cases.append(('the self-exclusion is announced, not silently subtracted',
                      any('self-exclusion' in n for n in own_notes), str(own_notes[:1])[:70]))
        copy_dir = os.path.join(tmp, 'copied_marker')
        os.makedirs(copy_dir)
        io.open(os.path.join(copy_dir, 'other.py'), 'w', encoding='utf-8').write(
            "CMD = 'New-Item -ItemType Junction'" + chr(10))
        copied, _c1, _c2 = scan_tree(copy_dir, self_path=os.path.abspath(__file__))
        cases.append(('the same marker text in another file is still caught',
                      len([f for f in copied if f[0] == 'link']) == 1, str(copied)[:70]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # The CLI is a second entry point of its own: main() still unpacked the old 3-field finding
    # after the shape grew to 4, and every fixture above called scan_tree directly - the same
    # "the path nobody exercised" defect as the --quiet NameError found last round.
    cli_dir = os.path.join(tmp, 'cli_case')
    os.makedirs(cli_dir)
    io.open(os.path.join(cli_dir, 'clean.py'), 'w', encoding='utf-8').write("x = 1" + chr(10))
    code_clean = main(['--scan', cli_dir, '--json'])
    cases.append(('the CLI exits 0 on a clean tree (and prints machine-readable findings)',
                  code_clean == 0, 'exit=%d' % code_clean))
    io.open(os.path.join(cli_dir, 'bad.py'), 'w', encoding='utf-8').write(
        "import os" + chr(10) + "os.symlink('a', 'b')" + chr(10))
    code_link = main(['--scan', cli_dir])
    cases.append(('the CLI exits 1 when a file creates a link', code_link == 1,
                  'exit=%d' % code_link))
    bad = 0
    for name, passed, detail in cases:
        if passed:
            print('  ok  %s (%s)' % (name, detail))
        else:
            bad += 1
            print('  SELFTEST-FAIL %s (%s)' % (name, detail))
    print('link_guard selftest: %d cases, %d failures' % (len(cases), bad))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--scan', action='append', default=[],
                    help='directory to scan (repeatable); defaults to this file\'s directory')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    roots = args.scan or [os.path.dirname(os.path.abspath(__file__))]
    all_findings, total, all_notes, per_root = [], 0, [], {}
    for root in roots:
        findings, scanned, notes = scan_tree(root, self_path=os.path.abspath(__file__))
        per_root[root] = scanned
        total += scanned
        all_notes += notes
        tag = os.path.basename(root.rstrip('/' + chr(92))) or root
        for kind, f, ln, marker in findings:
            all_findings.append((kind, '%s:%s' % (tag, f), ln, marker))
    ok, code, lines = verdict(all_findings, total)
    lines += ['note: ' + n for n in all_notes]
    if args.json:
        print(json.dumps({'scanned': total, 'roots': per_root, 'notes': all_notes,
                          'findings': [{'kind': k, 'file': f, 'line': ln, 'marker': m}
                                       for k, f, ln, m in all_findings]}, ensure_ascii=False))
    else:
        for line in lines:
            print(line)
    return code


if __name__ == '__main__':
    sys.exit(main())
