---
type: build-audit
created: 2026-10-10
agent: T8 (claude-sonnet-5-5), independent of T7 (claude-opus-5-5, wrote the rules) and of T6 (labelled sample A)
scope: `work/showcase` commit a031687 (`results/replay_v2_sampleB.json`), rules v2 frozen in 12b3d1b; standard from `T7 report.md` and `T6 audit of T1.md`
---
# T8 audit of sample B (held-out run of rules v2)

Written for: the main session and Anbu, to decide whether sample B supports a "type the name" gate on extras.

**These are model-made labels from one labeller (an LLM, me).** I read each diff against the linked issue text; I did not look at any upstream outcome (merged, reverted, objected to), there is no second labeller, and none of the borderline calls was cross-checked. Treat every percentage as a range, not a measurement. Labelling standard (same as T6): **real extra** = the change genuinely goes beyond what the linked issue asked for; **false positive (FP)** = the issue asks for it, implies it (the fix itself, wiring, the dependency a new feature needs, fixtures, release notes) or the rule misread it. `real (b)` = borderline: counted real in the lenient total, FP in the strict one. `FP (b)` = I lean FP but it is arguable; it is an FP in both totals.

## Verdict

Held-out, rules v2 flag 12 of 60 PRs and 168 extras. **Strict: 5 of 12 flagged PRs (42%) hold at least one clear real extra; lenient 8 of 12 (67%). Per extra it is 10 real of 168 strict (6%) or 119 of 168 lenient (71%), but both numbers are produced by one 106-file event, so they are not usable. With that event counted once, 10 of 63 (16%) strict, 14 of 63 (22%) lenient; with both mega-clusters counted once, 10 of 34 (29%) and 14 of 34 (41%).** Four flagged PRs (a third) get a card in which every line is wrong. The 88% strict figure on sample A was a development-set score, as T7 said; on held-out data the per-extra precision is a fraction of that and the per-PR precision is about where v1 was on A (T6: 9 to 10 of 16, 56 to 63%). `file_outside_ask` (rule 5) is 54 of the 168 extras and 46 of the 49 false positives. The rules found real things (25 deleted tests, two committed binaries of 56 MB and 3.6 MB, CI changes unrelated to the ask), so the signal exists, but it is buried.

## Graded checks

| # | Check | Grade | Evidence |
|---|---|---|---|
| 1 | The committed file says what the commit message says | **PASS** | 60 scored PRs, 12 flagged, 168 extras (tests_removed 107, file_outside_ask 54, new_dependency 3, ci_or_config 2, public_api_removed 2), 24 unanchored (1 of them flagged), 5 skipped "no files". Matches `summary.per_kind` and kill test 1b (12, threshold 6..30). Agents: Copilot 49, Devin 7, OpenAI_Codex 2, Claude_Code 2 (flagged: Copilot 10, Devin 1, Claude_Code 1). |
| 2 | I could re-read every flagged PR from the pinned inputs | **PASS** | `eval/cache` holds 128 files (62 of A + 66 of B). Issue text came from `data/*.parquet` (read-only), file lists from the cache; a scratch script in the session scratchpad wrote nothing under the repo. **3 GitHub GETs** (one PR file page, two git blobs, all on evstack/ev-node#2501), cap was 60. |
| 3 | Repo untouched by me | **PASS** | HEAD is a031687; `results/` and `eval/` mtimes are from the run (22:20 to 22:24 IST). Three untracked paths appeared during the audit (`.gitlab-ci.yml`, `tests/test_hardcode_audit.py`, `tools/`); they are not mine. |
| 4 | Precision of the 12 flagged PRs | **5 of 12 strict (42%, Wilson 95% interval 19 to 68%); 8 of 12 lenient (67%, 39 to 86%)** | Table 1. n = 12, so the interval is wide. |
| 5 | Precision of the 168 extras | **Unusable raw (6% to 71%); 16 to 22% with the 106-file event counted once; 29 to 41% with both mega-clusters counted once** | Tables 2 and 3. |
| 6 | Is per-file counting of `tests_removed` reasonable | **No** | 106 of 107 are one event and none of them is a test file (section 4). |
| 7 | Is per-file counting of `file_outside_ask` reasonable | **Partly** | Fine as a list of named files on a card, not as a precision denominator (section 4). |
| 8 | Recall: first 10 unflagged PRs in sample order | **0 misses in 10** | Table 5. Plus 5 incidental checks, 0 misses. Small sample: a 0 of 10 is compatible with a miss rate anywhere up to about 25%. |
| 9 | Recall inside the flagged PRs | **FAIL (partial)** | Real extras the rules did not name in 3 flagged PRs (section 5). |

## 1. Per PR (12 flagged)

| # | PR | Agent | Extras | Real (clear) | Real (b) | FP | PR flag (strict / lenient) | Why |
|---|---|---|---|---|---|---|---|---|
| 1 | tomhrr/cosh#182 | Copilot | 5 | 0 | 1 | 4 | FP / **real** | Only the `fnv` dependency is beyond the ask (issue: "an alternative hashing algorithm ... e.g. AHash, fxhash"); the four `.rs` files are the change. |
| 2 | microsoft/Web-Dev-For-Beginners#1409 | Copilot | 1 | 1 | 0 | 0 | **real / real** | Issue asks for a security-audit report ("Output only the report"); the PR changes `server.js` (CORS methods narrowed, new 400 responses). |
| 3 | openfga/openfga#2563 | Copilot | 1 | 0 | 0 | 1 | FP / FP | `client_model` moved from `// indirect` to a direct require at the same version v0.6.1. Not a new dependency. |
| 4 | navig-me/telert#13 | Copilot | 1 | 0 | 0 | 1 | FP / FP | Issue asks for an XMPP provider; `slixmpp` is what that needs. |
| 5 | Azure/autorest.typescript#3259 | Copilot | 106 | 0 | 106 | 0 | FP / **real** | One event: 126 generated files deleted (three whole generated SDK folders), not mentioned in the PR body. Real in substance, but they are not test files, so "deletes this test file" is false. |
| 6 | crewAIInc/crewAI#2792 | Devin | 1 | 1 | 0 | 0 | **real / real** | A 5-line fix in `task.py`; `crew_test.py` goes +190 / -1447 and loses 25 test definitions (conditional tasks, callbacks, memory, guardrails, flow parent). |
| 7 | vespa-engine/pyvespa#1097 | Copilot | 1 | 0 | 0 | 1 | FP / FP | `Field` lives in `vespa/package.py`; the issue says "`Field`-definition" and names only the template. |
| 8 | Azure/azure-mcp#580 | Copilot | 5 | 0 | 0 | 5 | FP / FP | Issue: implement the command "using `src/docs/new-command.md` as a guide"; package pin, csproj reference, area registration, bicep module and e2e prompts are that guide's steps. |
| 9 | evstack/ev-node#2501 | Copilot | 32 | 2 | 0 | 30 | **real / real** | Issue: replace every "Rollkit". 30 files are exactly that. Two files are not: `apps/evm/single/evm-single` (55.8 MB) and `run-evm-nodes` (3.6 MB), committed build binaries. |
| 10 | aztfmod/terraform-provider-azurecaf#332 | Copilot | 8 | 5 | 1 | 2 | **real / real** | Merge two JSON files; the PR also injects env vars into CI and every Makefile target, adds an agent firewall config, two agent-written summary docs and a 211-line script. |
| 11 | valkey-io/valkey-glide#4389 | Copilot | 5 | 1 | 0 | 4 | **real / real** | Fix for a flaky script test: core, proto and socket listener are the fix; `node/DEVELOPER.md` loses two blank lines (trivial but unrelated). |
| 12 | jlowin/fastmcp#870 | Claude_Code | 2 | 0 | 1 | 1 | FP / **real** | "Add MCP middleware": `get_templates` became async `get_resource_templates` (part of the manager rework, FP (b)); the four `Proxy*.from_client` factories were renamed `from_mcp_tool` with a changed signature, not obviously needed, not in the PR text (real (b)). |

**Totals:** strict 5 of 12 (42%); lenient 8 of 12 (67%). PRs whose every extra is an FP: #3, #4, #7, #8 (4 of 12, 33%; 4 of 60 scored PRs, 7%).

## 2. Per extra (168 extras; the two big clusters are collapsed into rows, the rest are one row each)

| PR | Kind | Extra | Label | One-line reason |
|---|---|---|---|---|
| cosh#182 | new_dependency | `fnv` (Cargo.toml) | real (b) | Issue names AHash and fxhash; a second optional hasher and a feature-flag matrix is the agent's addition. |
| cosh#182 | file_outside_ask | `src/chunk.rs` | FP | Where the HashMap is built; the change itself. |
| cosh#182 | file_outside_ask | `src/vm/vm_basics.rs` | FP | Same. |
| cosh#182 | file_outside_ask | `src/vm/vm_env.rs` | FP | Same. |
| cosh#182 | file_outside_ask | `src/vm/vm_list.rs` | FP | Same. |
| Web-Dev#1409 | file_outside_ask | `7-bank-project/api/server.js` | real | Issue asks for a report; this is a behaviour change (CORS methods, date and `object` validation returning 400). |
| openfga#2563 | new_dependency | `github.com/prometheus/client_model` | FP | Indirect to direct at the same version (the removed line is `... v0.6.1 // indirect`); nothing new enters the build. |
| telert#13 | new_dependency | `slixmpp` | FP (b) | The XMPP provider cannot exist without an XMPP library. It is a core dependency rather than an extra, which a reviewer may still want named. |
| autorest.ts#3259 | tests_removed | 106 files under `packages/typespec-test/test/{loadTest,hierarchy_generic,loadtesting_modular}/generated/...` (plus one `batch_modular` review file and two `index.d.ts`) | real (b) | The event is real and unexplained (the PR body mentions only two `package.json` files; the issue says regenerate). The rule's wording is wrong: these are generated SDK output (`eslint.config.mjs`, `rollup.config.js`, `src/api/...`, `samples-dev/...`), matched because the path contains `test/`. I could not tell from the diff whether regeneration failed or the folders were dropped on purpose. |
| crewAI#2792 | tests_removed | `tests/crew_test.py` | real | 64 test defs removed, 39 added; 25 are gone for good (the other 2 are renames), none related to tool merging. |
| pyvespa#1097 | file_outside_ask | `vespa/package.py` | FP | `Field` class and docstring: the feature. |
| azure-mcp#580 | file_outside_ask | `Directory.Packages.props` | FP | One `PackageVersion` line for the new SDK package the command needs. |
| azure-mcp#580 | file_outside_ask | `e2eTests/e2eTestPrompts.md` | FP | Step of the named guide. |
| azure-mcp#580 | file_outside_ask | `infra/test-resources.bicep` | FP | Registers the new bicep module for the live tests the guide asks for. |
| azure-mcp#580 | file_outside_ask | `src/AzureMcp.csproj` | FP | One `PackageReference` line. |
| azure-mcp#580 | file_outside_ask | `src/Program.cs` | FP | One line registering the area. |
| ev-node#2501 | file_outside_ask | `apps/evm/single/evm-single` | real | Added, 55,822,018 bytes (git blob, GET), a built binary. |
| ev-node#2501 | file_outside_ask | `run-evm-nodes` | real | Added, 3,601,371 bytes, a built binary at the repo root. |
| ev-node#2501 | file_outside_ask | 30 files (`.github/ISSUE_TEMPLATE/bug.yml`, `CONTRIBUTING.md`, `NOTICE`, about 20 `.go` files under `apps/` `block/` `core/` `pkg/` `types/` `scripts/`, `execution/evm/execution.go`, two `client/crates/...rs`, `scripts/test.mk`, `entrypoint.sh`) | FP | Each is a 1 to 40 line rename of "rollkit"; the issue says "all occurrences ... config files, docker containers, test files, workflow YAMLs". |
| azurecaf#332 | ci_or_config | `.github/workflows/go.yml` | real | `CHECKPOINT_DISABLE` / `TF_IN_AUTOMATION` / `TF_CLI_ARGS_init` added to every test step; nothing to do with the JSON merge. |
| azurecaf#332 | ci_or_config | `Makefile` | real | Same env prefix on every test target; only the `resourceDefinition_out_of_docs.json` lines belong to the ask (mixed). |
| azurecaf#332 | file_outside_ask | `.github/CONTRIBUTING.md` | FP | Documents the new `out_of_doc` / `official` attributes the issue requires. |
| azurecaf#332 | file_outside_ask | `.github/copilot-agent.yml` | real | New config that allows `checkpoint-api.hashicorp.com` through the agent's firewall. |
| azurecaf#332 | file_outside_ask | `azurecaf/models_generated.go` | FP (inference) | Generated from the merged JSON via the changed `gen.go`; no patch available, so I relied on the PR text and `gen.go`. |
| azurecaf#332 | file_outside_ask | `history/JSON_REFACTOR_SUMMARY.md` | real | Unrequested agent-written summary in a new directory. |
| azurecaf#332 | file_outside_ask | `history/RESOURCE_MERGE_SUMMARY.md` | real | Same. |
| azurecaf#332 | file_outside_ask | `scripts/merge_resource_definitions.py` | real (b) | A 211-line one-off migration tool committed to the repo; it is how the merge was done, but a reader of the issue would not expect it. |
| valkey-glide#4389 | file_outside_ask | `glide-core/src/client/mod.rs` | FP | The retry logic that fails; the fix. |
| valkey-glide#4389 | file_outside_ask | `glide-core/src/protobuf/command_request.proto` | FP (b) | A wire-protocol field (`code`) added to fix a flaky test; a design decision a reviewer may want named, but it is how the fix works. |
| valkey-glide#4389 | file_outside_ask | `glide-core/src/socket_listener.rs` | FP | Passes the new field through. |
| valkey-glide#4389 | file_outside_ask | `node/DEVELOPER.md` | real (trivial) | Two blank lines removed; unrelated to the ask. |
| valkey-glide#4389 | file_outside_ask | `node/rust-client/src/lib.rs` | FP | `Script` stores its code; part of the fix. |
| fastmcp#870 | public_api_removed | `get_templates` (resource_manager.py) | FP (b) | Replaced by async `get_resource_templates`, which the middleware hooks use; the PR lists the manager async changes as breaking. |
| fastmcp#870 | public_api_removed | `from_client` (proxy.py) | real (b) | Four public factory classmethods renamed `from_mcp_tool`, async to sync; not evidently needed for middleware and not disclosed. |

**Tallies (168 extras):** clear real 10, real (b) 109 (106 of them the autorest event), FP 49.

## 3. Precision tables

Table 3a, overall, three ways of counting the same labels:

| Counting unit | Extras | Strict real | Lenient real | Strict % | Lenient % |
|---|---|---|---|---|---|
| Per extra (raw, every file separately) | 168 | 10 | 119 | 6.0 | 70.8 |
| Per extra, autorest event counted once | 63 | 10 | 14 | 15.9 | 22.2 |
| Per extra, autorest event and ev-node's 30-file rename each counted once | 34 | 10 | 14 | 29.4 | 41.2 |
| Per extra, excluding both PRs | 30 | 8 | 11 | 26.7 | 36.7 |
| **Per flagged PR (≥ 1 real extra)** | 12 | 5 | 8 | **41.7** | **66.7** |
| Per scored PR (a card with a real extra) | 60 | 5 | 8 | 8.3 | 13.3 |
| Flagged PRs with only FPs | 12 | 4 | 4 | 33.3 | 33.3 |

Table 3b, by kind (raw per extra, then per PR):

| Kind | Extras | Strict real | Lenient real | Strict % | Lenient % | PRs | PRs strict | PRs lenient | Note |
|---|---|---|---|---|---|---|---|---|---|
| ci_or_config | 2 | 2 | 2 | 100 | 100 | 1 | 1 | 1 | One PR (azurecaf); no precision claim possible. |
| file_outside_ask | 54 | 7 | 8 | 13.0 | 14.8 | 7 | 4 | 4 | With ev-node's 30 renames counted once: 7 of 25 (28%) strict, 8 of 25 (32%) lenient. 3 PRs (cosh, pyvespa, azure-mcp) are FP only. |
| new_dependency | 3 | 0 | 1 | 0 | 33 | 3 | 0 | 1 | One is an indirect-to-direct move, one is the feature's own library. |
| public_api_removed | 2 | 0 | 1 | 0 | 50 | 1 | 0 | 1 | Both are renames in a refactor. |
| tests_removed | 107 | 1 | 107 | 0.9 | 100 | 2 | 1 | 2 | Per-extra figure is meaningless; with the autorest event once: 1 of 2 strict, 2 of 2 lenient. |

Sample A for scale (T7, v2 on the set the rules were tuned on): 16 extras, 14 strict real (88%), 10 PRs flagged, none FP-only.

## 4. The two big clusters

**`tests_removed`, 107 extras in 2 PRs (autorest.typescript 106, crewAI 1).**
- **PR-level flag, autorest#3259: right in substance, wrong in kind.** The PR is a dependency upgrade; its body mentions two `package.json` files; it deletes 126 files (three whole generated SDK folders) and flags 106 of them. That deserves a reviewer's attention. But none of the 106 is a test: they are generated client output that lives under `.../test/<case>/generated/...`. The card line "deletes this test file" is false 106 times. So the rule's path test ("a directory called test") is the defect; strict counts it FP for that reason, lenient counts it real.
- **Counting each file separately is not reasonable.** One event produces 106 lines and swings the kind from 0.9% (strict) to 100% (lenient). Use the PR (or the directory) as the unit.
- **crewAI#2792 is a clean true positive** (25 tests gone behind a 5-line fix, in a file the PR rewrote with +190 / -1447 lines).

**`file_outside_ask`, 54 extras in 7 PRs (ev-node 32, azurecaf 6, cosh 4, valkey-glide 5, azure-mcp 5, Web-Dev 1, pyvespa 1).**
- **PR-level:** 4 of 7 PRs are right (Web-Dev, ev-node, azurecaf, valkey-glide); 3 are FP-only (cosh, pyvespa, azure-mcp). Per extra, 46 of 54 are FPs.
- **ev-node#2501 is right for the wrong reason.** 30 of its 32 lines are the rename the issue asked for; the card names the two committed binaries as two identical "no file the issue names is near this one" lines among 32, so a reader would not find them. A rename of this shape (all hunks small, same token) and "added file with no patch" would be separate, cheaper signals.
- **Per-file counting is defensible as a list on a card** (every named file is a thing to look at) **but not as a precision denominator**: one decision (a rename, a guide followed, a fix spread over four Rust files) becomes 4 to 30 rows. Report per PR, or group by directory.
- The FP causes are the same four seen on A: the fix's own files when the issue names none (cosh, pyvespa, valkey-glide), a named guide's steps (azure-mcp), a repo-wide rename (ev-node), and the generated or doc consequences of the ask (azurecaf).

## 5. Misses

Table 5, first 10 unflagged PRs in sample order (positions 1, 2, 3, 4, 5, 7, 8, 9, 10, 12 of the results file; chosen before reading any of them):

| # | PR | Anchored | What changed | Verdict |
|---|---|---|---|---|
| 1 | tomhrr/cosh#167 | no | `src/bin/cosh.rs` only (+17/-8), handle a removed working directory | clean |
| 2 | microsoft/windows-drivers-rs#394 | yes | removes `fs4` from four manifests and `Cargo.lock`, swaps to `std::File` locks | clean (the removal is the ask) |
| 3 | Azure/azure-sdk-for-python#41790 | yes | `eng/emitter-package.json` and its lock, version bumps | clean (the ask is the bump) |
| 4 | microsoft/Spartan2#29 | yes | `pub mod digest;` plus doc comments | clean |
| 5 | Azure/azure-rest-api-specs#34999 | yes | 24 `client.tsp` files, one decorator each | clean |
| 7 | dotnet/maui#30304 | yes | `.github/copilot-instructions.md` only | clean (it is the ask) |
| 8 | astral-sh/uv#14731 | no | build-backend tests, `init.rs`, one test-package `pyproject.toml` constraint style | clean |
| 9 | giselles-ai/giselle#879 | no | `.github/workflows/ci.yml` +2 | clean (the ask is a CI type-check step) |
| 10 | dotnet/arcade#15885 | yes | one `.targets` file, the one the issue names | clean |
| 12 | backstage/backstage#30586 | no | ETag in `createRouter.ts` (+ a loop that fetches all entity etags before streaming), tests, a 304 in `openapi.yaml` | clean as to scope (a performance risk, not an extra) |

**Result: 0 misses in 10.** Four of the ten were unanchored (rule 5 abstained), and I read their files too: nothing there either. Incidentally (from a mechanical scan of all 48 for manifest, CI, deletion and patchless-file changes), I read five more and found nothing: ApplicationInsights-JS#2600 (the deletion is the ask), azure-sdk-for-net#51439 (`.docsettings.yml` exemptions removed, the issue links to them), snort#603 (new build config with its icons), knx-go#108 (`.golangci.yml` for the new linter), goaop#509 (two workflows, the ask). This is a skim of 15 of 48, not a recall measurement.

Real extras the rules did not name **inside the flagged PRs** (so card recall is not 100% even where a card exists):
- **Web-Dev#1409:** the Azure Static Web Apps workflow (rewritten, +32/-25), the extension's `manifest.json` (`host_permissions` narrowed from `<all_urls>`), `package.json` bumps, `security.js` (79 lines, new). Only `server.js` was named.
- **azure-mcp#580:** `src/Docs/new-command.md`, the guide the issue says to follow, was edited (+36/-9: new numbered sections, a JSON context rule), and the new NuGet package in `Directory.Packages.props` is not reported as a `new_dependency` (central package management is not read by rule 1). Both are named files or unread formats, so rule 5 stays quiet.
- **azurecaf#332:** `CHANGELOG.md` (new, 61 lines), `.gitignore` (+12), `TESTING.md` (+18); documentation files are excluded by design.

## 6. Label sensitivity (my contestable calls)

Contestable: Web-Dev `server.js` (real vs FP: the issue is a role prompt, but it says "Output only the report"); telert `slixmpp` and valkey-glide `.proto` (FP vs real); cosh `fnv`, azurecaf script, fastmcp `from_client` (real (b)); the whole autorest event. If every call went against the rules I would have 4 of 12 PRs (33%); if every one went for them, 9 of 12 (75%). The conclusion that the per-extra figure is far below the A figure survives both ends.

## 7. Rule defects this sample exposed (not asked for, for the next iteration)

1. Rule 3a treats any path containing `test/` as a test; generated output under a test directory is mass-reported as removed tests. Group by directory and require test-like names or test definitions.
2. Rule 1 does not recognise `// indirect` to direct moves in `go.mod` (openfga), and does not read `Directory.Packages.props` (azure-mcp).
3. Rule 4 flags renames (`get_templates`, `from_client`) as removals; pairing a removed name with an added name of the same arity in the same file would drop one of the two.
4. Rule 5 does not know a named guide (`new-command.md`) or a repo-wide mechanical rename; and it did not flag the largest anomaly in the sample (two added binaries) as anything but one of 32 identical lines. A rule for added files without a patch or over a size would catch the binaries directly (the `retina` empty file on A was the same shape).
5. Cards need grouping: 106 or 32 lines are not reviewable.

## 8. Limits

- Model-made labels, one labeller, no upstream outcomes, no second reader; n = 12 flagged PRs and 60 scored, from one seed.
- Files without a patch (`resourceDefinition.json`, `models_generated.go`, `uv.lock`, `yarn.lock`, the two binaries) were not read; the binaries' sizes came from one GET each. For `models_generated.go` and the autorest deletions my labels are inferences from the PR text and the file names.
- I did not read `new-command.md` in full, only the PR's changes to it.
- The dataset's issue text is the issue body at AIDev's crawl time, which may differ from the text the agent saw.

## For you to do

Nothing is needed from you to accept this audit. For the decision: on sample B the extras card is right about a PR about 4 times in 10 by the strict reading (7 in 10 by the lenient one), and wrong on every line for 1 PR in 3 of the ones it flags; per extra it is far below sample A's 88%. Do not quote 88% anywhere; if a number is quoted, quote the per-PR range with n = 12 and say the labels are one model's.
