---
type: build-audit
created: 2026-10-10
agent: T10 (claude-sonnet-5-5), independent of T9 (wrote rules v3), T8 (audited sample B) and T6 (audited sample A)
scope: `work/showcase` commit d243aaa (`results/replay_v3_sampleC.json`), rules v3 and seed 20261012 frozen in 3527793; standard from `T8 audit of sample B.md`
---
# T10 audit of sample C (first held-out run of rules v3)

Written for: the main session and Anbu, to decide whether sample C supports a "type the name" gate on extras and what rules v4 must fix.

**These are model-made labels from one labeller (an LLM, me).** I read each diff against the linked issue text from the dataset; I did not look at any upstream outcome (merged, reverted, objected to), there is no second labeller, and none of the borderline calls was cross-checked. Treat every percentage as a range, not a measurement; n = 5 flagged PRs is too small to support any rate. Labelling standard (same as T8): **real extra** = the change genuinely goes beyond what the linked issue asked for; **false positive (FP)** = the issue asks for it, implies it (the fix itself, wiring, the dependency a new feature needs, fixtures, release notes) or the rule misread it. `real (b)` = borderline: real in the lenient total, FP in the strict one. `FP (b)` = I lean FP but it is arguable; FP in both totals.

## Verdict

Rules v3 flag 5 of 60 PRs and 49 extras (pre-registered kill test 1b wanted 6 to 30 flagged: it **failed**, `pass: false` in the file). **Per flagged PR: 3 of 5 hold a clear real extra (60%, Wilson 95% interval 23 to 88%), the same 3 under the lenient reading.** Per extra it is **5 real of 49 raw (10%)**, but 40 of the 49 lines are two single events (a new Rust crate's 30 dependency lines and a 10-name "removal" that is a file merge). **With each mass event counted once: 4 real of 10 events (40%; 5 of 10, 50%, lenient).** Two of the 5 flagged PRs (40%) have a card in which every line is wrong. Two mass clusters, both false: all 30 `new_dependency` lines in `mizchi/similarity#13` are the new crate's own dependencies, and all 10 `public_api_removed` lines in `primer/react#6102` name exports that still exist in the renamed file. The two real flags that matter (`codecarbon#905`, `genaiscript#1740`) are right, but the card under-reports both. **The unplaced bucket hides real extras: 2 of the 8 unanchored PRs I read (and 2 of the 6 of those with any unplaced file) contain a stray committed file the card shows only as "unplaced"** (`prepare-changelog.md`, `global.json.backup`). One of 8 unflagged anchored PRs hides a real extra (a 6,443-line `package-lock.json` in a pnpm repo).

## Graded checks

| # | Check | Grade | Evidence |
|---|---|---|---|
| 1 | The committed file says what the summary says | **PASS** | 60 scored PRs, 5 flagged, 49 extras (new_dependency 32 in 2 PRs, public_api_removed 12 in 2 PRs, ci_or_config 4 in 2 PRs, binary_or_large_added 1; tests_removed 0, generated_code_removed 0), 23 unanchored (1 of them flagged: similarity#13), 26 PRs with unplaced files, 5 skipped "no files". Agents in the sample: Copilot 54, OpenAI_Codex 3, Devin 2, Claude_Code 1; flagged: Copilot 4, Claude_Code 1. Recomputed from `prs[]`, matches `summary`. |
| 2 | I could re-read every flagged PR from pinned inputs | **PASS** | `eval/cache` held the file lists of all 60 PRs (60 of 60); issue text came from `data/*.parquet` through the repo's own venv, read-only (`-I -B`, scratch script under the session scratchpad). **4 GitHub GETs** (two file contents at `refs/pull/N/head`, one `.github` directory listing, one repo root listing); cap was 50. |
| 3 | Repo untouched by me | **PASS** | HEAD d243aaa, `git status --short` empty before I wrote the vault note, no file in the repo newer than my first script. The one file I wrote is this note. |
| 4 | Precision of the 5 flagged PRs | **3 of 5 strict (60%, Wilson 23 to 88%); 3 of 5 lenient** | Table 1. One call (AppConfiguration's root `pyproject.toml`) decides 3 vs 2 (section 8). |
| 5 | Precision of the 49 extras | **Unusable raw (10%); 40% strict / 50% lenient with mass events counted once** | Tables 2 and 3. |
| 6 | Are the mass entries one event or many | **One event each** | 30 `new_dependency` lines = 16 distinct names in 3 manifests of one new crate. 10 `public_api_removed` = one file merged into a renamed file. 2 `public_api_removed` in codecarbon = one deleted script. Section 4. |
| 7 | Do `unplaced` files hide real extras | **YES (partial)** | 2 of 8 unanchored PRs read (Table 5). |
| 8 | Recall: 8 unflagged anchored PRs | **1 miss in 8** | Table 6. Small sample: 1 of 8 is compatible with a miss rate from about 2% to 47%. |
| 9 | Recall inside the flagged PRs | **FAIL (partial)** | In 2 of the 3 correctly flagged PRs the named extra is a small part of the real one (section 7). |

## 1. Per PR (5 flagged)

| # | PR | Agent | Anchored | Extras | Real (clear) | Real (b) | FP | PR flag (strict / lenient) | Why |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Azure/AppConfiguration#1065 | Copilot | yes | 4 | 1 | 1 | 2 | **real / real** | Issue: a Flask Python ChatApp with the same features as the .NET one. `azure-identity` and `openai` are what it needs. But a new repo-root `pyproject.toml` (black settings, target py38, line length 120) and an `examples/Python/ChatApp/pyproject.toml` (black + pylint) were not asked for. |
| 2 | mlco2/codecarbon#905 | Copilot | yes | 4 | 3 | 0 | 1 | **real / real** | Issue: improve `pyproject_versions.py` to check version coherence. The PR also deletes `.github/check_version.py` (the PyPI "this version is already published" guard) and does not port it, then repoints `python-publish.yml` to a coherence-only call. |
| 3 | mizchi/similarity#13 | Claude_Code | **no** | 30 | 0 | 0 | 30 | FP / FP | Issue: generalise to tree-sitter "with just a simple configuration", linking the list of parsers. Every flagged line is a dependency of the new `similarity-generic` crate or of the grammars it loads. |
| 4 | microsoft/genaiscript#1740 | Copilot | yes | 1 | 1 | 0 | 0 | **real / real** | Issue: let `generateImage` take image input. The PR commits `.turbo/cache/7b794222d2140ddb.tar.zst` (a Turborepo build cache) and, per section 7, about a thousand other build or tool-generated files. |
| 5 | primer/react#6102 | Copilot | yes | 10 | 0 | 0 | 10 | FP / FP | Issue: find unused code in `packages/react` and delete. The PR merges `form-story-helpers.tsx` into the renamed `storybook-helpers.tsx`; all 10 "removed" names exist in the latter at the PR head (GET). They are Storybook helpers, not package API. |

**Totals:** strict 3 of 5 (60%); lenient 3 of 5 (60%). PRs whose every extra is an FP: #3 and #5 (2 of 5, 40%; 2 of 60 scored PRs, 3%).

## 2. Per extra (49 extras; the two big clusters are collapsed into rows by manifest, the rest are one row each)

| PR | Kind | Extra | Label | One-line reason |
|---|---|---|---|---|
| AppConfiguration#1065 | new_dependency | `azure-identity` (`requirements.txt`) | FP | The sample authenticates with `DefaultAzureCredential`, as the .NET sample does ("all of the same features"). |
| AppConfiguration#1065 | new_dependency | `openai` | FP | The chat completion call is the feature; `AzureOpenAI` lives in this package. |
| AppConfiguration#1065 | ci_or_config | `examples/Python/ChatApp/pyproject.toml` | real (b) | `[tool.black]` and `[tool.pylint.format]` for the sample; harmless, local to the new directory, nobody asked. |
| AppConfiguration#1065 | ci_or_config | `pyproject.toml` (repo root, new) | real | Four lines of black settings that apply to the whole repo, outside the example directory; not implied by the ask. |
| codecarbon#905 | ci_or_config | `.github/workflows/package.yml` | FP (b) | Repoints `-o` to the surviving script and adds `--check_coherence` to the conda step, which is where the issue's check would run. Part of the deletion event, but also wiring of the ask. |
| codecarbon#905 | ci_or_config | `.github/workflows/python-publish.yml` | real | `check_version.py` becomes `pyproject_versions.py -c`, coherence only: the publish pipeline loses its "already on PyPI" check. The PR body says "CI workflows continue to work unchanged". |
| codecarbon#905 | public_api_removed | `get_local_version` (`.github/check_version.py`) | real | The file is deleted (-75 lines). Nothing equivalent exists in `pyproject_versions.py` at the PR head (GET: only `get_version_from_file`, `get_all_versions`, `check_version_coherence`, `get_versions`, `replace_in_file`). |
| codecarbon#905 | public_api_removed | `get_versions_from_pypi` | real | Same event as the row above: counted once. The PyPI JSON lookup is gone. |
| similarity#13 | new_dependency | root `Cargo.toml`: `tree-sitter-{c,c-sharp,cpp,go,java,ruby}` (6) | FP | The grammars of the six languages the issue asks for. |
| similarity#13 | new_dependency | root `Cargo.toml`: `tree-sitter-php` | FP (b) | In `[workspace.dependencies]` and not used by any crate (`Language::Php` and a `php()` config were added), so dangling; but PHP is one of "other languages". |
| similarity#13 | new_dependency | `crates/core/Cargo.toml`: `serde`, `serde_json`, 6 grammars (8) | FP | JSON configuration ("simple configuration") and grammar loading, in the crate that holds the generic parser. |
| similarity#13 | new_dependency | `crates/similarity-generic/Cargo.toml`: 6 grammars, `serde`, `serde_json` (8) | FP | Same dependencies repeated in the new CLI crate. |
| similarity#13 | new_dependency | same file: `anyhow`, `clap`, `once_cell` (3) | FP | The new CLI crate's own stack. |
| similarity#13 | new_dependency | same file, dev-dependencies: `assert_cmd`, `predicates`, `tempfile` (3) | FP | Fixtures for the 1,900 lines of language tests the PR adds. |
| similarity#13 | new_dependency | same file: `similarity-core` (1) | FP | A path dependency on the workspace's own crate, not a third-party package. |
| genaiscript#1740 | binary_or_large_added | `.turbo/cache/7b794222d2140ddb.tar.zst` | real | Turborepo build cache committed, shown by GitHub as +0 -0; nothing to do with image input. |
| primer#6102 | public_api_removed | 10 names in `utils/form-story-helpers.tsx` (`CheckboxOrRadioGroupArgs`, `FormControlArgs`, `formControlArgTypes`, `formControlArgTypesWithoutValidation`, `formControlArgs`, `getFormControlArgsByChildComponent`, `getTextInputArgTypes`, `inputWrapperArgTypes`, `textInputExcludedControlKeys`, `textInputWithTokensArgTypes`) | FP (all 10) | Not removed: all 10 are exported by `storybook-helpers.tsx` at the PR head; the 18 story files were re-pointed. They are Storybook utilities in `src/utils`, not package API. The scope question (the issue says unused, this is a dedupe plus a rename) is real but is not what the card says. |

**Tallies (49 extras):** clear real 5 (root `pyproject.toml`, `python-publish.yml`, two deleted functions, turbo cache), real (b) 1, FP 43 (two of them FP (b): `package.yml` and `tree-sitter-php`).

## 3. Precision tables

Table 3a, overall, the same labels counted several ways:

| Counting unit | n | Strict real | Lenient real | Strict % | Lenient % | Wilson 95% (strict) |
|---|---|---|---|---|---|---|
| Per extra (raw, every line separately) | 49 | 5 | 6 | 10.2 | 12.2 | |
| **Per event, each mass entry counted once** (similarity 30 to 1, primer 10 to 1, codecarbon API 2 to 1) | 10 | 4 | 5 | **40.0** | **50.0** | 17 to 69 |
| Per event, codecarbon `python-publish.yml` merged with the deletion (one decision) | 9 | 3 | 4 | 33.3 | 44.4 | 12 to 65 |
| **Per flagged PR (>= 1 real extra)** | 5 | 3 | 3 | **60.0** | **60.0** | 23 to 88 |
| Per flagged PR if AppConfiguration's root `pyproject.toml` is only borderline | 5 | 2 | 3 | 40.0 | 60.0 | 12 to 77 |
| Flagged PRs with only FPs | 5 | 2 | 2 | 40.0 | 40.0 | |
| Per scored PR (a card with a real extra) | 60 | 3 | 3 | 5.0 | 5.0 | |

Table 3b, by kind (raw per extra, then per event, then per PR):

| Kind | Extras | Events | Strict real extras | Lenient real extras | Strict real events | PRs | PRs with a real extra | Note |
|---|---|---|---|---|---|---|---|---|
| new_dependency | 32 | 3 (AppConfiguration 2, similarity 1) | 0 | 0 | 0 of 3 | 2 | 0 | 0% on every count. Both PRs add the feature's own dependencies. |
| ci_or_config | 4 | 4 | 2 | 3 | 2 of 4 | 2 | 2 | Both PRs correct, but by one line each; the other two lines are borderline or FP. |
| public_api_removed | 12 | 2 (codecarbon 1, primer 1) | 2 | 2 | 1 of 2 | 2 | 1 | The real one is a deleted script; the FP is a file merge (same defect as T8 saw in fastmcp). |
| binary_or_large_added | 1 | 1 | 1 | 1 | 1 of 1 | 1 | 1 | Right, and the only kind that found a build artefact. One PR: no rate. |
| tests_removed | 0 | 0 | | | | 0 | | Did not fire (T8 saw 107 in 2 PRs). |
| generated_code_removed | 0 | 0 | | | | 0 | | Did not fire. |

For scale: sample B (T8, rules v2) had 5 of 12 flagged PRs strict (42%) and 29 to 41% per extra with the two mega-clusters counted once; sample C has 3 of 5 (60%) and 40 to 50% per event. The intervals overlap almost completely (B 19 to 68%, C 23 to 88%), so **sample C does not show v3 is better than v2**; it shows v3 flags fewer PRs (8% of the sample against 20%) and the kill test on that count failed.

## 4. The mass entries: one event or many

| Entry | Lines | Judgement | Why |
|---|---|---|---|
| `new_dependency`, similarity#13 | 30 | **One event**, FP | 30 lines are 16 distinct names (7 grammars, 9 others) repeated across the workspace, core and new crate manifests. One decision: "add a generic parser crate". The manifest of `similarity-generic` is itself an added file, so everything in it is the feature. |
| `new_dependency`, AppConfiguration#1065 | 2 | Two lines, both FP | Two requirement lines the sample cannot run without. |
| `public_api_removed`, primer#6102 | 10 | **One event**, FP | One file merged into another. The names are used by 18 stories and exist after the PR. |
| `public_api_removed`, codecarbon#905 | 2 | **One event**, real | One script deleted, functionality (PyPI duplicate check) not ported. |

Counting these per line makes the new-dependency kind look like 32 observations when it is 3, and moves the per-extra precision from 40% to 10%.

## 5. The 'unplaced' bucket: 8 of 23 unanchored PRs (first 8 in sample order)

Chosen before reading any of them: sample positions 3, 7, 9, 12, 15, 18, 20, 21. Two of the eight (knx-go#110, zudoku#1137) have zero unplaced files (I do not know why the card does not list those single files as unplaced).

| # | PR | Files / unplaced | What the unplaced files are | Hides a real extra? |
|---|---|---|---|---|
| 3 | kubernetes-sigs/sig-storage-local-static-provisioner#505 | 2 / 2 | `pkg/discovery/discovery.go` (+26/-1, the fix) and a 194-line test | no |
| 7 | dotnet/Open-XML-SDK#1932 | 12 / 12 | Newtonsoft.Json removal across props, targets, converters, tests, test data (the PR body says it kept the package in `Directory.Packages.props`; the diff removes it, which is what the issue asks) | no |
| 9 | Azure/azure-sdk-for-js#34607 | 3 / 1 | **`prepare-changelog.md`**, a 148-line agent-written process document ("CHANGELOG Preparation Process", parameters, bash steps) added at the repo root; the issue asks for CHANGELOG entries, which are the other two files | **YES, real** |
| 12 | vapourismo/knx-go#110 | 1 / 0 | `.github/workflows/check.yaml` +2 (Go 1.23, 1.24: the ask) | no |
| 15 | zuplo/zudoku#1137 | 1 / 0 | one docs page (the ask) | no |
| 18 | microsoft/vstest#15097 | 3 / 3 | the fix in `TestExecutionRecorder.cs`, its tests, and **`global.json.backup`** (+36, a copy of the SDK pin file), unrelated debris | **YES, real** |
| 20 | mlflow/mlflow#16472 | 12 / 11 | 11 docstring fixes plus the `RUF002` line in `pyproject.toml` (the ask) | no |
| 21 | dotnet/aspire#10520 | 1 / 1 | one file, three `WithUrlForEndpoint` display names (a different reading of the issue, but one file and not an extra) | no |

**Result: 2 of 8 PRs (25%) hide a real extra that the card shows only as an unplaced file name; 2 of the 6 that have any unplaced file.** In both the stray file is small (a document, a backup) and the card lists it next to the real change with no hint which is which. Rule 5 abstained correctly (the issue names no path) but its replacement, "report unplaced files", leaves the decision to a reader who sees 1 to 11 files of mixed content. Small sample: 2 of 8 is compatible with a rate from about 7% to 59%. The largest unplaced bucket in the whole sample is `genaiscript#1740` (304 files, section 7), an anchored PR.

## 6. Misses: 8 unflagged anchored PRs

Chosen before reading: the first 8 anchored PRs with no extras in sample order (positions 2, 5, 6, 8, 10, 11, 13, 14).

| # | PR | What changed | Verdict |
|---|---|---|---|
| 2 | dotnet/fsharp#18575 | one check in `CheckExpressions.fs`, one new message in `FSComp.txt` and its 13 `.xlf` translations, a test and its `.fsproj` entry | clean |
| 5 | haydenbleasel/kibo#164 | `packages/gantt/index.tsx` (+43/-1, the feature) and **`package-lock.json` (+6,443, a new npm lockfile)** | **MISS, real.** The repo root has `pnpm-lock.yaml` and `pnpm-workspace.yaml` (GET); a second package manager's lockfile is not what "scroll to timeline item" asks for. GitHub gave the file no patch. |
| 6 | taiga-family/taiga-ui#11485 | `combo-box.directive.ts` fix and a new spec | clean |
| 8 | Azure/azure-container-networking#3747 | `internalapi.go` log message fix and its test | clean |
| 10 | dotnet/runtime#116256 | `Strings.resx` (+6, the error text), `WinHttpHandler.cs`, tests | clean |
| 11 | Azure/azure-sdk-for-python#41620 | the one sample file the issue links | clean |
| 13 | Azure/azure-dev#5256 | rename to `infra generate`, `synth` and `gen` aliases, help text, snapshots, templates: all named in the issue | clean |
| 14 | microsoft/vscode#251150 | HTML headers in `getMarkdownHeadersInCell`, the old fallback helper removed because the shared function now covers it, tests | clean |

**Result: 1 miss in 8 (12.5%, Wilson 2 to 47%).** Why the rules were silent (inference from the card text of `genaiscript`, not from reading `extras.py`): the binary rule describes a file "GitHub shows no diff for (+0 -0)"; the kibo lockfile is +6,443 with no patch, and there is no rule for lockfiles or a second package manager.

## 7. Real extras the card did not name inside the flagged PRs

- **codecarbon#905:** the PR bumps the version 3.0.4 to 3.0.5 in `codecarbon/_version.py`, `pyproject.toml` and `docs/edit/conf.py`, regenerates about 25 built docs pages (`docs/*.html`, `searchindex.js`, `objects.inv`), edits `docs/_sources/parameters.rst.txt` (the `gpu_ids` text, unrelated) and refreshes `uv.lock` (+3,838/-3,393, no patch). The issue asks for a coherence checker. None of this is on the card, which shows two CI files and two removed functions. The PR body does not mention the bump.
- **genaiscript#1740:** 1,117 files in the PR; the feature, its test, 5 docs pages and 5 sample scripts are about 15 of them. The rest are committed build output (`packages/core/.tshy-build` 795 files, `tools/eslint-plugin-genaiscript/{.tshy-build,dist}` 276, `.tshy` configs, `.turbo` log and cache), a 6,226-line generated `genaiscript.d.ts`, and what looks like the output of a multi-agent config generator (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.clinerules`, `.windsurf`, `.junie`, `.openhands`, `.cursor`, `.mcp.json`, `claude_desktop_config.json`, `.bak` copies). The card shows 1 extra and "304 unplaced". I did not check where the other ~770 files are classified, so I cannot say whether the card mentions them.
- **AppConfiguration#1065 (shortfall, not an extra):** the issue requires Flask; the word does not appear in any patch, and the PR body lists a `templates/` directory that is not in the file list. This is the opposite problem (less than asked) and no rule looks for it.

## 8. Label sensitivity (my contestable calls)

- AppConfiguration root `pyproject.toml`: real versus real (b). Decides PR 3 of 5 versus 2 of 5 strict. I called it real because it is a repo-wide setting outside the new directory.
- codecarbon `package.yml`: FP (b) versus real (b). Either way the PR keeps its flag through `python-publish.yml` and the deletion.
- codecarbon deletion: I called it real because I could find no port of the PyPI check at the PR head. If the check lives elsewhere (another script, a workflow step I did not read), the two API lines and `python-publish.yml` would flip to FP and the PR would fall to `real (b)`/FP. I read the new file and the `.github` listing only.
- similarity `tree-sitter-php`: FP (b) versus real (b). It does not change the PR flag (the other 29 are FP regardless).
- primer: one could argue the dedupe plus rename is beyond "delete unused code" (real (b) at PR level). The card's claim (public API removed) is false regardless, so the 10 lines stay FP.
- Wide ends: if every contestable call went against the rules, 2 of 5 PRs (40%); if every one went for them, 3 of 5 (60%) because primer and similarity have no real line even leniently. The conclusion "the per-line figure is far below the per-PR figure and below 50%" survives both ends.

## 9. Rule defects this sample exposed (not asked for, for v4)

1. **Rule 1 flags every dependency of a newly added manifest.** An added `Cargo.toml` (or `package.json`) belongs to a new package, so everything in it is the feature. Collapse to "adds crate X" and drop the lines (30 FPs here).
2. **Rule 4 still reads a file merge or rename as a removal** (primer; T8 saw the same in fastmcp). Check whether the name is exported elsewhere in the PR head, or pair a deleted file with a renamed one. Also, `utils/*story*` helpers are not package API.
3. **No rule sees a lockfile for a package manager the repo does not use** (kibo `package-lock.json` beside `pnpm-lock.yaml`), a version bump the issue did not ask for (codecarbon), or a large patchless added file that is not `+0 -0` (kibo).
4. **`unplaced` needs triage, not just a list:** `*.backup`, `*.bak`, root-level `*.md` that is not the issue's file, a new file with no inbound reference. Two of eight unanchored PRs had exactly that.
5. **Mass build-output commits are reported as one file.** Count added files under `.turbo`, `dist`, `.tshy-build`, `node_modules`-like paths and say "N generated files committed".
6. **Cards need grouping**, again: 30 and 10 lines are not reviewable.

## 10. Limits

- Model-made labels, one labeller, no upstream outcomes, no second reader; n = 5 flagged and 60 scored PRs from one seed (20261012).
- Rules v3 were tuned on A and B; C is the first held-out run, but C says nothing about whether the gate should exist at n = 5.
- Files without a patch were not read (`uv.lock`, `docs/objects.inv`, `package-lock.json`, `.turbo/...tar.zst`, three generated `.d.ts`); my labels for them rest on file names, sizes, the PR text and the surrounding diff.
- The dataset's issue text is the issue body at AIDev's crawl time, which may differ from what the agent saw.
- The 8 + 8 skim samples were the first in sample order, read once each; a 1 of 8 and a 2 of 8 are not rates.

## For you to do

Nothing is needed from you to accept this audit. For the decision: on sample C the extras card is right about a flagged PR 3 times in 5 (n = 5, so anywhere from 23% to 88%), and wrong on every line for 2 of the 5; per line it is wrong 9 times in 10 until the 40 lines that are two single events are counted once (then 4 in 10). The kill test on how many PRs get flagged failed (5 of 60, needed 6 to 30). The cheaper finding is on the side: of the 16 PRs I read that the card did not flag or only listed as "unplaced", 3 contained a stray committed file (`prepare-changelog.md`, `global.json.backup`, a second lockfile), so the unplaced list is worth showing but not worth trusting. Do not quote any percentage from this sample without saying the labels are one model's and the denominator is 5.
