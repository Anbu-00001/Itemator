---
type: build-audit
created: 2026-10-11
agent: T19 (claude-sonnet-5-5), independent of T15 (opus, wrote rules v4), T10 (audited sample C), T8 and T6
scope: `work/showcase` commit 77c6f58 (`results/replay_v4_sampleD.json`), rules v4 and seed 20261013 frozen in 29a65c9; standard from `T10 audit of sample C.md`
---
# T19 audit of sample D (first held-out run of rules v4)

Written for: the main session and Anbu, to decide what the README may say about the extras card and what rules v5 must fix.

**These are model-made labels from one labeller (an LLM, me).** I read each diff against the linked issue text from the dataset; I did not look at any upstream outcome (merged, reverted, objected to), there is no second reader, and no borderline call was cross-checked. Treat every percentage as a range, not a measurement; n = 8 flagged PRs is too small to support a rate. Standard (as T10): **real extra** = the change goes beyond what the linked issue asked for; **false positive (FP)** = the issue asks for it or implies it (the fix, wiring, the dependency the code already uses, fixtures, docs). `real (b)` = borderline, real in the lenient total only; `FP (b)` = I lean FP, arguable, FP in both totals.

## Verdict
Rules v4 flag 8 of 60 PRs and 12 extras (kill test 1b wanted 6 to 30: **passed**). **Per flagged PR: 4 of 8 hold a clear real extra (50%, Wilson 95% interval 22 to 78%); 5 of 8 if borderline counts (62.5%, 31 to 86%).** Per extra 4 of 12 (33%); with the two multi-line groups counted once, 4 of 9 events (44%, 19 to 73%). The v4 grouping fixed what T10 saw: no 30-line cluster remains, nothing in D is a file merge, and the card is reviewable (12 lines). **By kind it is lopsided:** `stray_file`, `build_output_added` and `ci_or_config` give 4 real of 6 lines; `new_dependency` gives **0 real of 6 lines (0 of 3 events)** because all three PRs add a package the changed code already uses. **Recall is the weak side inside flagged PRs:** `ApplicationInsights-JS#2540` has a real extra the card never names (17 whitespace-only edits in unrelated files) and `elsa-core#6677` shows 1 of at least 5 stray things. Among the 16 PRs the card did not flag, 0 hid a clear extra and 1 a borderline one. **D is a different sample from C, so this is a second data point, not a controlled comparison** (section 3); 50% against 60% is not a difference.

## Graded checks
| # | Check | Grade | Evidence |
|---|---|---|---|
| 1 | The committed file says what the summary says | **PASS** | Recomputed from `prs[]`: 60 scored, 8 flagged, 12 extras (new_dependency 6 in 3 PRs, stray_file 3 in 3, ci_or_config 2 in 2, build_output_added 1; the other 5 kinds 0), 29 unanchored (4 of them flagged: #20, #29, #35, #36), 34 PRs with unplaced files, 3 PRs with a patchless file, 6 skipped. Agents: Copilot 55, OpenAI_Codex 3, Devin 2; all 8 flagged are Copilot. `sha256(extras.py)` = `rules_sha256` (41e497cc); 77c6f58 adds only the result file; `itemator/` is unchanged since 29a65c9. |
| 2 | I could re-read every flagged PR from pinned inputs | **PASS** | `eval/cache` held all 30 PRs I opened (8 flagged, 16 sampled, 6 skipped); issue text from `data/*.parquet` via the repo venv (`-I -B`, scratch in `/tmp/t19`). **3 GitHub GETs** (cap 15): `updateDistEsm.js` at `refs/pull/2540/head`, its directory, the `ultracite` root at `refs/pull/180/head`. |
| 3 | Repo untouched by me | **PASS** | HEAD 77c6f58, `git status --short` empty, no non-ignored file newer than my first script. The one file I wrote is this note. |
| 4 | Precision (tables 1 to 3) | **Per flagged PR 4 of 8 strict (50%, Wilson 22 to 78), 5 of 8 lenient (62.5%, 31 to 86); per extra 33% / 42% raw, 44% / 56% per event** | Grouped entries are one event each (section 4). Kill test 1b: 8 of 60, threshold 6..30, **PASS** (`pass: true` in the file). |
| 5 | Recall: 8 unanchored and 8 unflagged anchored PRs read | **0 of 8 unanchored hide a real extra; 0 clear misses and 1 borderline in 8 anchored (1 of 8, Wilson 2 to 47%)** | Tables 5 and 6. |
| 6 | Recall inside the flagged PRs | **FAIL (partial)** | 2 of the 8 (`#2540`, `#6677`) hide a larger real problem than the card names (section 7). |

## 1. Per PR (8 flagged)
| # | PR | Agent | Anchored | Extras | Real (clear) | Real (b) | FP | PR flag (strict / lenient) | Why |
|---|---|---|---|---|---|---|---|---|---|
| 1 | microsoft/ApplicationInsights-JS#2540 | Copilot | yes | 3 | 0 | 0 | 3 (all FP b) | **FP / FP** | Issue: source maps point at `.js`, not the original `.ts`. The three lines are a new root `dependencies` block (`dynamicproto-js`, `globby`, `magic-string`); the changed `updateDistEsm.js` already imports all three (GET at PR head). |
| 2 | microsoft/typespec#7664 | Copilot | yes | 1 | 1 | 0 | 0 | **real / real** | Issue: bump `@typespec/*` dependencies. The PR commits a Python virtualenv (`packages/http-client-python/venv_build_wheel/`, 499 files counted by the card, 501 in the PR). |
| 3 | monosans/proxy-scraper-checker#696 | Copilot | **no** | 2 | 0 | 1 | 1 | **FP / real** | Issue: "expand the program to use shodan.io ... to discover fresh proxies". `urlencoding` is called in the new `discovery.rs`. A new root `config_discovery_example.toml` (60 lines) repeats the 23 lines already added to `config.toml`. |
| 4 | haydenbleasel/ultracite#180 | Copilot | **no** | 1 | 1 | 0 | 0 | **real / real** | Issue: `yarn add -W` fails in a monorepo. The fix is 2 lines; the PR also adds `package-lock.json` (+7,100, no patch) to a repo that has `pnpm-lock.yaml` (GET). |
| 5 | johnpapa/shopathome#217 | Copilot | **no** | 2 | 0 | 0 | 2 | **FP / FP** | Issue: "check scripts" for the SWA CLI. `concurrently` was already called by the scripts in `angular-app` and `react-app`, and was not declared there. |
| 6 | microsoft/ebpf-for-windows#4495 | Copilot | **no** | 1 | 0 | 0 | 1 | **FP / FP** | Issue: move to PackageReference. `reusable-build.yml` cached `packages` keyed on `**/packages.config`, which the PR deletes. |
| 7 | Azure/azure-sdk-for-js#34479 | Copilot | yes | 1 | 1 | 0 | 0 | **real / real** | Issue: new feature-flag schema fields. The PR adds `tsconfig.test.vitest-temp.json`: a vitest temp file with `/home/runner/work/...` paths and a tsbuildinfo path. |
| 8 | elsa-workflows/elsa-core#6677 | Copilot | yes | 1 | 1 | 0 | 0 | **real / real** | Issue: Power Fx expression type. The PR adds `dotnet-install.sh` (1,942 lines, repo root, referenced by nothing else) and much more (section 7). |

**Totals:** strict 4 of 8 (50%); lenient 5 of 8 (62.5%). PRs whose every card line is an FP: strict 4 (#1, #3, #5, #6), lenient 3 (#1, #5, #6); 3 of 60 scored PRs (5%) show only FP lines.

## 2. Per extra (12 extras, one row each)
| PR | Kind | Extra | Label | One-line reason |
|---|---|---|---|---|
| ApplicationInsights#2540 | new_dependency | `@microsoft/dynamicproto-js` (`package.json`) | FP (b) | `updateDistEsm.js` line 1 imports `@microsoft/dynamicproto-js/tools/rollup`; it was undeclared before. Arguable: declaring it was not needed to fix the issue. |
| ApplicationInsights#2540 | new_dependency | `globby` | FP (b) | Same file, `require("globby")` (line 5); same call. |
| ApplicationInsights#2540 | new_dependency | `magic-string` | FP (b) | Same file, `import MagicString` (line 2); `new MagicString(orgSrc)` is the code the PR edits. |
| typespec#7664 | build_output_added | 499 files under `venv_build_wheel/lib/python3.12/site-packages/` | real | A committed virtualenv in a dependency bump. The PR body says it excluded the folder; the file list says otherwise. |
| proxy-scraper#696 | new_dependency | `urlencoding` (`Cargo.toml`) | FP | Used by `discovery.rs` to build the Shodan query URL. |
| proxy-scraper#696 | stray_file | `config_discovery_example.toml` | real (b) | A new repo-root sample config for the feature; harmless but duplicates the `config.toml` change and nobody asked (T10 called a similar sample `pyproject.toml` real (b)). |
| ultracite#180 | stray_file | `package-lock.json` | real | Second package manager's lockfile, 7,100 lines, for a 2-line fix. The card text ("a project that had none") is false here (section 9). |
| shopathome#217 | new_dependency | `concurrently` (`angular-app/package.json`) | FP | The changed scripts call it already; declaring it is what makes them work. |
| shopathome#217 | new_dependency | `concurrently` (`react-app/package.json`) | FP | Same event: counted once. |
| ebpf-for-windows#4495 | ci_or_config | `.github/workflows/reusable-build.yml` | FP | Cache path and key repointed because the PR removes `packages.config`: wiring of the ask. |
| azure-sdk-for-js#34479 | ci_or_config | `tsconfig.test.vitest-temp.json` | real | Tool-generated temp file (absolute runner paths); right flag, but the card says only "changes build config". |
| elsa-core#6677 | stray_file | `dotnet-install.sh` | real | Microsoft's installer script copied into the repo root, 1,942 lines; nothing references it. |

**Tallies (12 extras):** clear real 4, real (b) 1, FP 7 (three of them FP (b)).

## 3. Precision tables
Table 3a, the same labels counted several ways, then v3 on C against v4 on D:

| Counting unit | n | Strict real | Lenient real | Strict % | Lenient % | Wilson 95% (strict / lenient) |
|---|---|---|---|---|---|---|
| Per extra (raw) | 12 | 4 | 5 | 33.3 | 41.7 | 14 to 61 / 19 to 68 |
| **Per event** (PR#2540's 3 lines = 1, shopathome's 2 = 1) | 9 | 4 | 5 | **44.4** | **55.6** | 19 to 73 / 27 to 81 |
| **Per flagged PR (>= 1 real extra)** | 8 | 4 | 5 | **50.0** | **62.5** | 22 to 78 / 31 to 86 |

| | v3 on sample C (T10) | v4 on sample D (this note) |
|---|---|---|
| Seed, PRs scored | 20261012, 60 | 20261013, 60 (6 more drawn, skipped) |
| Flagged PRs (kill test 1b: 6 to 30) | 5, **failed** | 8, passed |
| Extras raw / events | 49 / 10 | 12 / 9 |
| Flagged PRs with a clear real extra (strict) | 3 of 5 = 60% (23 to 88) | 4 of 8 = 50% (22 to 78) |
| Lenient | 3 of 5 = 60% | 5 of 8 = 62.5% (31 to 86) |
| Per event, strict | 4 of 10 = 40% (17 to 69) | 4 of 9 = 44% (19 to 73) |
| Per extra, strict | 5 of 49 = 10% | 4 of 12 = 33% |
| Flagged PRs with only FP lines (strict) | 2 of 5 | 4 of 8 |
| Misses among 8 unflagged anchored PRs | 1 | 0 (1 borderline) |
| Stray file in 8 unanchored PRs read | 2 | 0 |

**D is a different sample (different seed and PRs) and C was one of the three samples v4 was fixed on, so this is not v3 against v4 on the same data.** The intervals overlap almost completely. What does differ is the shape: the per-line figure is no longer dominated by two mass events, because v4 grouped them away.

Table 3b, by kind:

| Kind | Extras | Events | Strict real extras | Strict real events | PRs | PRs with a real extra | Note |
|---|---|---|---|---|---|---|---|
| new_dependency | 6 | 3 | 0 | 0 of 3 | 3 | 0 | 0% on every count. All three add something the changed code already uses. |
| stray_file | 3 | 3 | 2 | 2 of 3 | 3 | 2 | Best kind; the third is borderline. |
| ci_or_config | 2 | 2 | 1 | 1 of 2 | 2 | 1 | One FP is migration wiring. |
| build_output_added | 1 | 1 | 1 | 1 of 1 | 1 | 1 | One PR: no rate. |
`binary_or_large_added`, `generated_code_removed`, `public_api_removed`, `tests_removed` and `version_bump` did not fire: D says nothing about them.

## 4. Grouped entries: one event or many
Three lines in `ApplicationInsights#2540` are one event (one new `dependencies` block, all three imported by the same script, FP (b)); the two `concurrently` lines in `shopathome#217` are one event (same package, two sibling apps, FP); the 499 venv files in `typespec#7664` are already one extra (v4 pooled the directory).

## 5. The 'unplaced' bucket: 8 of 29 unanchored PRs (first 8 in sample order, positions 3, 4, 5, 8, 9, 10, 12, 13, chosen before reading; #3 and #4 have no unplaced file)

| # | PR | Files / unplaced | What the files are | Hides a real extra? |
|---|---|---|---|---|
| 3 | celestiaorg/celestia-core#1982 | 5 / 0 | The five workflows the issue names, branch name only | no (but see section 9, defect 1) |
| 4 | spcl/dace#2024 | 1 / 0 | `copilot-setup-steps.yml`, the file the issue asks for | no |
| 5 | dotnet/aspire#10516 | 2 / 2 | `AddProject` overload (+39 -2) and its tests (+184) | no |
| 8 | camunda/camunda-modeler#5121 | 4 / 4 | tenant-ID field for no-auth, validator, API, two specs | no |
| 9 | microsoft/typespec#7651 | 4 / 4 | `[WIP]`: a Spector scenario, mock API, changeset, regenerated `spec-summary.md` | no |
| 10 | prebid/Prebid.js#13698 | 1 / 1 | `adapterManager.ts`, 3 lines | no |
| 12 | microsoft/playwright#36059 | 8 / 8 | `active` in aria snapshots, 4 codegen files strip `[active]`, 2 specs | no (codegen edit is wiring) |
| 13 | docling-project/docling-parse#141 | 1 / 1 | `page_font.h` fix | no |

**Result: 0 of 8 hide a real extra (Wilson 0 to 32%).** T10 found 2 of 8; with 0 of 8 and 2 of 8 the two samples cannot be told apart.

## 6. Misses: 8 unflagged anchored PRs (first 8 in sample order: positions 1, 2, 6, 11, 16, 17, 19, 21)
| # | PR | What changed | Verdict |
|---|---|---|---|
| 1 | Azure/azure-sdk-for-go#24697 | `[WIP]`: `EncryptionContext` option in `directory/models.go` and two test files | clean (a shortfall: the issue links `filesystem/client.go`, not touched) |
| 2 | haydenbleasel/kibo#169 | `AIMessage` actions, docs page, two example files | clean |
| 6 | syncfusion/maui-toolkit#205 | one Android fix (+6 -1) and a test | clean |
| 11 | vdaas/vald#2967 | 240 added `doc.go`, 393 edits of at most -3 lines, none adding a line (file list only; contents not read) | clean |
| 16 | microsoft/generative-ai-with-javascript#122 | wording fixes in lesson READMEs, quizzes and two translations | clean |
| 17 | microsoft/finops-toolkit#1679 | five new columns in two KQL scripts, data-model docs, changelog | clean |
| 19 | githubnext/awesome-continuous-ai#4 | issue template and a `CONTRIBUTING.md` link | clean |
| 21 | prebid/Prebid.js#13368 | `pbYield` helper (the ask), plus `GREEDY` now **disabled by default** and a new `--enable` build flag (`gulpHelpers.js`, README) | **borderline miss, real (b)**: a default flip the issue does not ask for, though greedy promises work against yielding |

**Result: 0 clear misses in 8, 1 borderline (Wilson 2 to 47% for 1 of 8).** No rule reads a default-behaviour flip.

## 7. Real extras the card did not name inside flagged PRs
- **ApplicationInsights#2540:** 17 files under `shared/AppInsightsCore/src` are whitespace-only edits (final newline or blank lines; I checked each patch: added and removed non-blank lines are identical). The card shows them as 17 unplaced names beside 3 FP lines. `devDependencies` is also re-sorted.
- **elsa-core#6677:** the card shows `dotnet-install.sh` and 3 unplaced files. The PR also adds `tempvalidator/` (a Hello-World console project), `.github/workflows/copilot-setup-steps.yml.yml` (on the card nowhere), `src/extensions/Elsa.Testing.Extensions/` and `src/samples/` (a README on stopping background tasks in integration tests), and, by path only, Liquid and `Elsa.Http` content-writer changes. I read the patches of the first four, not the Liquid and Http ones.
- **typespec#7664:** the venv has 501 files, the card counts 499 (`pyvenv.cfg` and the `lib64` link are treated as "named", section 9). `.gitignore` +1 for the venv is the agent's own clean-up. **proxy-scraper#696:** `.gitignore` gains `test_out/`, unrelated housekeeping, shown as unplaced.

## 8. Label sensitivity (my contestable calls)
- ApplicationInsights' three dependencies, FP (b): as real (b), PR #1 joins the lenient total, 6 of 8 (75%, 41 to 93%); strict is unaffected. `config_discovery_example.toml`, real (b): decides lenient 5 versus 4 of 8; strict unaffected (T10 gave a comparable file the same label).
- `reusable-build.yml`, FP: I treat cache wiring forced by a deleted file as implied. A reader who counts any CI edit as an extra flips PR #6 to real.
- The four clear real calls each rest on a patch or listing I read (venv paths, a 7,100-line second lockfile with `pnpm-lock.yaml` beside it, a runner-path temp file, a 1,942-line installer). I expect strict 4 of 8 to hold for another reader; that is my expectation, not a test.

## 9. Rule defects v4 exposed (for v5, not fixed here)
1. **Anchoring drops config files the issue names.** `celestia-core#1982` names all 5 workflows; `_named_files` finds all 5, but `_unplaced` first removes config and manifest files, so `named` is empty and the PR is "unanchored" (verified by running `analyse`). The 29 of 60 unanchored include this case; I tested one PR.
2. **`new_dependency` on a modified manifest ignores usage.** 3 of 3 events were packages the changed or added code already imports or calls (`dynamicproto-js`/`globby`/`magic-string`, `urlencoding`, `concurrently`). A check "does an added or context line use the name" would remove all three. T15 left this open knowingly.
3. **The word "workflow" mutes the CI rule for workflow engines.** `_ci_or_config` returned nothing for `copilot-setup-steps.yml.yml` in Elsa because the issue says "workflow" and that is one of the rule's mention words.
4. **`stray_file` wording is false for a second lockfile:** "in a project that had none" for `ultracite#180`, whose root holds `pnpm-lock.yaml` (the cache cannot show unchanged files; the wording should not assert it).
5. **Temp artefacts and whitespace-only edits have no kind:** `tsconfig.test.vitest-temp.json` is flagged only as "build config", `tempvalidator/` is only unplaced, and 17 whitespace-only files in `#2540` are 17 unplaced names.
6. **`build_output_added` excludes two venv files** (`pyvenv.cfg`, `lib64`), because the directory token `http-client-python` makes them "named"; the card says 499 of 501 and names a deep `site-packages` path, not `venv_build_wheel/`.
7. **No rule reads a default flip** (Prebid `GREEDY`) or a shortfall (`azure-sdk-for-go#24697`).

## 10. The 6 PRs that could not be fetched, and limits
The file lists them under `skipped_fetch_failed`, each with `"error": "no files"`: `dotnet/maui#30225`, `umasteeringgroup/UMA#492`, `Azure/azure-sdk-for-python#41243`, `dotnet/aspire#9399`, `valkey-io/valkey-glide#4263`, `Azure/azure-sdk-for-go#24698`. All six are Copilot PRs; `eval/cache` holds `{"files": []}` for each, so the API call succeeded and returned an empty file list (the code treats that like an error). I did not check why (an empty PR is consistent but unverified). They were skipped and replaced; the sample is 60 scored of 66 drawn.

- Model-made labels, one labeller, no upstream outcomes, no second reader; n = 8 flagged and 60 scored PRs from one seed (20261013), 55 of 60 Copilot, no Claude_Code or Cursor PR.
- The dataset's issue text is the body at AIDev's crawl time and may differ from what the agent saw; PR bodies were context only. Patchless files (`package-lock.json` in #4, 393 edits in `vald#2967`) were not read; labels rest on names, sizes and the surrounding diff.
- The 8 + 8 skim samples were the first in sample order, read once; 0 of 8 and 1 of 8 are not rates. v4 was fixed on A, B and C; 8 flagged PRs cannot show whether a "type the name" gate should exist.

## For you to do
Nothing is needed from you to accept this audit. For the decision: on sample D, the first test that rules v4 had not seen, the extras card was right about a flagged PR 4 times in 8 (50%, and with only 8 flagged PRs that could really be anywhere from 22% to 78%), and 5 in 8 if I count one borderline call. The flag-count test passed this time (8 of 60, needed 6 to 30), and the long clusters that spoiled the last sample are gone. The weak spots are specific: every "new dependency" flag was wrong (3 of 3, each a package the changed code already used), and in two of the eight flagged PRs the card showed only a small part of what the agent added by mistake (an unrelated 17-file whitespace change, a throwaway test project and installer script). Of the 16 PRs the card did not flag, none hid a clear extra and one a borderline one. The honest README line is "on a held-out sample, 4 of 8 flagged PRs held an extra the issue did not ask for (labels by one model, no maintainer check)"; do not write that v4 is better than v3, because 50% against 60% on two different samples of 8 and 5 is no difference at all.

