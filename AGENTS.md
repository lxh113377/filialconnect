# AGENTS.md — filialconnect

Rules for anyone (human or agent) changing this repository. They exist because these specific
failures happened here and cost a round each time they were discovered late.

## Before claiming anything is done

```bash
python tools/test_build.py            # structure, i18n, copy-truth, budgets, determinism
python tools/build.py check           # python-owned derived files in sync
node tools/build.mjs check            # i18n.js / sitemap / lighthouserc / sw.js in sync
python tools/stage-site.py check      # the deploy/probe file lists match reports/deploy-staging.json
python tools/stage-site.py explain assets/… # why is this file being served (empty = a stray)
python tools/check-i18n.py            # EN/ZH key symmetry and data-i18n coverage
python tools/contrast_coverage.py --check   # contrast audit denominator ledger
python tools/judge_coverage.py --selftest  # the ledger generator may not read git/fs/other tools
node_modules/.bin/htmlhint "index.html" "pages/*.html"

python tools/verify-live.py           # after a deploy: does production equal this commit? (needs net)
python tools/ci-watch.py --once       # after a push: green / red(+repair hint) / UNVERIFIED (needs net)
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
8. **A directory-wide shipping rule hides stray files.** `assets/` is shipped wholesale, so nothing
   structurally stops an unreferenced file riding into production (this was #145: a contest logo and
   the locale JSONs shipped, referenced by no page, with no written why). `t_deploy_reasons` now
   demands every shipped asset be explained by a reference, an og:image/manifest/dynamic rule, or
   `SHIPPED_WITHOUT_REFERENCE` with a reason. Ship for a reason or do not ship.
9. **A verification harness that reaches back into the live repository.** Two harnesses junctioned a
   throwaway `git worktree` to this repo's own `node_modules` on 2026-09-26 and `git worktree remove
   --force` followed the link, deleting 744 packages - twice, after the rule had already been written
   into a docstring. No file here may create a filesystem link, and `t_no_link_code` fails if one does
   (the detector's both-directions proof is `python tools/link_guard.py --selftest`). Harnesses kept
   outside this repository are scanned by their own command, `python _internal/check_harness_links.py`.
   A worktree that needs dependencies installs them inside itself; it does not link to the live tree.

## Attribution before action

When two runs disagree, diff the artifact bytes before theorising. When CI is red, read the tool's
own log and the failing audit's own `target`/`node` before touching CSS — the footer fix was lost for
two rounds because the diagnosis guessed at the wrong element. Every claim in a report needs a
command that would falsify it, and a mutation that turns the new check red.

## Triage: 报错特征 → 处置（每条都对应一次真实踩坑）

签名字符串的权威是 `tools/ci-watch.py` 的 `HINTS` 表（`--selftest` 保证它非空且可编译）；本节只是给人看的
速查，改判据文案时**先改那张表**，否则这里会烂（失败类别 7）。

| 日志里的原话 | 真实成因 | 处置 |
|---|---|---|
| `ERR_MODULE_NOT_FOUND` / `Cannot find package` | 缺依赖，**不是**产物漂移 | `npm ci`；worktree 需要依赖就在里面装，绝不链接真仓（`t_no_link_code`） |
| `ABORTED JUDGES: t_xxx` | 某判据崩了 ⇒ 它之后所有判据的结论丢失（含已收集失败的打印） | 先修崩的那条；不要顺手"抬 timeout"或跳过它 |
| `matches this measurement: run: python tools/…` | 生成物/台账过期 | 跑它点名的那个生成器，提交它的输出，别手改台账 |
| `no build input is untracked` | 上一笔提交用了 `git add -u`（漏新文件） | `git add <显式路径>`；收口看 `git show --name-only` |
| 本地全绿、CI 红 | 提交缺件，或台账里抄了随工作树变化的量 | 比对 `git ls-tree` 与本地；把不可移植的字段删掉（不是改 CI 环境） |
| `verify-live … UNVERIFIED` | 网络不可达 | UNVERIFIED ≠ 通过 ≠ 失败；复跑或如实写"未核验" |
| job 数秒失败且 `steps=0` | 没拿到 runner（配额/环境），不是代码错 | 读 `gh api repos/<slug>/check-runs/<id>/annotations` |
| `gh api` 返回 404（GET） | 参数被当 body 发了 | GET 的参数拼进 query string，`-f` 是写请求用的 |
| 后台任务通知"exit 0" | 那是 shell 最后一条命令的码，不是被测对象的结论 | 读日志里的 `rc=`，或 `gh run view --json conclusion` |

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
- `ci-watch.py` - hand-only by classification, and that is the honest label: nothing in a CI job can
  watch CI. It is the post-push waiter - `python tools/ci-watch.py --once` reuses `release.ci_verdict`
  (so the two tools can never disagree) and on red prints a named repair hint from its `HINTS` table
  plus the log tail. Exit 0 green / 1 red / 2 pending-or-UNVERIFIED; `--selftest` covers the
  signature table and the state→exit mapping offline. A client hook may call it after `git push` -
  that config lives on the machine, not in this repository, so wiring it is a local decision.
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
