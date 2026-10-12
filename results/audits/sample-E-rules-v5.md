---
type: build-audit
created: 2026-10-12
agent: T36 (claude-sonnet-5-5), cascade audit P1; independent of the opus session that wrote rules v5
scope: `work/showcase` commit ada10d8 (`results/replay_v5_sampleE.json`), rules v5 frozen in 4a04365, seed 20261014; standard and layout from `results/audits/sample-D-rules-v4.md`
---
# T36 audit of sample E (first held-out run of rules v5)

Written for: the main session and Anbu, to decide what the README may say about the extras card after the flag-count test failed.

**These are model-made labels from one labeller (an LLM, me).** I read each flagged PR's changes against the linked issue text from the dataset; I did not look at any upstream outcome (merged, reverted, objected to), there is no second reader, and no borderline call was cross-checked. n = 3 flagged PRs supports no rate; read every percentage as a range. Standard (as T10 and T19): **real extra** = the change goes beyond what the linked issue asked for; **FP** = the issue asks for it or implies it. `real (b)` = borderline, real in the lenient total only.

## Verdict
Rules v5 flag 3 of 60 PRs and 4 extras; kill test 1b wanted 6 to 30 and the file says `pass: false`: **failed, and that stands**. **Per flagged PR: 2 of 3 hold a clear real extra (67%, Wilson 95% interval 21 to 94%); 3 of 3 if borderline counts (100%, 44 to 100%).** Per extra 3 of 4 (75%, 30 to 95%). Why so few: **mostly the sample, plus one blind spot** (section 4): only 5 of 60 PRs touched a manifest, a config file or added a top-level file; of the 22 unflagged PRs I read, 19 were clean (86%, 67 to 95%), 1 hid a clear extra and 2 a borderline one. The clear miss is real and has a cause: `RulesEngine#674` dropped `net9.0` and pinned an older SDK, and v5 does not treat `.csproj` or `global.json` as config. Inside the flagged PRs, `SpotifyScraper#48` hides at least five more stray files than the card names. **E is another sample, not a controlled test of v5 against v4.**

## Graded checks
| # | Check | Grade | Evidence |
|---|---|---|---|
| 1 | The committed file says what the summary says | **PASS** | Recomputed from `prs[]`: 60 scored, 3 flagged, 4 extras (ci_or_config 1, stray_file 2, version_bump 1; 7 kinds 0), **21 unanchored** (1 flagged: #48), 28 PRs with unplaced names (210 names, 126 of them in #32), 1 PR with a patchless file (#18, a snapshot), 4 skipped. Agents: Copilot 45, Devin 7, OpenAI_Codex 6, Cursor 2; flagged: Copilot 2, Cursor 1. `sha256(extras.py)` = `rules_sha256` (67f62f09); `git diff --name-only 4a04365 ada10d8 -- itemator` is empty; ada10d8 adds only the result file. |
| 2 | I could re-read every flagged PR from pinned inputs | **PASS** | `eval/cache` held every PR I scanned (322 in A to E, scored and skipped); issue text from `data/*.parquet` via the repo venv (`-I -B`, scratch in `/tmp/t36`). **2 GitHub GETs** (cap 15), both `repos/dotnet/maui/pulls/30293/files`. |
| 3 | Repo untouched by me | **PASS** | HEAD ada10d8; `git status --short` was empty when I first checked (later changes in `itemator/ci.py` and new files are another agent's, ignored). I wrote only the two notes and scratch under `/tmp/t36` (since wiped). |
| 4 | Precision (tables 1 to 3) | **Per flagged PR 2 of 3 strict (67%, 21 to 94), 3 of 3 lenient (44 to 100); per extra 3 of 4 / 4 of 4** | Kill test 1b: 3 of 60, threshold 6..30, **FAIL**. |
| 5 | Recall: 8 unflagged anchored PRs read | **0 clear misses, 1 borderline in 8 (Wilson 2 to 47%)** | Section 6. |
| 6 | Recall: 8 listed only as unplaced, 6 more unanchored | **0 of 8 clear (1 borderline); 1 of 6 clear (Wilson 3 to 56%)** | Sections 5 and 4. |
| 7 | Recall inside the flagged PRs | **FAIL (partial)** | `SpotifyScraper#48`: the card names 1 of at least 6 stray files (section 7). |

## 1. Per PR (3 flagged)
| # | PR | Agent | Anchored | Extras | Real (clear) | Real (b) | FP | PR flag (strict / lenient) | Why |
|---|---|---|---|---|---|---|---|---|---|
| 3 | lukasoppermann/style-dictionary-utils#114 | Copilot | yes | 1 | 0 | 1 | 0 | **FP / real** | Issue: layered shadows per the W3C spec. The fix is `inset?` (1 line) plus tests; the PR also deletes `"vitest/globals"` from `types` in `tsconfig.json`. The issue never mentions vitest or tsconfig; why the agent did it is unknown. |
| 29 | AliAkhtari78/SpotifyScraper#48 | Copilot | yes | 2 | 2 | 0 | 0 | **real / real** | Issue: `get_track_info()` lacks `album`. The PR sets the version back from 2.0.15 to 2.0.7 (`pyproject.toml` twice, `__init__.py`, and a new `[2.0.7]` changelog entry) and adds `MCP_TESTING.md` (107 lines on "MCP (Mock, Capture, Playback)" testing). |
| 48 | StarRocks/starrocks#61244 | Cursor | **no** | 1 | 1 | 0 | 0 | **real / real** | Issue: ORDER BY/WHERE for all show commands. 17 Java files are the feature; `SHOW_COMMANDS_IMPLEMENTATION_SUMMARY.md` (240 lines, repo root) is the agent's write-up of its own work. |

**Totals:** strict 2 of 3 (67%); lenient 3 of 3 (100%). PRs whose every card line is FP: strict 1 (#3), lenient 0.

## 2. Per extra (4 extras, one row each)
| PR | Kind | Extra | Label | One-line reason |
|---|---|---|---|---|
| style-dictionary-utils#114 | ci_or_config | `tsconfig.json` | real (b) | One-line edit to the test type list, unrelated to the ask; could be the agent's own workaround (unverified). |
| SpotifyScraper#48 | version_bump | `2.0.7` (`pyproject.toml`, `__init__.py`) | real | A downgrade, which no issue asks for; the card says "from 2.0.15 to 2.0.7" without the word downgrade. |
| SpotifyScraper#48 | stray_file | `MCP_TESTING.md` | real | Top-level agent-written document, not asked. |
| StarRocks#61244 | stray_file | `SHOW_COMMANDS_IMPLEMENTATION_SUMMARY.md` | real | Top-level summary of the agent's work, not asked. |

**Tallies (4 extras):** clear real 3, real (b) 1, FP 0.

## 3. Precision tables
| Counting unit | n | Strict real | Lenient real | Strict % | Lenient % | Wilson 95% (strict / lenient) |
|---|---|---|---|---|---|---|
| Per extra (raw = per event: the two version files are one event) | 4 | 3 | 4 | 75.0 | 100 | 30 to 95 / 51 to 100 |
| **Per flagged PR (>= 1 real extra)** | 3 | 2 | 3 | **66.7** | **100** | 21 to 94 / 44 to 100 |

| | v3 on C (T10) | v4 on D (T19) | v5 on E (this note) |
|---|---|---|---|
| Seed | 20261012 | 20261013 | 20261014 |
| Flagged PRs (kill test 1b: 6 to 30) | 5, failed | 8, passed | **3, failed** |
| Extras raw / events | 49 / 10 | 12 / 9 | 4 / 4 |
| Flagged PRs with a clear real extra | 3 of 5 = 60% (23 to 88) | 4 of 8 = 50% (22 to 78) | 2 of 3 = 67% (21 to 94) |
| Lenient | 3 of 5 | 5 of 8 = 62.5% (31 to 86) | 3 of 3 (44 to 100) |
| Flagged PRs with only FP lines (strict) | 2 of 5 | 4 of 8 | 1 of 3 |
| Clear misses among 8 unflagged anchored PRs | 1 | 0 (1 borderline) | 0 (1 borderline) |
| Clear extras in the unplaced/unanchored PRs read | 2 of 8 | 0 of 8 | 0 of 8 (1 borderline); 1 of 6 more |

Pooled over the three held-out samples (rule sets v3, v4, v5, so not one rule set): 9 of 16 flagged PRs strict (56%, 33 to 77%), 11 of 16 lenient (69%, 44 to 86%). **Different samples and rule versions; the intervals overlap throughout, so E is no evidence that v5 is better or worse than v4.**

| Kind | Extras | Strict real extras | PRs | Note |
|---|---|---|---|---|
| stray_file | 2 | 2 | 2 | Both caught by the top-level `*.md` clause; both clear. |
| version_bump | 1 | 1 | 1 | One PR: no rate. |
| ci_or_config | 1 | 0 (1 borderline) | 1 | |
`new_dependency` (6 of D's 12 extras, all FP) did not fire: no PR in E adds a dependency. The v5 additions (whitespace_only, temp-artefact strays, venv pooling) fired 0 times, so E says nothing about them.

## 4. Why only 3 of 60 were flagged
- **A count in the brief does not match the file.** "About 29 unanchored" is not E: `unanchored` is 21 (D had 29 under v4, 27 when v5 re-runs D). 29 is `flagged_if_rule5_never_abstained`: PRs with an extra (3) or an unplaced name (26 more).
- **The sample gave the rules little to read.** PRs touching a manifest / a config file / adding a top-level file: E 2 / 2 / 2; A 5 / 5 / 2, B 8 / 7 / 6, C 7 / 3 / 6, D 5 / 8 / 3. Only 5 of E's 60 PRs have any of the three; the rules flagged 3 of them. The other two were correct non-flags (#22: the issue asks for the two workflows; #37: the issue asks to remove a plugin from the pom).
- **Flag counts cannot separate the explanations.** v5 re-run on A to D (development sets, so flattering) flags 32 of 240 (13%, 10 to 18%); E flags 3 of 60 (5%, 2 to 14%).
- **What I read says "mostly quiet sample".** 22 unflagged PRs read (sections 5, 6 and the table below): 19 clean, 2 borderline (#6, #25), 1 clear (#28).
- **Unanchored does not mean hiding.** 13 of the 21 unanchored PRs change 2 files or fewer (17 change 4 or fewer): little room. I read 13 of them (7 in section 5, 6 here):

| # | PR | Files | What the files are | Hides an extra? |
|---|---|---|---|---|
| 11 | antiwork/shortest#250 | 1 / 0 unplaced | README wording (the issue says the README may need an update) | no |
| 26 | openai/openai-agents-js#135 | 2 / 2 | tracing exporter fix (+3 -1) and its test | no |
| 28 | microsoft/RulesEngine#674 | 4 / 4 | fix in `RulesEngine.cs`, new test, **`global.json` SDK 9.0.0 to 8.0.115; `RulesEngine.csproj` drops `net9.0`, `LangVersion` 13.0 to 12.0** | **yes, clear real** (for a bug about a type being "not accessible"; likely an agent sandbox without .NET 9, my inference) |
| 31 | dotnet/aspire#9730 | 1 / 1 | one `ActiveIssue` attribute on the test the issue names | no |
| 32 | microsoft/typescript-go#1141 | 126 / 126 | `helpers.go`, one test, 124 regenerated baselines (98 modified, 28 removed; not opened) | no (consistent with a port) |
| 34 | microsoft/vscode#251760 | 4 / 4 | new setting, search view, a test, a constant | no |

**Result: 1 of 6 hides a clear extra (Wilson 3 to 56%); 1 of the 13 unanchored PRs read (1 to 33%).**

## 5. The 'unplaced' bucket: 8 PRs with only unplaced names (first 8 in sample order not already in section 6: positions 1, 4, 7, 15, 16, 22, 23, 25)
| # | PR | Files / unplaced | What the files are | Hides an extra? |
|---|---|---|---|---|
| 1 | sgb-io/fta#237 | 2 / 2 | exclude-directory fix (+55 -4) and tests | no |
| 4 | alvinwan/timefhuman#85 | 2 / 2 | grammar change and an e2e test | no |
| 7 | Jaysmito101/cgl#43 | 10 / 9 | 8 Python examples, README, `.gitignore` gains `__pycache__/` | no (the ask is "more examples") |
| 15 | shugo/textbringer#124 | 2 / 2 | `buffer.rb` refactor, a test | no |
| 16 | elsa-core#6658 | 1 / 1 | `MassTransitFeature.cs` (+12 -1) | no |
| 22 | genaiscript#1711 | 3 / 1 | the two workflows and a `.genai.mjs` script the issue asks for | no |
| 23 | rqlite#2159 | 1 / 1 | `.stepdown` command in `cmd/rqlite/main.go` | no |
| 25 | dotnet/maui#30358 | 1 / 1 | `eng/common/tools.sh`: retry loop (up to 5 attempts) around the MSBuild call, for "extract all the httpclient changes from PR 30293"; that PR's 7 files (GET) are safe-area code, none under `eng/`, none about http | **borderline, unverifiable** |

**Result: 0 of 8 hide a clear extra (Wilson 0 to 32%); 1 borderline.** No unflagged PR has a stray list: the 2 non-empty `stray` lists are in flagged PRs.

## 6. Misses: 8 unflagged anchored PRs (first 8 in sample order: positions 2, 5, 6, 8, 9, 10, 12, 13)
| # | PR | What changed | Verdict |
|---|---|---|---|
| 2 | dotnet/aspnetcore#62541 | `Boot.Web.ts`, `NavigationEnhancement.ts`, one e2e test: what the issue describes | clean |
| 5 | forntoh/LcdMenu#375 | new `ItemLabel` item, docs, example, tests; `.gitignore` +1 -1 only adds a final newline (patch read) | clean (trivial) |
| 6 | NewFuture/DDNS#528 | noip auth through the URL, `http.py`, tests; **plus `doc/providers/alidns.en.md` heading renames** (patch read), a different provider | **borderline miss, real (b)**: harmless, but docs are never extras |
| 8 | syncfusion/maui-toolkit#219 | `CategoryAxis.cs` +31 only | clean |
| 9 | haydenbleasel/ultracite#178 | lefthook script, tests, docs page, init wiring | clean |
| 10 | getsentry/sentry-cli#2554 | `login.rs` +54 | clean |
| 12 | microsoft/qsharp#2511 | `code_lens.rs`, tests, `test_utils.rs` `Exe` to `Lib` (patch read; reads as test wiring) | clean |
| 13 | crewAI#2165 | agent, crew, knowledge storage, tests | clean |

**Result: 0 clear misses in 8, 1 borderline (Wilson 2 to 47%).** Labels for #2, #8, #9, #10, #13 rest on file names, sizes and the issue; I read patches only where marked.

## 7. Real extras the card did not name inside flagged PRs
- **SpotifyScraper#48:** the card names `MCP_TESTING.md`. Also added, shown only as unplaced names: `docs/mcp_testing.md` (127), `examples/mcp_testing_demo.py` (130), `mcp_test_runner.py` (101, repo root), `track_with_album.json` (20, repo root), three VCR cassettes (399) and `tests/unit/test_track_album_mcp.py` (214), for the agent's own "MCP testing" idea (the three cassettes may belong to the fix's own tests; not checked). `CHANGELOG.md` rewrites its first six lines (the same text, likely line endings). Patches read for the first two and the changelog only.
- **StarRocks#61244:** nothing hidden that I could see; the 17 other unplaced names are the feature. **style-dictionary-utils#114:** nothing hidden.

## 8. Label sensitivity (my contestable calls)
- `tsconfig.json`, real (b): as clear real, per PR 3 of 3 strict; as FP, 2 of 3 lenient (21 to 94%). The strict total of 2 of 3 is unaffected.
- The downgrade is clear real on the issue text alone. A reader who knows the project's release plans could disagree; I could not check.
- `RulesEngine#674`, clear: the SDK pin and target removal are not asked for; the sandbox explanation is inference. #6 and #25 are borderline and enter no strict count. A stricter reader would add #6 to the misses.

## 9. Rule defects v5 exposed (for a later version, not fixed here)
1. **`.csproj`, `global.json`, `Directory.Build.props`, `NuGet.config` are neither manifest nor config** (`_manifest_kind` and `_config_kind` both return None, which I ran). A dropped target framework, a lower `LangVersion` or an SDK pin is invisible: the one clear miss.
2. **No rule reads a version or target downgrade as such.** The `version_bump` wording does not say "downgrade", which is the telling part.
3. **`stray_file` goes quiet when strays name each other or are code.** In #29 `track_with_album.json` is named by the demo script, and `mcp_test_runner.py` is a root code file; only the `.md` is on the card.
4. **Docs are never extras on their own**, so an unrelated doc edit (#6) and a single whitespace-only edit (#5, below the 3-file group) leave no trace.
5. **An issue that only points at another PR** (#25) gives no file or word to anchor on, and the pointed-to PR is not read.
6. **The unplaced list is long and ungraded:** 210 names over 28 PRs, 126 in one regenerated-baselines port; in the 22 PRs I read it held 1 clear and 1 borderline extra.
7. **`ci_or_config` on a one-line `tsconfig.json` edit** says "changes build config", the same text as for a rewrite.

## 10. The 4 PRs that could not be fetched, and limits
The file lists `azure-rest-api-specs#35395`, `usememos/memos#4815`, `Azure-Sentinel#12443`, `risingwave#22637` under `skipped_fetch_failed` with `"error": "no files"`. `eval/cache` holds `{"files": []}` for each, so the GitHub call returned an empty list and `replay_aidev.py` treats an empty list like an error (`not got.get("files")`). All four are Copilot PRs with issue text of 205 to 2,608 characters. I did not check why the lists are empty. The walk went on to the next PR (60 scored, 4 skipped, 2 passed over as already in A to D: 66 walked).

- Model-made labels, one labeller, no upstream outcomes, no second reader; 3 flagged and 60 scored PRs from one seed, 45 of 60 Copilot (more Devin, Codex and Cursor than D). 25 distinct PRs read of 60; the other 35 are unread, so no miss rate for the whole sample.
- The issue text is the body at AIDev's crawl time. Patchless files (`#18`'s snapshot) were not read. Read order: the first N in sample order, fixed before reading; sets in sections 4 to 6 do not overlap.

## For you to do
Nothing is needed from you to accept this audit. For the decision: on sample E, the first test that rules v5 had not seen, the extras card flagged only 3 of 60 PRs, where your own test asked for at least 6, so that test failed and I do not soften it. Of the 3 flagged PRs, 2 held an extra the issue did not ask for (a version number set backwards, and extra "write-up" documents plus a whole set of home-made testing files) and 1 was a borderline one-line change; with only 3 PRs that says nothing about accuracy. The likely reason is mostly the sample: only 5 of the 60 PRs touched the kind of file the rules look at, and of 22 PRs the card did not flag, 19 were clean. But one real hole showed up: a PR quietly dropped a .NET version and pinned an older SDK, and the rules do not treat those build files as settings at all. The honest README line is "on a second held-out sample the card flagged 3 of 60 PRs, 2 of them with an extra the issue did not ask for (labels by one model, no maintainer check; the flag-count test failed)"; do not write that v5 is better or worse than v4.
