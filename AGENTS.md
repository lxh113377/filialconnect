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
rebuilding, not appending by hand (`t_perf_coverage` fails otherwise). The Triage table below is
generated from `tools/ci-watch.py`'s `HINTS` by `tools/triage.py --write` and verified byte for byte
by `t_triage_copy`; the rows are data, this document is a rendering of them.

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
10. **A declared authority relationship that nothing verifies stops being true.** `AGENTS.md` claimed
   the triage table's authority was `tools/ci-watch.py`'s `HINTS` and that the section was "only the
   human copy". One round later both sides still had nine rows - so a length comparison is green -
   while three rows existed only in the code and three only in the document, and two document rows
   were not log signatures at all and therefore could never fire. If a file claims to render another
   file's data, the render must be generated and byte-verified (`python tools/triage.py --check`,
   judge `t_triage_copy`); if it cannot be generated, the claim must not be written. The same rule
   applies to artifacts, not just prose: `legacy-report-findings.json` sat in the archive with no
   generator and no consumer, which is a fossil of a number, not a ledger.
11. **A mutation fixture that does not change its input proves nothing, and a restore that prints
   `rc=0` proves nothing either.** Round 37 shipped a "violation" whose search string was not in the
   value being replaced, so the bytes came back identical and the case looked like a control. Round 38
   found the mirror-image defect: the same batteries restored with a bare `git checkout -- <path>`,
   which exits 0 whether or not anything was dirty. Both shapes are refused by
   `python _internal/fixture_guard.py --selftest` and `_internal/restore_guard.py --selftest`, and
   `_internal/audit_fixtures.py --verify` (a close-out gate) enumerates every battery and fails a new
   one that has neither guard. Two more forms measured while writing them: opening a file `'wb'`
   before reading it back truncates the copy to nothing (and an empty copy is a prefix of
   everything, so it also "passed"), and "is the path in HEAD" is not "are these bytes in HEAD" on an
   append-only log. Read first, then write; compare content, never existence.
12. **A counter that knows two shapes prints `0` for a population it cannot see, and the zero gets
   read as a finding.** `_internal/audit_fixtures.py` printed `cases=` from a detector that only
   recognised `case(...)` calls and M/A-labelled tuples, so on 2026-09-27 eleven of its fifteen
   batteries printed `cases=0` - including every one that records verdicts through
   `results[k] = ...`, `checks.append(...)` or a `*_CASES = [...]` list. Nothing was miscounted, but
   the number was unowned: no reader could tell "measured nothing" from "runs no cases", which is the
   shrinking-denominator class wearing a diagnostic column. `case_nodes()` now enumerates the shapes
   present in the population, counts the **union** of nodes (a tuple inside a `CASES` list is one
   case, not two shapes), the column is labelled `sites=`, and a battery added after the rule with
   `sites=0` is refused by name (`must_number`) alongside `must_guard` - and both reasons print,
   because the first red must not swallow the second. A zero is still allowed to exist; it is no
   longer allowed to be silent.
13. **A second top-level `def` with the same name silently replaces the first - and a precondition
   you invented will red-book the wrong party.** Round 40 added a widened `meta_verdict(log, items,
   ok_line)` *above* the round-39 definition in the same module; Python keeps the last binding, so
   the widened signature was dead until a selftest crashed with `TypeError: meta_verdict() takes 1
   positional argument but 3 were given`. This repository has judged the shape since round 20
   (`t_no_duplicate_defs` over `tools/`), but the harness that lives outside the repository had no
   equivalent - so the rule existed and did not reach me. `python _internal/audit_dupes.py --verify`
   (close-out gate 11) now enumerates module-level `def`/`class` names across the archive. Measure
   before wiring: the wide form, which also counted `s = ...` re-assignments, flagged 18 of 86
   modules and 17 of them were one-shot patch scripts where linear rebinding is the design - so the
   judge ships narrowed to callables, with the wide run recorded as the reason. The mirror-image
   mistake the same round made: a new "the tree must be dirty before the reset" precondition reddened
   a case whose mutation was real and whose *own build step* restored the file. Put effectiveness on
   the mutation's receipt (`fixture_guard` per edit), never on a state the system under test is
   allowed to undo.
14. **A verdict cannot see coverage: count the receipts, on both ends of the wire.** Round 40 made
   `verify-live.py` print one `metadata item <field>: match` line per declared field, and the archive
   began importing that vocabulary instead of carrying its own copy - but the *producer* still printed
   the match lines only in a block that runs when nothing differed. So a log carrying one `MISMATCH`
   and no `match` lines read `red` whether the other two fields matched, differed, or were never
   compared: the red verdict was right, and the coverage claim underneath it was unverifiable. The fix
   is the identity `matched + mismatched == len(META_ITEMS)`, printed on the gate's face
   (`items=3/3 matched=2 mismatched=1`), plus a battery that drives the real producer with its network
   call stubbed (`_internal/test_round41_meta_identity_mutations.py`) - a reader-side rule and a
   producer-side behaviour tested against each other, because two ends of one wire drift separately.
   Same-round sibling: an archived one-shot script that has never parsed (`patch_round27_bump.py`,
   `unterminated string literal` since round 27) was **repaired, not excluded** - the escape-only
   rewrite is proved lossless at the byte level before it is written, and the judge keeps naming any
   unparsable file it meets.

15. **A control leg must take its baseline from the population it compares against.** Round 42's new
   battery had a case claiming "adding one workflow moves the count by exactly 1"; it failed, and the
   defect was in the leg, not the tool: the previous case had restored the boundary to the real tree,
   so `before` was counted over 4 shipped workflows while `after` was counted over a 6-file sandbox.
   The assertion was one-to-one in shape and unachievable in fact - which is how a control can look
   rigorous and measure nothing. Same family as the r41 rule that a mutation must enter the predicate
   it claims to test. Before trusting a `before/after` case, print both sides' denominators; if they
   differ by anything other than the change under test, the case is comparing two populations.
   Wiring cost noted too: a new tool under `tools/` must be declared in `tools/gate-wiring.json` and
   both `reports/gate-wiring.json` and `reports/judge-coverage.json` regenerated, or three checks
   fail at once (undeclared consumer, ledger drift, untracked build input) - that is the chain
   telling you the new file has no owner yet.
16. **A hand-counted zero becomes next round's plan table.** Round 42 measured the CI-hygiene
   population with `grep -n "^permissions:\|^  permissions:"`, saw no job-level block, and wrote that
   conclusion into three places: a priority row in the report, the next round's first item, and a
   line in global memory ("this leg is vacuous today"). Round 43 counted the same thing with an
   enumerator: `deploy-pages.yml:59` carries a **four-space** `permissions:` block and the pattern
   had allowed only two. The zero was not uncertain - it was invented by an indentation assumption,
   and everything downstream inherited the invention. Now enforced in code (`tools/ci_hygiene.py`):
   every leg reports its **sample count** on the verdict line (`leg_samples=… untested=…`), a leg
   with no sample is declared untested instead of counting as verified, `coverage_identity_issues()`
   refuses a label that contradicts its own counts, and the battery checks the enumerator against an
   independent scan of the shipped files. Rule: if a number decides a priority, enumerate it -
   a fixed indentation pattern is a guess wearing a measurement.
17. **A control that cannot fail is worse than no control - and a tool that reads no argv still has
   an argv contract.** Two round-43 self-inflicted catches. (a) The duplicated-binding leg added to
   `_internal/audit_dupes.py` was written *from* a real defect and then scored 0 hits on it, because
   it walked into compound statements and let a nested write overwrite the value being compared; only
   its own transcription fixture went red. Attributing a different finding, I built the mirror image
   of that error: on Windows, `subprocess.run(..., env={'PATH': ...})` **does not** test PATH, since
   CPython resolves a bare executable name against the parent's `os.environ` - the "control" returned
   rc=0 and briefly disproved a correct diagnosis. So name the branch a negative control is meant to
   break, then show it break. (b) `build_zip.py` read no arguments at all, so `--help` fell through to
   the build and overwrote that day's deliverable ZIP - the third instance of this family in the
   harness. The fix is structural, not per-accident: a side-effecting script states its argv policy in
   one powerless predicate (`decide()` → build/help/refuse), refuses unknowns by name with rc=2, and
   the refusal is proven by asserting the artefact's bytes and mtime are identical after the attempt.
18. **A writing default must not be reachable by a typo - and a rule that fires on 64 dead files
   gets switched off, not obeyed.** Round 44 inherited "generalise build_zip's argv refusal" as a
   plan item. Enumerated first: 94 of 110 modules write something, and 64 of those are one-shot
   fossil patch scripts that will never be invoked with a flag again, so the blanket rule was
   rejected by its own denominator. The decidable surface is *tools the harness actually invoked*
   (read back out of the newest instrument capture, never hand-listed) intersected with "can write":
   `live=22 writers=19`, of which `tools/gate_wiring.py` - whose **default action rewrites the wiring
   ledger**, so `--chk` silently means "mutate" - and `render_peers_table.py` had no refusal at all.
   Both now route through a powerless `decide()` and prove the refusal path leaves the ledger bytes
   unchanged; the standing judge is `_internal/audit_argv_contract.py --verify` (close-out gate ⑭).
   Gate ⑮ ("every archive artefact a report cites is tracked") then caught itself once: `git ls-files`
   octal-escapes CJK filenames by default, so the report's own name looked untracked until
   `-c core.quotePath=false` was added. Both halves are the same lesson - **size the population
   before writing the rule, and prove the probe can see the thing it claims is missing.**
19. **A declaration is configuration; only a run that used it is evidence - and a test that matches
   the chain's log can be certified by the wrong judge.** Round 45 closed the `permissions:` loop:
   `tools/ci_receipts.py` records, per job-level block, the newest **completed** run (an unfinished
   run is refused: "I expect it to pass" is not a receipt), its commit sha, the job conclusion and
   the exact scopes at capture time; `--check` then requires disk == ledger scope-for-scope, the job
   to have succeeded, and the sha to be reachable in this history. Six counter-cases, including the
   one people forget - a block deleted while its receipt survives (an orphan exemption is the silent
   half of a silent gap). Same round: after `test_round30_page_title_mutations` was moved to run
   `t_page_title` alone instead of the whole chain, case C1 went red immediately - its expected
   string had been satisfied by **another judge's** wording, so the battery had been green while
   never proving the judge it names. Match a finding, never a log; the chain's output is large
   enough for any red to look like yours.

## Attribution before action

When two runs disagree, diff the artifact bytes before theorising. When CI is red, read the tool's
own log and the failing audit's own `target`/`node` before touching CSS — the footer fix was lost for
two rounds because the diagnosis guessed at the wrong element. Every claim in a report needs a
command that would falsify it, and a mutation that turns the new check red.

## Triage: 报错特征 → 处置（每条都对应一次真实踩坑）

权威是 `tools/ci-watch.py` 的 `HINTS`（每行四字段：`sig` 日志里会出现的原话、`pattern` 匹配它的正则、
`cause` 成因、`action` 处置）。下面这张表**不是副本、是生成物**：`python tools/triage.py --write` 写它，
CI 跑 `--check` 逐字节回验，判据 `t_triage_copy` 在链上——因为第 36 轮把它写成"人看的副本"之后，
到第 37 轮实测两边都是 9 行、内容却已错位 3↔3（长度对比会绿，逐行对比才咬人）。
改判据文案 = 改那张表再 `--write`；手改标记之间的表格只会被判红。

<!-- BEGIN:TRIAGE-TABLE generated by `python tools/triage.py --write` - do not hand-edit -->
| 日志里的原话 | 真实成因 | 处置 |
|---|---|---|
| `ERR_MODULE_NOT_FOUND` / `Cannot find package` | 缺依赖，**不是**产物漂移 | run `npm ci` - dependencies are missing, this is not artifact drift; a worktree must never link node_modules from the live repo (t_no_link_code) |
| `no build input is untracked` / `Did you mean --force?` | 上一笔提交用了 `git add -u`（漏新文件） | a commit was made without new files: `git add <paths>` then re-check `git show --name-only`; `git add -u` skips untracked ones |
| `matches this measurement: run: python tools/…` | 生成物/台账过期 | a generated ledger is stale - run the generator its own message names (tools/judge_coverage.py, tools/gate_wiring.py, ...) and commit its output |
| `node half reports no drift` / `i18n.js … out of sync` | 构建顺序反了：node 侧派生件早于 python 侧 | build order is python then node: `python tools/build.py && node tools/build.mjs`, then re-run `node tools/build.mjs check` |
| job 数秒失败且 `steps=0` | 没拿到 runner（配额/环境），不是代码错 | the job never got a runner: read annotations at `gh api repos/<slug>/check-runs/<id>/annotations` - it is not a code failure |
| `ABORTED JUDGES: t_xxx` | 某判据崩了 ⇒ 它之后所有判据的结论丢失（含已收集失败的打印） | a judge crashed instead of reporting: fix that judge first - while it is aborting, the evidence of every later judge is lost |
| `HTTP 404` / `assertion … 404` | `gh api` 的 GET 参数被当 body 发了 | `gh api` GET parameters belong in the query string; `-f` puts them in the body and turns a good path into a 404 |
| `verify-live … UNVERIFIED` | 网络不可达，或线上部署不是被探针的那笔提交 | the live probe could not reach production (network) or the deploy is not the probed commit; UNVERIFIED is not a pass and not a red either |
| `precache revision` / `service worker` | sw.js 早于它的输入生成 | sw.js was generated before its inputs changed - rebuild in order and re-run the determinism judge (t_deterministic_sw) |
| `hand drift: N row(s) differ` | AGENTS.md 的 Triage 表被手改，或 `HINTS` 改了没重生成 | run `python tools/triage.py --write` and commit it; the section between the markers is generated, so hand edits there are not a second opinion (t_triage_copy) |
| `stale receipt` / `malformed receipt` | 报告里的收尾回执不是本次实测（或字段残缺） | re-run `python _internal/closeout_round.py --emit` and paste the whole block again; a receipt from last round is not evidence this round closed |
| `unknown permission key` / `declared untested` | 工作流里写了 GitHub 不认识的权限键（拼错即静默失权），或判据报告自称某腿无样本却与样本数矛盾（块锚定把 `runs-on` 之类误当权限项） | 按 `tools/ci_hygiene.py` 的 `KNOWN_SCOPES` 改键名或删掉那行；若是锚定问题，修 `job_blocks()` 的缩进回引用，不要放宽判据或把键加进豁免名单 |
<!-- END:TRIAGE-TABLE -->

两条**不是日志签名**的操作纪律（它们没法被 grep 到，所以不进表；表只收"原话"）：

- **本地全绿、CI 红** ⇒ 提交缺件（`git add -u` 漏未跟踪新件），或台账里抄了随工作树变化的量。
  比对 `git ls-files` 与本地，把不可移植的字段删掉——不是去改 CI 环境。
- **后台任务通知"exit 0"** ⇒ 那是 shell 最后一条命令的码，不是被测对象的结论。
  读日志里的 `rc=`，或 `gh run view --json conclusion`。

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
