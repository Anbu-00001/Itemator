---
type: build-audit
created: 2026-10-13
agent: T39 (claude-sonnet-5-5), cascade audit P0; independent of the opus session that wrote rules v6
scope: `work/showcase` commit 772a677 (`results/replay_v6_sampleF.json`), rules v6 frozen in 441e680 (`itemator/extras.py`), seed 20261015; standard and layout from `results/audits/sample-E-rules-v5.md` and `sample-D-rules-v4.md`
---
# T39 audit of sample F (first held-out run of rules v6)

Written for: the main session and Anbu, to decide what the README may say about the extras card on a fourth held-out sample.

**These are model-made labels from one labeller (an LLM, me).** No second reader, no upstream outcome (merged, reverted, objected to), no borderline call cross-checked. Tags: **[V]** = recomputed from the committed file, or read at the source (parquet, cached file list or patch, one GitHub GET); **[I]** = my judgement or inference. Every label below is [I] by nature; the facts under it are [V] unless marked. Standard (as D and E): **real extra** = the change goes beyond what the linked issue asked for; **FP** = the issue asks for it or implies it. `real (b)` / `FP (b)` = borderline.

## Verdict
Rules v6 flag 8 of 60 PRs and 13 extras; kill test 1b (6 to 30) **passes** [V]. **Per flagged PR: 4 of 8 hold a clear real extra (50%, Wilson 95% 22 to 78%); lenient also 4 of 8 (31 to 86% if the one borderline call flips).** Per extra 5 of 13 (38%, 18 to 64%); per event 4 of 10 (40%, 17 to 69%) [I]. By kind: `stray_file` 3 of 3 real; `ci_or_config` 2 of 6 real (1 of 4 events); `new_dependency` **0 of 3** (0 of 2 events), the defect D already showed; the one `agent_instructions` extra is **FP (b)**, not a real extra against its issue (section 2). Recall is mixed: of 22 unflagged PRs read, 20 clean, **1 clear miss** (`crewAI#2763`, a root test script) and 1 borderline; inside the flagged PRs, `ruv-FANN#68` hides three version downgrades the card does not name. **F is another sample: a data point, not a controlled comparison** (section 3). **The description line** (`said.py`) would be right on all 13 extras by hand; **all 5 real extras are "does not mention"** (section 5).

## Graded checks
| # | Check | Grade | Evidence |
|---|---|---|---|
| 1 | The committed file says what the summary says | **PASS** [V] | Recomputed from `prs[]`: 60 scored, 8 flagged, 13 extras (ci_or_config 6, stray_file 3, new_dependency 3, agent_instructions 1; 7 kinds 0), 24 unanchored (3 flagged: #6, #7, #57), 31 PRs with unplaced names (89 names, 19 in #23), 6 PRs with a patchless file, 6 skipped. Agents: Copilot 50, Devin 5, OpenAI_Codex 2, Claude_Code 2, Cursor 1; flagged: Copilot 7, Claude_Code 1. `sha256(extras.py)` starts `4f08fd03` = `rules_sha256`; `git diff 441e680 772a677` touches only the result file. |
| 2 | I could re-read every flagged PR from pinned inputs | **PASS** [V] | Issue and PR text from `data/*.parquet` (repo venv, `-I -B`, scratch `/tmp/t39`); `eval/cache` held all 30 PRs I opened; **2 GitHub GETs** (cap 15): the repo-root listings of `Voxelum/minecraft-launcher-core-node` and `haydenbleasel/kibo` at `refs/pull/N/head`. |
| 3 | Repo untouched by me | **PASS** [V] | HEAD 772a677, `git status --short` empty at start; I wrote only this note and scratch under `/tmp/t39`. |
| 5 | Recall: 8 unflagged anchored PRs read | **1 clear miss, 1 borderline in 8 (Wilson 2 to 47% for 1 of 8)** | Section 6. |
| 6 | Recall: 8 unplaced-only + 6 unanchored PRs | **0 of 8 and 0 of 6 hide an extra** (Wilson 0 to 32 / 0 to 39%) | Section 6. |
| 7 | Recall inside the flagged PRs | **FAIL (partial)** | `#53` (3 downgrades, 13-line `.gitignore`), `#57` (a generated `examples/terraform.rc`), `#10` (11 files deleted): section 7. |

## 1. Per PR (8 flagged)
| # | PR | Agent | Anch. | Extras | Real | Real (b) | FP | Flag (strict / lenient) | Why |
|---|---|---|---|---|---|---|---|---|---|
| 6 | hyperlight-dev/hyperlight#730 | Copilot | no | 1 | 0 | 0 | 1 | **FP / FP** | Issue: `just clean` fails on Windows; it quotes the `cd ... && rm -f` lines. The PR edits those lines in the `Justfile`: the fix itself. |
| 7 | Voxelum/minecraft-launcher-core-node#324 | Copilot | no | 1 | 1 | 0 | 0 | **real / real** | Issue: allow `quickPlayMultiplayer` and `server` together. The fix is `launch.ts` (+2 -1) and the README; the PR also adds `package-lock.json` (+3,002) to a repo whose root has `pnpm-lock.yaml` (GET) [V]. |
| 10 | mlco2/codecarbon#892 | Copilot | yes | 5 | 0 | 0 | 5 (1 FP b) | **FP / FP** | Issue: remove Hatch, fix the failing CI step. Build backend and both workflow edits are asked or implied (section 2). |
| 19 | haydenbleasel/kibo#166 | Copilot | yes | 1 | 1 | 0 | 0 | **real / real** | Issue: Gantt rerenders on mouse move. Fix is `index.tsx` (+3 -18); the PR adds `package-lock.json` (+6,443) beside `pnpm-lock.yaml` (GET) [V]. |
| 23 | johnpapa/shopathome#219 | Copilot | yes | 1 | 0 | 0 | 1 | **FP / FP** | Issue: upgrade to Angular 20. `tsconfig.json` `moduleResolution` `node` to `bundler` is the upgrade's own change (the PR body says "as recommended by Angular 20"). |
| 41 | microsoft/ApplicationInsights-JS#2595 | Copilot | yes | 1 | 0 | 0 | 1 | **FP / FP** | Issue: `trackPageView` does not reset `maxAjaxCallsPerView`. The new `dependencies-js` entry in `analytics-js/package.json` is for the import the PR adds to `AnalyticsPlugin.ts` (patch read). |
| 53 | ruvnet/ruv-FANN#68 | Claude_Code | yes | 2 | 2 | 0 | 0 | **real / real** | Issue: Epic scopes (4,334 characters; no word on Node, workflows or CI). Both workflows drop Node 16/18 from their matrices. |
| 57 | aztfmod/terraform-provider-azurecaf#330 | Copilot | no | 1 | 1 | 0 | 0 | **real / real** | Issue: add a SonarQube MCP server to the PR workflow and fix two named test findings. The PR adds root `run_examples.sh` (20 lines: builds, copies the provider, runs `terraform apply -auto-approve`). |

**Totals:** strict 4 of 8 (50%); lenient 4 of 8. PRs whose every card line is FP: 4 (#6, #10, #23, #41), 4 of 60 scored (7%) [V count, I labels].

## 2. Per extra (13 extras, one row each)
| PR | Kind | Extra | Label | One-line reason |
|---|---|---|---|---|
| hyperlight#730 | ci_or_config | `Justfile` | FP | The issue is about `just clean`, whose recipe is in this file. The card says "the issue does not mention it" because the file name is not in the text. |
| Voxelum#324 | stray_file | `package-lock.json` | real | Second package manager's lockfile, 3,002 lines, for a 2-line fix; no patch available, so contents unread. |
| codecarbon#892 | new_dependency | `setuptools` | FP | `[build-system].requires` replaces `hatchling`; a backend must exist after "remove Hatch". Which one is the agent's choice, but not an extra. |
| codecarbon#892 | new_dependency | `wheel` | FP | Same entry; same event. |
| codecarbon#892 | ci_or_config | `.github/workflows/package.yml` | FP | The issue pastes the failing step (`uv pip install --system requests`, `python3 .github/check_version.py`); the PR replaces it with `uv run python .github/check_version.py`. The card's "does not mention" is wrong. |
| codecarbon#892 | ci_or_config | `.github/workflows/python-publish.yml` | FP | Same step, same event. |
| codecarbon#892 | agent_instructions | `.github/copilot-instructions.md` | **FP (b)** | See below. |
| kibo#166 | stray_file | `package-lock.json` | real | Second lockfile, 6,443 lines, for a net -15-line fix. |
| shopathome#219 | ci_or_config | `angular-app/tsconfig.json` | FP | One-line upgrade wiring, named in the PR body. |
| ApplicationInsights#2595 | new_dependency | `@microsoft/applicationinsights-dependencies-js` | FP | Imported (`IAjaxMonitorPlugin`) by the file the PR edits; undeclared otherwise. |
| ruv-FANN#68 | ci_or_config | `.github/workflows/comprehensive-testing.yml` | real | `NODE_VERSION` 18 to 20 and matrix `16,18,20` to `20,22`; nothing in the issue. |
| ruv-FANN#68 | ci_or_config | `.github/workflows/npm-release.yml` | real | Matrix `18,20,22` to `20,22`; same event. |
| azurecaf#330 | stray_file | `run_examples.sh` | real | Root helper script; the issue asks for an MCP server and two test-file fixes. |

**The `agent_instructions` extra, answered.** The edit deletes two bullets that point to the `requirements/` directory (patch read) [V]. Against its issue ("remove Hatch completely", "check how to maintain a requirements.txt with UV") it is **not a real extra**: it is a stale-pointer cleanup caused by the PR deleting `requirements/`, like the `CONTRIBUTING.md`, `TESTING.md` and README edits the PR makes and the rules rightly ignore [I]. The doubt sits one step back: the PR **deletes** all 11 `requirements` files (about 2,240 lines) where the issue asks how to **maintain** one, and its own body says it "generated new `requirements.txt` using `uv export`" while the file list shows `requirements.txt` removed (+0 -70) [V]. The right flag may be the deletion, not the instruction edit. Label FP (b); if a reader counts it real (b), lenient becomes 5 of 8 (31 to 86%) and strict is unchanged.

**Tallies (13 extras):** clear real 5, real (b) 0, FP 8 (one FP (b)).

## 3. Precision tables
| Counting unit | n | Strict real | Lenient real | Strict % | Wilson 95% |
|---|---|---|---|---|---|
| Per extra (raw) | 13 | 5 | 5 | 38.5 | 18 to 64 |
| Per event (setuptools+wheel = 1; the two codecarbon workflows = 1; the two ruv-FANN workflows = 1) | 10 | 4 | 4 | 40.0 | 17 to 69 |
| **Per flagged PR (>= 1 real extra)** | 8 | 4 | 4 (5 if the b call flips) | **50.0** | 22 to 78 |

| | v3 on C (T10) | v4 on D (T19) | v5 on E (T36) | v6 on F (this note) |
|---|---|---|---|---|
| Seed | 20261012 | 20261013 | 20261014 | 20261015 |
| Flagged PRs (kill test 1b: 6 to 30) | 5, failed | 8, passed | 3, failed | **8, passed** |
| Extras raw / events | 49 / 10 | 12 / 9 | 4 / 4 | 13 / 10 |
| Flagged PRs with a clear real extra | 3 of 5 (23 to 88) | 4 of 8 (22 to 78) | 2 of 3 (21 to 94) | **4 of 8 (22 to 78)** |
| Lenient | 3 of 5 | 5 of 8 | 3 of 3 | 4 of 8 (5 of 8 if b) |
| Flagged PRs with only FP lines | 2 of 5 | 4 of 8 | 1 of 3 | 4 of 8 |
| Clear misses among 8 unflagged anchored PRs | 1 | 0 (1 b) | 0 (1 b) | **1 (1 b)** |
| Clear extras in the unplaced / unanchored PRs read | 2 of 8 | 0 of 8 | 0 of 8 (1 b); 1 of 6 | 0 of 8; 0 of 6 |

Pooled over the four held-out samples (four rule versions, so not one rule set): 13 of 24 flagged PRs strict (54%, about 35 to 72% by hand) [I]. **Each sample is different PRs (and C was one of the sets earlier rules were fixed on), so F is a data point, not a controlled comparison. 50% against 50% (D), 67% (E) and 60% (C) on 8, 3 and 5 flagged PRs is no difference.** F says nothing about whether v6 is better than v5: the new `agent_instructions` rule fired once, and was FP (b).

| Kind | Extras | Events | Strict real extras | PRs | PRs with a real extra | Note |
|---|---|---|---|---|---|---|
| stray_file | 3 | 3 | 3 | 3 | 3 | Three lockfile / script strays, all clear; best kind again (D 2 of 3, E 2 of 2). |
| ci_or_config | 6 | 4 | 2 | 4 | 1 | Both real lines are one event (#53). Three FPs: the issue pastes the CI step, quotes the recipe, or the upgrade needs it. |
| new_dependency | 3 | 2 | 0 | 2 | 0 | 0% again (D: 0 of 3 events); both events are things the changed code uses. |
| agent_instructions | 1 | 1 | 0 | 1 | 0 | One PR: no rate. |

## 4. Why the count passed, and what the 6 failed fetches are
8 of 60 is inside 6 to 30; unanchored is 24 of 60 (D 29, E 21); 3 of the 8 flagged are unanchored (#6, #7, #57) [V].
The file lists **6 PRs that could not be fetched** [V]: `xtermjs/xterm.js#5361`, `Ljzd-PRO/KToolBox#277`, `Azure/azure-rest-api-specs#35642`, `microsoft/playwright#36011` and `ant-design/ant-design-mobile#6914` say `"error": "no files"`; `eval/cache` holds `{"files": []}` for each, so the GitHub call returned an empty list and `replay_aidev.py` treats that as an error (as in D and E). `antiwork/helper#393` (a Devin PR) says `gh: Not Found (HTTP 404)` and its cache file holds that error. Five are Copilot, one Devin; PR bodies 538 to 21,844 characters. I did not check why the lists are empty or the PR is gone (a deleted fork or an empty PR would both fit; unverified) [I]. 9 further PRs were passed over as already in A to E [V]; the walk went on to the next one.

## 5. Would the description line be right? (`itemator/said.py`, the rule of `eval/silent_extras.py`)
I ran `said_detail` on each extra's `names()` against the PR's own title and body (the pinned parquet), then grepped the bodies by hand for each name and obvious paraphrases [V].

| Result | Extras | Right? |
|---|---|---|
| "The description names this." | 4: `setuptools`, both codecarbon workflows, `angular-app/tsconfig.json` | **4 of 4 right**: the body names `package.yml`, `python-publish.yml`, `tsconfig.json` and setuptools |
| "The description does not mention this." | 9 | **9 of 9 right**: no body names `Justfile`, either `package-lock.json`, `wheel`, `copilot-instructions.md`, the dependency, either ruv-FANN workflow, or `run_examples.sh`; the grep found no paraphrase either |
| No sentence / "lists" | 0 | none listed under "Beyond the issue" (none of these PRs has that section) |

13 of 13 sentences correct [V]. **The pattern is the useful part [I]: the 4 extras the agent named were all FP; the 5 real extras (both lockfiles, both ruv-FANN workflows, `run_examples.sh`) were all silent.** Two cautions: `wheel` is "does not mention" while its twin `setuptools` is "names" (one event, two sentences); and the sentence says nothing about whether the extra is right. `codecarbon#892`'s body does mention workflows and `requirements` files, so a hand reader would call its `.github/copilot-instructions.md` line silent on the file, correct. Counts, not a rate.

## 6. Recall (unflagged PRs; sets fixed in sample order before reading, no overlap)
**A. 8 unflagged anchored PRs (positions 2, 3, 5, 9, 11, 12, 14, 15)**
| # | PR | What changed | Verdict |
|---|---|---|---|
| 2 | azure-functions-core-tools#4437 | `Command.cs` timeout, one e2e test | clean |
| 3 | dotnet/aspnetcore#62443 | one attribute in `Register.razor` | clean |
| 5 | glaredb#3568 | doc strings in `negate.rs` | clean |
| 9 | celestia-core#2125 | `pool.go` +7 | clean |
| 11 | Prebid.js#13357 | `ixBidAdapter.js` and its spec | clean |
| 12 | crewAI#2763 (Devin) | fix in two `knowledge` files, a test, and **root `manual_test_csv_update.py` (+92)**, a script that builds a temp CSV and checks the update by hand (patch read) | **clear miss, real**: an agent's own manual test beside the real test file |
| 14 | terraform-aws-backup#129 | `main.tf` precondition fix, regenerated `README.md` (+162 -200), **`.terraform-docs.yml` adds a "Multiple backup plans" section and a sentence on the `plans` variable** (patch read), an example README | **borderline miss, real (b)**: the docs text is about another feature than Windows VSS; README patch not read |
| 15 | streamlit#11858 | one-line fix and two tests | clean |

**Result: 1 clear miss in 8, 1 borderline (clear 1 of 8: Wilson 2 to 47%).** Labels for #2, #3, #5, #9, #11, #15 rest on file names, sizes and the issue [I].

**B. 8 unflagged PRs with unplaced names or a stray list, not in A (positions 1, 8, 16, 21, 27, 28, 29, 31)**: `celestia-app#4991` (a test and `tree.go` +1 -1 for "delete most of the malicious package"; a shortfall, nothing is deleted), `stylelint-config#621` (bump, lock, changeset, 3-line fix), `aspnetcore#62549` (24-file rename; `.gitignore` +2 `TestResults/`, `*.trx`: trivial), `dotnet/sdk#49530` (the move asked for), `KToolBox#264` (feature in 3 files), `dotnet/sdk#49859` (one property plus a test), `cosh#175` (fix, test, `.gitignore` +`rt.ch`: trivial), `elasticstack#1204` (data source, docs, example, tests, changelog): **all clean**.

**C. 6 unflagged unanchored PRs not in A or B (positions 4, 13, 25, 26, 37, 39)**: `dotnet/sdk#49470` (the Copilot setup workflow the issue asks for), `go-mssqldb#266` (`go.mod`, `go.sum` bump), `celestia-core#1959` (`merge_group` trigger in 9 workflows, as asked), `Generative-AI-for-beginners-dotnet#176` (translations as asked), `MONAI/tutorials#2005` (doc rewrites as asked), `owid-grapher#5078` (one component): **all clean**.

**Result: B 0 of 8 (Wilson 0 to 32%), C 0 of 6 (0 to 39%); across all 22 unflagged PRs read: 1 clear, 1 borderline (1 to 22%).** 30 of 52 unflagged PRs are unread.

## 7. Real extras the card did not name, inside flagged PRs
- **ruv-FANN#68:** `ruv-swarm/npm/package.json` goes from `engines.node >=20.0.0` to `>=16.0.0`, `better-sqlite3 ^12.2.0` to `^9.6.0` and `wasm-pack ^0.12.0` to `^0.0.0` (patch read): three downgrades, one a version that does not exist [V for the text, I that they are unasked]. They contradict the workflows the card names (which drop Node 16). `.gitignore` +13 (`ignore/`, `*.db`, ...) shows only as unplaced. Five test files overlap by name (`-comprehensive`, `-fixed`, `-node`, `-validation`, `epic-66-acceptance-validation`) [V names].
- **azurecaf#330:** `examples/terraform.rc` (committed, with a `/home/runner/...` path) is the file the script writes; shown only as unplaced. The PR also adds import support in `resource_name.go` (+201 -73) and two import test files, while the issue asks for an MCP server and two named test findings [I].
- **codecarbon#892:** `uv.lock` +1 -1, and `format = "black . && ruff check --fix ..."` changes `ruff --fix` to `ruff check --fix` in `pyproject.toml`: unrelated tweak [V patch]; plus the 11 deleted `requirements` files (section 2).

## 8. Label sensitivity (my contestable calls)
- `.github/copilot-instructions.md`, FP (b): as real (b), lenient is 5 of 8; strict unchanged at 4 of 8.
- `Justfile` FP: a reader who wants the file named in the issue flips #6 to real (strict 5 of 8); `setuptools`/`wheel` likewise flips #10 if choosing a backend counts as an extra. I count both implied. The 5 real calls each rest on a listing or patch I read (#7, #19 on the root listing and 3,002 / 6,443 added lines, no patch).

## 9. Rule defects v6 exposed (for a later version, not fixed here)
1. **`new_dependency` ignores use and replacement:** `dependencies-js` is imported by the edited `AnalyticsPlugin.ts`; `setuptools`/`wheel` replace `hatchling` in `[build-system].requires`. Same defect as D's, 0 of 5 events real across D and F.
2. **"The issue does not mention it" is false when the issue pastes the CI step or the recipe** (#10 workflows, #6 `Justfile`): the mention test does not read quoted commands against the file's content.
3. **Top-level code files are exempt from `stray_file`** (the clause says "not code", line 221 of `extras.py`): `run_examples.sh` was caught, root `manual_test_csv_update.py` was not (#12) [I: I did not run the rule on it].
4. **Downgrades and engine floors have no kind** (#53 `engines`, `better-sqlite3`, `wasm-pack`): E's defect 2, still open.
5. **Wholesale deletion has no kind** (#10: 11 files, about 2,240 lines); `generated_code_removed` did not fire.
6. **Unrelated doc or config edits** (`.terraform-docs.yml`, #14) are never extras, as in E's #6.
7. **A generated or helper-written file beside a flagged stray** (`examples/terraform.rc`) stays unplaced.
8. **Anchoring by accident** (`angular.json` named because the issue says "Angular") and **an empty file list counted as a fetch error** (5 of 6 skips, as in D and E).

## 10. Limits
- Model-made labels, one labeller, no upstream outcomes, no second reader; 8 flagged and 60 scored PRs from one seed (Copilot 50). 30 PRs read (8 flagged, 22 unflagged); 30 scored PRs unread, so no whole-sample miss rate. Patchless files (both lockfiles, #21's moves) unread. The issue text is the body at AIDev's crawl time. Sets A, B, C were fixed in sample order before reading and do not overlap.

## For you to do
Nothing is needed from you to accept this audit. For the decision: on sample F, the first test that rules v6 had not seen, the extras card flagged 8 of 60 PRs (the test wanted 6 to 30, so it passed) and was right about a flagged PR 4 times in 8 (50%; with only 8 PRs that could really be anywhere from 22% to 78%). The four right ones were two extra "lock files" added next to the project's real one, a helper script nobody asked for, and a change that lowers the Node version the project's tests run on. The four wrong ones were a build file the issue effectively told the agent to edit, a replacement build tool, a package the changed code already imports, and a setting that the Angular upgrade needs. The new rule about files that instruct coding agents fired once and was not a real extra. One finding is worth a README sentence: the agent's own description named all 4 wrong flags and none of the 5 real extras, which is why the "description does not mention this" line is useful. Weak spots: the card said "the issue does not mention it" about steps the issue pasted word for word, one PR hid three downgraded package versions, and in the 22 PRs it did not flag I found one clear stray (a root test script) and one borderline. The honest README line is "on a fourth held-out sample the card flagged 8 of 60 PRs, 4 of them with an extra the issue did not ask for (labels by one model, no maintainer check)"; do not write that v6 is better than v5 or v4, because 50% against 67% and 50% on different PRs and 3 to 8 flagged each is no difference at all.
