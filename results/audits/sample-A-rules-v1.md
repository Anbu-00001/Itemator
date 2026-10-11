---
type: build-audit
created: 2026-10-10
agent: T6 (claude-sonnet-5-5), independent of T1 (claude-opus-5-5)
scope: commit cf0d762 in work/showcase, plus `T1 report.md`; context `Lock v2 2026-10-10.md`
---
# T6 audit of T1 (extras rules and AIDev replay)

**Verdict:** the numbers and the pre-registration hold; the rules do not yet earn a "type the name" gate. Of 35 flagged extras, **17 are real and 18 are false positives** (14 real if borderline cases count against us), so precision is **40 to 49%**. The precision figures below are **a model-made estimate** (one labeller, an LLM, reading each diff against the issue text; no upstream outcome was looked at, and no second labeller). Treat them as a range, not a measurement.

Nothing in the repository was modified by me. Scratch scripts are in the session scratchpad. `ana run` wrote only to `~/.anamnesis`. An untracked `eval/replay_outcomes.py` appeared in the repo during the audit; it is not mine.

## Graded checks

| # | Check | Grade | Evidence |
|---|---|---|---|
| 0 | Tests on the committed code | **PASS** | `ana run 8b09c9 -- .venv/bin/python -m pytest -q`: 20 passed, graded TRUE (my forecast 93%). |
| 0b | Mutation script re-run on the final code | **PASS** | 23 of 23 mutants killed (matches T1's 303e8b). |
| 0c | The committed predictions come from the committed rules | **PASS** | I recomputed all 60 PRs from `eval/cache` with the current `extras.py`: 0 mismatches in extras, `anchored`, `unplaced`, file counts. The sha256 `4373e9f6...` in the commit message equals the committed file. |
| 1 | Correctness of the rules | **FAIL** | 11 concrete wrong or missed outputs below (4 false positives, 7 misses). |
| 2 | Precision of the 16 flagged PRs | **40 to 49% of extras; 9 to 10 of 16 PRs have at least one real extra** | Table below. `file_outside_ask` makes 20 of 35 extras and is only 20 to 30% precise; `tests_removed` is 0 of 2. |
| 3a | Licence filter is honest | **PASS** | Filter is `PERMISSIVE` (MIT, Apache-2.0, BSD-2/3, ISC, 0BSD, Unlicense) on AIDev's GitHub-detected `repository.license`. It is conservative: it drops NOASSERTION (511 linked PRs), unlicensed (126), CC0-1.0 (23) and CC-BY-4.0 (101). The funnel adds up (2842+808+94+2+4+7 = 3,757). All 60 sampled are MIT 44, Apache-2.0 14, BSD-3 2. Caveat: repo-level, as detected by GitHub at AIDev's crawl, not checked against LICENSE files (T1 says so). |
| 3b | Sampling and seed are honest | **PASS** | I rebuilt the pool (3,703, same agent split), sorted by `pr_id`, shuffled with `Random(20261010)`: the first 62 are exactly the 60 sampled plus the 2 skipped ("no files"), in the same order. Mtimes: `extras.py` last edited 21:47:05 IST; the ledger claims 229a43/51dfff/fa36b6/21b863 were created 21:47:14; the first API fetch is 21:47:19; the last is 21:48:45 (one run, 86 s); results written 21:48:46. So rules and predictions precede the run, and the run happened once. |
| 3c | Third parties can reproduce it | **FAIL** | `BASE_URL` uses the movable ref `v3`, with no sha256 of the four parquet files; `duckdb` is unpinned in `pyproject.toml`; `eval/cache` (the 62 file lists) is gitignored and not hashed. I found no drift: the 3 live GitHub file lists I re-fetched (s3-zip#113, AIShell#385, retina#1704) equal the cache. |
| 4a | Every figure in `T1 report.md` matches `replay_predictions.json` | **PASS** | 36 figures checked, 36 match: funnel 4,905 / 3,757 / 3,703 / 0 / 0; 16 of 60; 2 skipped; 67 calls; per-kind pairs 1/1, 3/4, 1/2, 2/8, 12/20; 18 abstained; 27 if never abstained; 4 with a patchless file; agent split 3,152 / 340 / 110 / 63 / 38 (85% Copilot); 4,923 `source = body` rows; 62 cache files; 20 tests; 23 mutants; 47-line and 109-line figures; seed. The 11 ana claim ids exist with the stated text. |
| 4b | The report's judgements and status lines | **FAIL** | (i) Example 3 (`policy_test.go`, "109 lines deleted") is a false positive: the issue says "copy the existing acceptance tests into the new codebase" and the PR adds `acc_test.go` (+200). (ii) "`json` flagged twice ... likely false positive" is wrong: `CrewOutput.json` and `TaskOutput.json` (`@property`) were really removed, replaced by `model_json()`. (iii) "Nothing is committed" is stale (cf0d762 exists). (iv) "Both parts of kill test 1 pass": Lock v2 lists a third part, 1c (at least 3 flagged extras reverted or objected to upstream), still open. |
| 5 | AIDev CC BY 4.0 attribution | **PASS, with gaps** | `NOTICE` gives authors, title, version v3, source URL, licence name and URL, the paper (arXiv 2507.15003, from memory, not re-fetched), says the data is fetched not redistributed, and says the results file holds derived values. Gaps: `README.md` and `AGENTS.md` do not mention AIDev or `NOTICE`; the Lock v2 demo shows real agent PRs, so the video and the Devpost text need the credit and the repo owners' licence notices (MIT/Apache) too. I could not check the dataset licence at source (no network allowed beyond GitHub); T1's brief is the only source in the vault. |

## 1. Concrete rule bugs (inputs run in a scratch script against the committed `extras.py`)

False positives:
- **R2 dependabot.** Issue "configure dependabot to bump the aspire sdk" + changed `.github/dependabot.yml` gives `ci_or_config`. `_CI_WORDS` has no "dependabot" (or "renovate"), and the file name `dependabot.yml` is not in the text. Real case: FilterLists#5036.
- **R3a moved or asked-for deletion.** A deleted test file is an extra unless a test file with the *same name* is added. Different name (`policy_test.go` to `acc_test.go`, elastic#1220), or issue "Remove the deprecated legacy_auth module" with `tests/test_legacy_auth.py` deleted beside `src/legacy_auth.py`: both flagged. (The second also flags `def x` as `public_api_removed`.)
- **R4 nested or renamed.** A removed indented `def inner(y)` inside a function is flagged `public_api_removed`; a rename `get_user` to `fetch_user` is flagged as a removal (arguably right, but the card calls it "public API").
- **R1 separator.** `python_dateutil` replaced by `python-dateutil` is reported as a new dependency (`removed` compares with `.lower()` only).

Misses:
- **R5 project-name directory.** Issue "crewai reset-memories fails with ollama" + changed `src/crewai/memory/reset.py` and `src/crewai/billing/invoice.py`: no extra, because the token "crewai" equals the directory `crewai`, so every file under it is "named" (rule 5c). Without the word "crewai" in the issue, `invoice.py` is flagged. Any issue that says the project or package name disables rule 5 for that package. This also silenced crewAI#2034's `agent.py` (+123/-28) and `task.py`.
- **R1 URL and VCS requirements.** `requirements.txt` adding `git+https://github.com/evil/pkg.git#egg=pkg` or a bare `https://.../pkg.whl`: no extra (`"://" in s and " @ " not in s` is skipped). That is the riskiest dependency form.
- **R1/R2 manifest content is invisible.** `package.json` adding `"postinstall": "node scripts/x.js"` and `pyproject.toml` adding `[tool.ruff.lint] ignore = [...]`: no extra. Manifests are in `covered`, so rule 5 skips them, and rules 1/2 only read dependency names. `.github/CODEOWNERS`, `.npmrc`, `renovate.json`, `global.json` are not in `_CONFIG_RULES` either (global.json was caught only by rule 5).
- **R4 `defined_again` is global.** `def load_config` removed from `src/auth/cfg.py` and an unrelated `def load_config` added in `tests/helpers.py`: the removal is suppressed (added lines of test files and other languages count).
- **R1 short-name mention.** Issue "Crashes on Node 20" + added `@types/node`: suppressed, because for npm and Go the last path segment ("node") is also tried as a mention.
- **R3 skip by common word.** A deleted `test.js` is skipped when the issue merely contains the word "test".
- **R5 abstention and generosity.** An issue with no anchor ("Fix the crash on startup") + `src/x.py`, `.github/CODEOWNERS`, `deploy/secrets.yaml`: no extras (by design). In the replay that is 18 of 60 PRs; 11 of the 44 unflagged PRs are "clean" only because rule 5 abstained on their files. Also, one named root file forgives every root file.

## 2. Per-extra precision (model-made estimate)

Label rule: **real** = a reviewer who read only the issue would not expect it and would want a named line; **FP** = the issue asks for it, implies it (the fix itself, wiring, fixtures, release note), or the rule misread it. `(b)` = borderline; counted real in the lenient total, FP in the strict one.

| # | PR | Kind | Extra | Label | Reason |
|---|---|---|---|---|---|
| 1 | compass#484 | file_outside_ask | `backend/.env.example` | FP | Adds `EMAILER_WAITLIST_INVITE_TAG_ID`; the issue asks to add the `compass_waitlist_invited` Kit tag. |
| 2 | compass#484 | file_outside_ask | `backend.test.init.js` | FP | Test env for the same variable. |
| 3 | compass#484 | file_outside_ask | `env.constants.ts` | FP | Schema entry for the same variable. |
| 4 | compass#484 | file_outside_ask | `env.util.ts` | FP | `isMissingWaitlistInviteTagId`, the guard for the same tag. |
| 5 | crewAI#2034 | public_api_removed | `json` (crew_output.py) | real | `CrewOutput.json` property removed, replaced by `model_json()`; issue is about `reset-memories` with Ollama. |
| 6 | crewAI#2034 | public_api_removed | `json` (task_output.py) | real | Same removal on `TaskOutput`. |
| 7 | crewAI#2034 | public_api_removed | `from_langchain` | real | Classmethod removed from `BaseTool`/`Tool` (base_tool.py -127 lines); unrelated to the ask. |
| 8 | crewAI#2034 | public_api_removed | `to_langchain` | real | Same file, same unrelated removal. |
| 9 | crewAI#2034 | file_outside_ask | `tests/conftest.py` | real (b) | Autouse fixture rewritten: drops the temp `CREWAI_STORAGE_DIR` isolation, forces Ollama env for every test; Ollama-related but global. |
| 10 | elastic#1220 | tests_removed | `policy_data_source_test.go` | FP | Tests copied into `acc_test.go` as the issue instructs; rule only knows same-name moves. |
| 11 | elastic#1220 | tests_removed | `policy_test.go` | FP | Same (T1's example 3). |
| 12 | elastic#1220 | file_outside_ask | `internal/utils/tfsdk.go` | real | Shared helper refactor (new generic `elementsAs`, rewrites `MapTypeAs`, `SliceToListType_String`) used outside the migrated resource. |
| 13 | elastic#1220 | file_outside_ask | `internal/utils/tfsdk_test.go` | real (b) | +58 test lines for that helper change; low risk, follows #12. |
| 14 | FilterLists#5036 | ci_or_config | `.github/dependabot.yml` | FP | The issue asks exactly for dependabot configuration (rule 2 bug). |
| 15 | FilterLists#5036 | ci_or_config | `workflows/check-aspire-versions.yml` | real | New 47-line CI workflow; the issue only asked for dependabot config and said not to bump the version. |
| 16 | dotnet/sdk#49315 | file_outside_ask | `NuGetPackageInstallerTests.cs` | FP | Regression tests for the fix in `PackageSourceLocation.cs`; not linked because the source file is not named. |
| 17 | retina#1704 | file_outside_ask | `test-summary` | real | Empty stray file added (+0/-0); agent debris. |
| 18 | maui#30178 | file_outside_ask | `BorderHandler.Android.cs` | FP | This is the bug fix itself; an issue cannot name the root-cause file. |
| 19 | maui#30178 | file_outside_ask | `BorderHandlerTests.Android.cs` | FP | Device test for that fix. |
| 20 | kibo#180 | ci_or_config | `apps/docs/tsconfig.json` | real (b) | `@/components/*` now also resolves to `./components/*` first; needed by the new components but changes resolution for existing imports. |
| 21 | fsharp#18584 | file_outside_ask | `Checking/infos.fs` | FP | `IsFSharpEventProperty` fix; the issue is exactly that CLIEvent properties are misreported. |
| 22 | fsharp#18584 | file_outside_ask | `TypedTree/TypedTreeOps.fs` | FP | `XmlDocSigOfVal` emits `E:` for CLIEvent: the XmlDoc id fix the issue describes. |
| 23 | autorest.typescript#3328 | file_outside_ask | `cadl-ranch-list.js` | FP | Registers `azure/core/operation-templates`, the test the issue asks for. |
| 24 | PSRule#2973 | file_outside_ask | `.github/copilot-instructions.md` | real | Agent edited its own instructions ("always add a trailing newline"). |
| 25 | PSRule#2973 | file_outside_ask | `src/PSRule.Tool/Program.cs` | FP (b) | CLI entry wiring for the new adapter (`AdapterBuilder.TryAdapter`); also moves the GitHub Actions detection, but "adapter ... to the CLI" is the ask. |
| 26 | AIShell#385 | file_outside_ask | `global.json` | real | .NET SDK pin changed 8.0.409 to 8.0.116; unrelated to formatting an Ollama model list. |
| 27 | s3-zip#113 | new_dependency | `normalize-path` | real | New runtime dependency in a fix for npm publish warnings (version, repository URL). |
| 28 | jekyll-relative-links#97 | ci_or_config | `.rubocop.yml` | real | Lint loosened: `RSpec/FilePath` excludes the new spec and two existing specs. |
| 29 | jekyll-relative-links#97 | file_outside_ask | `fixtures/.../another-page.md` | FP | Fixture for the regression spec. |
| 30 | jekyll-relative-links#97 | file_outside_ask | `fixtures/.../page-with-excerpt.md` | FP | Fixture for the regression spec. |
| 31 | azure-sdk-for-python#41693 | public_api_removed | `after_multiapi_combiner` | real | Part of a dropped feature (2 MB package-size check and its PR-body message); issue asked only to merge `sdk_package` into `sdk_generator` and update `generate_code`. |
| 32 | azure-sdk-for-python#41693 | public_api_removed | `check_package_size` | real | Same dropped feature (T1's example 4). |
| 33 | azure-sdk-for-python#41693 | public_api_removed | `get_private_package` | real | Same dropped feature. (#31 to #33 are one logical change.) |
| 34 | azure-sdk-for-python#41693 | public_api_removed | `generate_main` | FP | The function being merged away; `sdk_package.py` deleted as the issue asks. |
| 35 | lingo.dev#867 | file_outside_ask | `.changeset/few-boxes-sniff.md` | FP | Release note required by the repo's convention. |

**Totals:** 17 real (3 borderline), 18 FP. Strict 14 of 35 (40%); lenient 17 of 35 (49%).

| Kind | Extras | Real (strict to lenient) | Note |
|---|---|---|---|
| new_dependency | 1 | 1 | One sample; no precision claim possible. |
| ci_or_config | 4 | 2 to 3 | One rule bug (dependabot). |
| tests_removed | 2 | 0 | Both are moved tests. |
| public_api_removed | 8 | 7 | Mostly real behaviour removals; "public API" is a loose name for the Azure ones. |
| file_outside_ask | 20 | 4 to 6 | 14 FP: fix location, accompanying tests, fixtures, wiring, release notes. |

PR level: PRs with at least one real extra: crewAI, elastic, FilterLists, retina, PSRule, AIShell, s3-zip, jekyll, azure-sdk (9), plus kibo if borderline counts (10). PRs flagged **only** by false positives: compass, dotnet/sdk, maui, fsharp, autorest, lingo.dev (6 of 16). In the sample, that is about 10% of all PRs getting a card whose every extra is wrong, against 15 to 17% with a real extra. Recall was not measured (the 44 unflagged PRs were not hand-read); the bugs in section 1 show it is below 100%.

## 3. Ranked fixes (at most five)

1. **Stop gating on rule 5 as it stands.** It makes 20 of 35 extras at 20 to 30% precision. Either show rule 5 as information only (no "type the name"), or fix its two main sources: treat test files, fixtures and registration lists in the same change as inside when any changed source file is, and stop the repo or package name matching directories (pass the repo name in, or ignore directory tokens that equal the root package). Rules 1, 2 (after fix 3) and 4 are the ones with usable precision.
2. **Never print "Nothing beyond #N" for an abstained PR.** 11 of the 44 unflagged PRs (25%) are clean only because rule 5 had no anchor, and 3 of the 16 flagged PRs were unanchored. The card needs a third state ("could not place the issue; N files unchecked"), or the headline rate in the video is inflated.
3. **Remove the three remaining rule-level false positives:** add "dependabot" and "renovate" to the rule 2 mention words; in rule 3a, do not flag a deleted test when the same change adds at least as many test definitions in the same package, or when the issue names the directory or the source twin is deleted too.
4. **Close the supply-chain misses before the "Secure" claim is made:** URL and VCS requirements, `package.json` scripts (`postinstall`), pyproject tool config (ruff ignore), `CODEOWNERS`/`.npmrc`/`renovate.json`/`global.json`; make `defined_again` ignore test files; normalise `-`/`_` in rule 1.
5. **Pin and correct before anyone quotes this.** Record sha256 of the four parquet files, the duckdb and Python versions in `results/replay_predictions.json`, and commit the cache or its hashes; add AIDev credit to `README.md`. In `T1 report.md` fix example 3, the `json` note, the "nothing committed" line and the "both parts" line, so Lock v3 does not inherit them.
