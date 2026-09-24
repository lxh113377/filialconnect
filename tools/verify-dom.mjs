/**
 * tools/verify-dom.mjs — read-only DOM audit (cheerio parses, never writes).
 *
 * tools/build.py owns the *writing* of head meta and dictionary fallback text,
 * and it does so with regexes. A regex writer plus a regex reader cannot see a
 * mistake both of them make, so this file re-reads every page as a parsed DOM and
 * asserts the two invariants that matter:
 *   1. every [data-i18n] element's text equals the dictionary's EN value
 *      (and the placeholder / aria-label / alt variants);
 *   2. every page's head block carries the canonical / og:url / per-page og:image /
 *      manifest / apple-touch-icon / twitter:card that the rules require.
 * Exit 0 = clean, 1 = drift (with page, key, expected, actual).
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as cheerio from 'cheerio';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const SITE_BASE = 'https://lxh113377.github.io/filialconnect';
const read = (p) => readFileSync(join(ROOT, p), 'utf8');
const en = JSON.parse(read('assets/locales/en.json'));

const OG_BY_PAGE = {
  'pages/tutorials.html': 'og-tutorials.png',
  'pages/fraud-database.html': 'og-fraud.png',
  'pages/call-help.html': 'og-call-help.png',
};

const pages = ['index.html']
  .concat(readdirSync(join(ROOT, 'pages')).filter((f) => f.endsWith('.html')).sort().map((f) => 'pages/' + f))
  .concat(['404.html']);

/** Collapse markup/whitespace differences that are not copy differences. */
function norm(value) {
  return String(value).replace(/<br\s*\/?>/gi, '\n')
    .replace(/&nbsp;/gi, ' ').replace(/&amp;/gi, '&').replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>').replace(/&quot;/gi, '"').replace(/&#39;|&apos;/gi, "'")
    .replace(/\s+/g, ' ').trim();
}

const cut = (s) => (s.length > 90 ? s.slice(0, 90) + '…' : s);

function auditText($, fp, problems) {
  $('[data-i18n]').each((_, el) => {
    const $el = $(el);
    const key = $el.attr('data-i18n');
    if (en[key] === undefined) {
      problems.push(`${fp}: data-i18n="${key}" has no dictionary entry`);
      return;
    }
    const got = norm($el.html() === null ? '' : $el.html());
    const want = norm(en[key]);
    if (got !== want) problems.push(`${fp}: [${key}] fallback text drifts\n      dict: ${cut(want)}\n      html: ${cut(got)}`);
  });
  for (const kind of ['placeholder', 'aria-label', 'alt']) {
    $(`[data-i18n-${kind}]`).each((_, el) => {
      const $el = $(el);
      const key = $el.attr(`data-i18n-${kind}`);
      if (en[key] === undefined) {
        problems.push(`${fp}: data-i18n-${kind}="${key}" has no dictionary entry`);
        return;
      }
      const got = norm($el.attr(kind) || '');
      const want = norm(en[key]);
      if (got !== want) problems.push(`${fp}: [${key}] ${kind} drifts\n      dict: ${cut(want)}\n      html: ${cut(got)}`);
    });
  }
}

function auditHead($, fp, problems) {
  const up = fp.startsWith('pages/') ? '../' : '';
  const canonical = fp === 'index.html' ? SITE_BASE + '/' : `${SITE_BASE}/${fp}`;
  const need = [
    [`link[rel="manifest"]`, 'href', `${up}manifest.json`],
    [`link[rel="apple-touch-icon"]`, 'href', `${up}assets/images/icon-192.png`],
    ['link[rel="canonical"]', 'href', canonical],
    ['meta[property="og:url"]', 'content', canonical],
    ['meta[property="og:image"]', 'content', `${SITE_BASE}/assets/images/${OG_BY_PAGE[fp] || 'og-cover.png'}`],
    ['meta[name="twitter:card"]', 'content', 'summary_large_image'],
  ];
  for (const [sel, attr, want] of need) {
    const got = $(sel).first().attr(attr);
    if (got !== want) problems.push(`${fp}: ${sel}@${attr}\n      want: ${want}\n      got : ${got === undefined ? '(missing)' : got}`);
  }
  if ($('head script[src*="assets/vendor/i18next.min.js"]').length
      && !$('head script[src*="assets/js/i18n.js"]').length) {
    problems.push(`${fp}: loads i18next but no dictionary bundle`);
  }
}

function main() {
  const problems = [];
  for (const fp of pages) {
    const $ = cheerio.load(read(fp), { decodeEntities: false });
    auditText($, fp, problems);
    auditHead($, fp, problems);
  }
  if (problems.length) {
    console.log(`FAIL: DOM audit found ${problems.length} issue(s) across ${pages.length} pages`);
    problems.slice(0, 20).forEach((p) => console.log('  - ' + p));
    if (problems.length > 20) console.log(`  … ${problems.length - 20} more`);
    process.exit(1);
  }
  let nodes = 0;
  for (const fp of pages) {
    nodes += cheerio.load(read(fp))('[data-i18n]').length;
  }
  console.log(`verify-dom: ${pages.length} pages clean, ${nodes} [data-i18n] nodes agree with assets/locales/en.json`);
}

main();
