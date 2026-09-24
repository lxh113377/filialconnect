// Performance ground-truth probe. CI reports only the audits that *fail* a budget,
// which leaves the actual scores unmeasured. This runs Lighthouse over every URL the
// budgets already declare and writes down the numbers, so "performance" can be argued
// from measurement instead of from the absence of a red light.
//
//   node tools/perf-probe.mjs [--runs=1] [--profile=desktop|mobile|both]
//                             [--out=reports/perf-baseline.json] [--json]
//
// Needs a Chrome/Edge binary. If none is discovered the probe exits 2 with instructions
// rather than emitting an empty baseline (an empty baseline reads as "all good").

import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import lighthouse from 'lighthouse';
import * as chromeLauncher from 'chrome-launcher';
import desktopConfig from 'lighthouse/core/config/desktop-config.js';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => readFileSync(join(ROOT, p), 'utf8');
const argv = Object.fromEntries(
  process.argv.slice(2).map((a) => {
    const m = /^--([^=]+)(?:=(.*))?$/.exec(a) || [];
    return [m[1], m[2] === undefined ? true : m[2]];
  }),
);

const PORT = Number(process.env.LHCI_PROBE_PORT || 8899);
const RUNS = Number(argv.runs || 1);
const PROFILE = argv.profile || 'both';
const OUT = join(ROOT, argv.out || (argv.only ? '.perf-probe-scratch.json' : 'reports/perf-baseline.json'));
const CATEGORIES = ['performance', 'accessibility', 'best-practices', 'seo'];

/** The budgets file is the single source for which pages exist — reuse, don't re-declare. */
function profileConfig(name) {
  const file = name === 'mobile' ? 'lighthouserc.mobile.json' : 'lighthouserc.json';
  const cfg = JSON.parse(read(file)).ci;
  const settings = cfg.collect.settings || {};
  const flat = cfg.assert.assertions || {};
  const matrix = cfg.assert.assertMatrix || [];
  const declared = Object.keys(flat).length ? flat : matrix[0]?.assertions || {};
  const budgets = Object.fromEntries(
    Object.entries(declared).map(([k, v]) => [
      k,
      { level: Array.isArray(v) ? v[0] : v, minScore: Array.isArray(v) ? v[1].minScore : null },
    ]),
  );
  return {
    name,
    file,
    // The rc file owns *which pages* exist; the port belongs to this probe's server, so
    // rebind it rather than assuming the two agree.
    urls: cfg.collect.url.map((u) => u.replace(/^(https?:\/\/127\.0\.0\.1):(\d+)/, `$1:${PORT}`)),
    budgets,
    budgetExempt: matrix
      .filter((row) => String(row.assertions?.['categories:seo'] || '').match(/^(off|warn)$/))
      .map((row) => ({ pattern: row.matchingUrlPattern, level: row.assertions['categories:seo'] })),
    lighthouse:
      name === 'mobile'
        ? {
            extends: 'lighthouse:default',
            settings: {
              formFactor: 'mobile',
              screenEmulation: settings.screenEmulation,
              throttlingMethod: 'simulate',
            },
          }
        : desktopConfig,
  };
}

function findChrome() {
  if (process.env.CHROME_PATH && existsSync(process.env.CHROME_PATH)) return process.env.CHROME_PATH;
  const candidates = [
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ];
  return candidates.find((p) => existsSync(p)) || null;
}

function serveStatic() {
  const parent = join(ROOT, '..');
  const child = spawn(
    process.env.PYTHON || 'python3',
    ['-m', 'http.server', String(PORT), '--bind', '127.0.0.1', '--directory', parent],
    { stdio: 'ignore' },
  );
  return {
    child,
    // A stale server already holding the port answers happily, and then every number
    // below describes some old copy of the tree. Prove the bytes match the disk or stop.
    verify: async () => {
      const fp = join(ROOT, 'assets', 'css', 'main.css');
      const disk = readFileSync(fp);
      for (let i = 0; i < 40; i++) {
        try {
          const r = await fetch(`http://127.0.0.1:${PORT}/filialconnect/assets/css/main.css`);
          if (r.ok) {
            const net = Buffer.from(await r.arrayBuffer());
            if (net.equals(disk)) return { ok: true, sha: disk.subarray(0, 8).toString('hex') };
            return { ok: false, why: `served main.css (${net.length}B) != on disk (${disk.length}B) — is another server holding port ${PORT}?` };
          }
        } catch {}
        await new Promise((res) => setTimeout(res, 500));
      }
      return { ok: false, why: `nothing served at http://127.0.0.1:${PORT}/filialconnect/ after 20s` };
    },
  };
}

const median = (xs) => {
  const s = xs.filter((x) => typeof x === 'number').sort((a, b) => a - b);
  if (!s.length) return null;
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
};

/**
 * A single sample cannot tell a slow page from a busy laptop, and the CI gate only ever
 * shows the median, so the spread is the part that gets thrown away. Keep it.
 */
const spread = (xs) => {
  const s = xs.filter((x) => typeof x === 'number');
  return s.length ? { min: Math.min(...s), median: median(s), max: Math.max(...s) } : null;
};

/** Audits that actually cost score: a failing audit with weight 0 is informative only. */
function costedAudits(lhr) {
  const out = [];
  for (const cat of Object.values(lhr.categories)) {
    for (const ref of cat.auditRefs || []) {
      const weight = ref.weight === undefined ? 1 : ref.weight;
      if (weight <= 0) continue;
      const audit = lhr.audits[ref.id];
      if (!audit || audit.score === null || audit.score >= 1) continue;
      out.push({
        audit: ref.id,
        score: Number(audit.score.toFixed(2)),
        weight: Number(weight.toFixed(2)),
        cat: cat.id,
        // Without the offending node the number is not actionable, and re-running the
        // probe to find out is what made this defect survive six rounds.
        why: (audit.details?.items || []).slice(0, 4).map((it) => {
          const n = it.node || {};
          return [n.selector || it.url || it.entity || '?', String(it.explanation || it.failureMessage || it.reason || '').slice(0, 200)]
            .join(' :: ')
            .trim();
        }),
      });
    }
  }
  return out.sort((a, b) => b.weight * (1 - b.score) - a.weight * (1 - a.score));
}

const KEYS = {
  'first-contentful-paint': 'FCP',
  'total-blocking-time': 'TBT',
  'largest-contentful-paint': 'LCP',
  'cumulative-layout-shift': 'CLS',
  'speed-index': 'SI',
};

async function probeUrl(url, lighthouseConfig) {
  // One browser per URL. Sharing a profile across URLs lets the service worker precache
  // answer page 2..N from whatever it stored, so the last CSS you edited is not the last
  // CSS Lighthouse saw. Measured the hard way: call-help scored a11y 0.96 in a shared
  // profile and 1.00 in a clean one, with the same stylesheet on disk.
  const chrome = await chromeLauncher.launch({
    chromePath: lighthouseConfig.chromePath,
    chromeFlags: ['--no-sandbox', '--disable-gpu', '--headless=new'],
  });
  const samples = [];
  try {
    for (let i = 0; i < RUNS; i++) {
      const runner = await lighthouse(url, { port: chrome.port, output: 'json', logLevel: 'error' }, lighthouseConfig.lighthouse);
      const lhr = runner.lhr;
      const scores = Object.fromEntries(CATEGORIES.map((c) => [c, lhr.categories[c]?.score ?? null]));
      if (CATEGORIES.every((c) => scores[c] === null)) {
        throw new Error(`${url}: Lighthouse returned no scores (page not served? probe aborted instead of writing an empty baseline)`);
      }
      const cwv = {};
      for (const [id, label] of Object.entries(KEYS)) {
        const v = lhr.audits[id]?.numericValue;
        if (typeof v === 'number') cwv[label] = label === 'CLS' ? Number(v.toFixed(4)) : Math.round(v);
      }
      samples.push({ scores, cwv, failing: costedAudits(lhr), version: lhr.lighthouseVersion });
    }
  } finally {
    try {
      await chrome.kill();
    } catch (e) {
      process.stderr.write(`(chrome cleanup noise on ${url}: ${e.code || e.message})\n`);
    }
  }
  const range = {};
  for (const c of CATEGORIES) {
    const vals = samples.map((s) => s.scores[c]).filter((v) => v !== null);
    range[c] = vals.length > 1 ? { min: Math.min(...vals), max: Math.max(...vals) } : { min: vals[0], max: vals[0] };
  }
  return {
    url,
    lighthouse: samples[0].version,
    scores: Object.fromEntries(CATEGORIES.map((c) => [c, median(samples.map((s) => s.scores[c]))])),
    score_range: range,
    cwv: samples.reduce((a, b) => (b.cwv.CLS > a.cwv.CLS ? b : a)).cwv,
    failing_audits: samples.reduce((a, b) => (b.failing.length > a.length ? b : a)).failing,
  };
}

function renderTable(rows, title) {
  const pct = (v) => (v === null ? ' n/a' : (v * 100).toFixed(0).padStart(4));
  const rng = (r) => {
    const { min, max } = r.score_range.performance;
    return min === max ? '     ' : `(${(min * 100).toFixed(0)}-${(max * 100).toFixed(0)})`;
  };
  const line = (r) =>
    `  ${pct(r.scores.performance)} ${pct(r.scores.accessibility)} ${pct(r.scores['best-practices'])} ${pct(r.scores.seo)} ${rng(r)}  ` +
    `${String(r.cwv.LCP ?? '-').padStart(6)} ${String(r.cwv.CLS ?? '-').padStart(7)} ${String(r.cwv.TBT ?? '-').padStart(5)}  ${r.page}`;
  return (
    `\n${title}\n` +
    `   perf   a11y   bp    seo    perf范围   LCPms    CLS  TBTms  page\n` +
    rows.map(line).join('\n') +
    `\n   ${rows.length} pages, ${RUNS} run(s) each.` +
    (rows.some((r) => r.budget_breach.length)
      ? `\n   BUDGET BREACH: ${rows.filter((r) => r.budget_breach.length).map((b) => `${b.page} -> ${b.budget_breach.join(', ')}`).join(' | ')}`
      : `\n   All declared budgets met.`)
  );
}

async function main() {
  const chromePath = findChrome();
  if (!chromePath) {
    console.error('No Chrome/Edge found. Set CHROME_PATH to a Chrome or Edge binary and retry.');
    process.exit(2);
  }
  const server = serveStatic();
  const check = await server.verify();
  if (!check.ok) {
    server.child.kill();
    console.error(`Refusing to measure: ${check.why}`);
    process.exit(3);
  }
  const profiles = PROFILE === 'both' ? ['desktop', 'mobile'] : [PROFILE];
  const result = {
    generated_utc: new Date().toISOString(),
    runs_per_url: RUNS,
    port: PORT,
    served_css_head: check.sha,
    chrome: chromePath.replace(/\\/g, '/'),
    isolation: 'one browser instance per URL (a shared profile lets the service worker answer later pages from an earlier cache)',
    profiles: {},
  };
  const tables = [];
  try {
    for (const name of profiles) {
      const cfg = profileConfig(name);
      const rows = [];
      const only = argv.only ? String(argv.only) : null;
      for (const url of cfg.urls.filter((u) => !only || u.includes(only))) {
        const r = await probeUrl(url, { chromePath, lighthouse: cfg.lighthouse });
        const page = url.replace(/^https?:\/\/127\.0\.0\.1:\d+\//, '').replace(/^filialconnect\/?$/, 'index.html');
        const breach = [];
        for (const [cat, got] of Object.entries(r.scores)) {
          const b = cfg.budgets[`categories:${cat}`];
          const exempt = cfg.budgetExempt.some((e) => new RegExp(e.pattern).test(url));
          if (b && got !== null && got < b.minScore && !(exempt && cat === 'seo')) {
            breach.push(`${cat} ${got} < ${b.minScore}${b.level === 'warn' ? ' (warn-level)' : ''}`);
          }
        }
        rows.push({ page, ...r, budget_breach: breach });
        process.stderr.write(`  [${name}] ${page} done\n`);
      }
      result.profiles[name] = { source: cfg.file, budgets: cfg.budgets, budget_exempt: cfg.budgetExempt, pages: rows };
      tables.push(renderTable(rows, `Lighthouse ${name} — ${cfg.file} URL set`));
    }
    result.summary = summarize(result);
  } finally {
    server.child.kill();
  }

  mkdirSync(dirname(OUT), { recursive: true });
  writeFileSync(OUT, JSON.stringify(result, null, 2) + '\n', 'utf8');
  if (argv.json) console.log(JSON.stringify(result, null, 2));
  else console.log(tables.join('\n') + `\n\nbaseline written: ${OUT}`);
}

function summarize(probe) {
  const out = {};
  for (const [name, prof] of Object.entries(probe.profiles)) {
    const pages = prof.pages;
    if (!pages.length) {
      out[name] = { pages: 0, min: {}, worst_page: null, budget_breaches: [], distinct_failing_audits: [] };
      continue;
    }
    const lowest = (c) => Math.min(...pages.map((p) => p.scores[c]).filter((v) => v !== null));
    out[name] = {
      pages: pages.length,
      min: Object.fromEntries(CATEGORIES.map((c) => [c, lowest(c)])),
      worst_page: pages.reduce((a, b) => (b.scores.performance < a.scores.performance ? b : a)).page,
      budget_breaches: pages.filter((p) => p.budget_breach.length).map((p) => `${p.page}: ${p.budget_breach.join(' / ')}`),
      distinct_failing_audits: [...new Set(pages.flatMap((p) => p.failing_audits.map((f) => f.audit)))].sort(),
    };
  }
  return out;
}

main().catch((e) => {
  console.error('probe failed:', e.message);
  process.exit(1);
});
