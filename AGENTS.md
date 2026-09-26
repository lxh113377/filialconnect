# AGENTS.md — filialconnect

Rules for anyone (human or agent) changing this repository. They exist because these specific
failures happened here and cost a round each time they were discovered late.

## Before claiming anything is done

```bash
python tools/test_build.py            # structure, i18n, copy-truth, budgets, determinism
python tools/build.py check           # python-owned derived files in sync
node tools/build.mjs check            # i18n.js / sitemap / lighthouserc / sw.js in sync
python tools/stage-site.py check      # the deploy/probe file lists match reports/deploy-staging.json
python tools/check-i18n.py            # EN/ZH key symmetry and data-i18n coverage
python tools/contrast_coverage.py --check   # contrast audit denominator ledger
python tools/judge_coverage.py --selftest  # the ledger generator may not read git/fs/other tools
node_modules/.bin/htmlhint "index.html" "pages/*.html"

python tools/verify-live.py           # after a deploy: does production equal this commit? (needs net)
python tools/package-offline.py --verify   # the offline ZIP is reproducible from one commit
```

A release is cut with `python tools/release.py` (dry run) then `--apply`. It refuses to tag when
the sources disagree or CI is red; that refusal is the correct outcome, not an obstacle.

## Derived files

`index.html`, `pages/*.html`, locales are generated from `content/tutorials.json` by
`tools/build.py`. Edit the content file and rebuild — hand-editing generated pages drifts and
`check` will fail. The same URL list is owned by `lighthouserc*.json`; adding a page means
rebuilding, not appending by hand (`t_perf_coverage` fails otherwise).

## Recurring failure classes

1. **Copy promising a capability the static site does not have.** Four defects in this repo started
   as marketing copy asserting behaviour ("has been notified", "screenshot of your screen"). If the
   page says something happens, there must be code that does it; `t_promises` guards the fixed wordings.
2. **A gate that measures a shrinking denominator.** The contrast audit judged only pairs whose
   foreground and background were in one rule block, so the footer's 1.55:1 was invisible to it while
   axe caught it in CI. Any new judge ships with its coverage recorded (`reports/…-coverage.json`)
   and a positive floor assertion, so a green pass cannot quietly mean "we looked at less".
3. **Silent degradation.** The search panel hid itself when the index was missing, which read as
   success. Degrade observably: set a state attribute, announce in the live region.
4. **Vacuous passes.** A filter matching zero URLs printed "All declared budgets met"; a probe that
   mixed the median score with the worst sample's timings reported "LCP 9754ms, perf 96". Every
   measurement prints its own sample count and run count; zero input never records PASS.
5. **A tool that is not wired into a blocking chain is a half-finished tool.** Judges live in
   `tools/test_build.py` or CI, not in a README note someone has to remember.
6. **A list maintained by hand in two places stops being true.** The deploy file set was copied by
   hand into `deploy-pages.yml` and `ci.yml`, and the two had already drifted (CI served generator
   input; Pages served the service worker CI never measured). `tools/stage-site.py` is now the only
   enumerator and `t_deploy_staging` fails if a workflow keeps a private copy of the list. The same
   class covers public copy that is not a file: the repository's About box kept selling the site
   on what it does not use, long after that framing was revoked - because no gate looked outside
   the working tree.
7. **A number written in prose rots silently.** Three documents quoted a self-test count that had
   doubled. Do not restate measurable quantities in copy - either point at the command that prints
   it, or pin it with a judge (`t_public_metadata` pins the one number the About box commits to).

## Attribution before action

When two runs disagree, diff the artifact bytes before theorising. When CI is red, read the tool's
own log and the failing audit's own `target`/`node` before touching CSS — the footer fix was lost for
two rounds because the diagnosis guessed at the wrong element. Every claim in a report needs a
command that would falsify it, and a mutation that turns the new check red.

## Tool wiring, declared (round 27)

`tools/gate_wiring.py --check` (a CI step) reads `tools/gate-wiring.json` and fails if a tool in
`tools/` declares no consumer, declares CI but is named by no workflow, or is hand-only without
being written here. Declared hand-only or release-only:

- `ci-audit-nodes.py` - hand-only *by classification*, and this is the honest label: it is
  named by a CI step, but that step is `continue-on-error: true`, so its verdict cannot
  redden a run. `gate_wiring` no longer credits a non-blocking step as wiring - a tool
  that can only print is a diagnostic, and pretending otherwise is how the round-7
  `warn`-level budget hid a 0.63 SEO score for six rounds. Read it in a failed run's log.
- `perf-probe.mjs` - hand-only. It feeds the blocking `t_perf_measurement` budget, and a real
  browser run does not belong in the CI job, so nothing regenerates its input automatically.
  `t_perf_provenance` pins what it can: the Lighthouse version and the sample sizes recorded in
  `reports/perf-baseline.json`. Re-run it before changing budgets: `node tools/perf-probe.mjs`.
- `verify-live.py` - a job of the Pages workflow, so it runs on every push to `main` but never
  on a pull request (it needs the deployed site). It exits 2 (`UNVERIFIED`) when the network is
  unreachable rather than pretending, and it probes build outputs by the names the live manifest
  publishes; hashed fragment files are reported as unnameable instead of silently skipped.
- `release.py`, `package-offline.py` - declared `test` because the suite really executes them
  (`classify_checks()` over five fixtures, `pkg.build()` twice for reproducibility), even though
  their only *human* use is the release path.

## Git and paths

Never force-push, never move a published tag, never `git add -A` (this worktree sits inside a shared
parent repository with other projects). Commit with named paths and check `git show --stat`. Docs and
logs use forward slashes; patch scripts must be written as files (a shell-embedded non-raw string
turns `\b` into a real backspace byte — `t_no_control_bytes` is the result).

## What is deliberately not here

No backend, no analytics, no service-worker push, no real notification: the site must work offline
from a ZIP on a phone. Accessibility and legibility are not configurable, so there is no theme
toggle by design. Having no dependencies is not an aim — Pagefind, Workbox, Lighthouse and axe are
dependencies on purpose; prefer a mature library over a hand-rolled equivalent.
