# Itemator

**One click for what was asked. A name for anything more.**

When an AI agent or a new teammate opens a merge request, someone approves it, often with one click. Anthropic reports that Claude Code users approve 93% <!-- from: results/external_figures.json:approval_rate_claude_code_permission_prompts.value --> of permission prompts, and calls the result approval fatigue ([source](https://www.anthropic.com/engineering/claude-code-auto-mode)). A merge request has the same problem: the change that was asked for is easy to check, and the extras that came with it are not.

Itemator lists what a merge request changed beyond its linked issue, and asks a person to name each extra before it merges. Changes that stay inside the issue keep the normal one-click approval. Other tools flag out-of-scope changes and leave one override for the whole merge request; here each extra gets its own thread, a typed answer, and a record of who decided.

**On a real agent.** We gave GitLab's own Developer Flow the issue "make the itemator job faster". It changed only `.gitlab-ci.yml`, a file the issue never mentions. Itemator opened a thread on that file, the approver typed its name, and the flow recorded who kept it.

**Status:** built for GitLab's *Life After Code* hackathon (Path A, Supervised). Every number in this README sits next to a pointer to the results file that produced it, and a CI check (`tools/hardcode_audit.py`) enforces that.

## How it works
1. **A CI job lists the extras.** The `itemator` job reads the merge request's diff and its linked issue and applies fixed rules (`itemator/extras.py`): a new dependency, a CI or config change, removed tests, a removed public function, deleted generated code, a committed binary, large file or build output, a version bump, a stray file. No model decides whether an extra exists. It writes `itemator.json`.
2. **A GitLab Duo flow posts the card.** `flows/itemator_card.yml` starts by itself when the pipeline of a merge request a person opened finishes. In our runs GitLab did not start the flow from the pipeline of a merge request an agent opened, so for such a merge request, a person assigns the card account as reviewer, which is a normal reviewer step. The card is two lines: what is beyond the issue, and what the approver does next. Each extra gets its own resolvable thread on the line it changed, and the merge request is set to Draft.
3. **The approver answers in the thread** with one word each: the extra's exact name keeps it, `not an extra` dismisses it, `split` moves a CI or config file or a package manifest into its own merge request, `remove` takes it back out of this one (like `split`, only for whole CI or config files, or a manifest whose only change is the named package; `remove` also takes back a file the merge request adds). The thread offers only the answers the flow accepts for that extra. `flows/itemator_react.yml` reads the answers when someone mentions its account or marks the merge request ready. It records who typed what, reopens a thread that was resolved without a name, and takes Draft off when every extra is settled. Its summary lists each extra with who decided, and says so when the author typed every answer.
4. **For a new dependency the thread also carries facts from PyPI, npm or crates.io, and OSV**: whether the package exists, when it was first released, how many releases it has, its licence as the publisher declares it, and the number of known advisories. Only facts; no score. The lookup validates every name, reaches four hosts, and never fails the job.
5. **A team can set its own rules in `.itemator.toml`**, read from the branch the merge request targets, so the merge request cannot change the rules it is judged by. The file can require that someone other than the author names each extra, or quiet whole kinds of extras and paths; it can never quiet a binary file, a change to the policy itself, or a dependency the registry did not find. The `itemator` job also runs the checker exported from the target branch, and ignores git attributes in the checkout, so a merge request cannot hide its diff.

6. **Two Agent Skills** (`skills/`) sit in `skills/`; GitLab's Developer Flow read the first one with no setup (one run, below). `stay-inside-the-issue` is for an agent that opens a merge request: keep to the issue, and list anything that needs a person's decision under a `Beyond the issue` heading in the description. `answer-an-itemator-card` helps whoever reads the card: what the lines and the four answers mean. It explains and never answers for the approver.

To install it in your own project, see [docs/setup.md](docs/setup.md).

**Real agent runs.** We assigned two small issues to GitLab's own Developer Flow. For the first (look up registry facts in parallel) the agent changed only the code and its tests, and the card said so. For the second ("make the itemator job faster") it changed only `.gitlab-ci.yml`, a file the issue never mentions: Itemator flagged it, the approver typed the name, and the flow settled it. An agent that changes how a job runs is doing what it was asked, and a person still decides to keep it. We then added the first skill and gave the Developer Flow the same issue again: this time its description ended with a `Beyond the issue` section naming `.gitlab-ci.yml` and why. That is one run on one issue, so it shows that the skill is read, not how often it helps. The rules still flag the file either way; the skill only makes the agent say it.

Every step ran live on GitLab.com in this project, on throwaway merge requests and issues in this project, closed afterwards. The merge requests that tested naming, `split` and `remove` were prepared by us with planted extras (a made-up package name, a comment line in the CI file, a backup file). The two Developer Flow runs above were not prepared.

## How often agent pull requests get a second look
Itemator exists because a merge request that changes more than its issue asked for depends on someone noticing. The same AIDev data shows how often a human comments on these pull requests. Of the 1610 <!-- from: results/review_stats.json:overall.merged --> merged agent pull requests that link an issue (in public repositories with a permissive licence):

- 59% <!-- from: results/review_stats.json:overall.shares.merged_no_human_inline_comment --> had no comment by a human on any line of the diff.
- 18% <!-- from: results/review_stats.json:overall.shares.merged_no_human_review --> had no review by a human at all.
- Of those that did have a human review, 32% <!-- from: results/review_stats.json:overall.shares.merged_human_reviewed_only_empty_approvals --> held only approvals with no text.
- The median time from opening to merging was 1118.9 <!-- from: results/review_stats.json:overall.time.median_minutes --> minutes, so these are not instant merges.

This does not say anyone was careless. Reviews and talk outside GitHub are invisible here, an empty approval may follow a careful read, and the pool is mostly one agent (Copilot). It sizes how often a human leaves a written trace on a line, which is what an extra needs to be caught. Of the 8 <!-- from: results/review_stats.json:flagged.merged --> merged pull requests that rules v4 flagged in our samples, 0 <!-- from: results/review_stats.json:flagged.merged_with_human_inline_comment --> had a human comment on any line. The definitions and the per-agent split are in [results/review_stats.json](results/review_stats.json).

## What we measured
The rules were checked on real pull requests that coding agents opened and linked to an issue, taken from the AIDev dataset by a seeded random draw. Four samples of sixty: the rules were tuned on the first, and for each later sample the next version of the rules was committed before that sample was drawn. For every flagged pull request, a language model read the diff against the issue and said whether at least one extra was real.

| Sample | Rules | Use | Flagged of scored | Held a real extra (strict) | Held a real extra (lenient) |
|---|---|---|---|---|---|
| A | v1 | tuning | 16 <!-- from: results/precision_audits.json:samples[0].prs_flagged --> of 60 <!-- from: results/precision_audits.json:samples[0].prs_scored --> | 9 <!-- from: results/precision_audits.json:samples[0].prs_with_real_strict --> | 10 <!-- from: results/precision_audits.json:samples[0].prs_with_real_lenient --> |
| B | v2 | held out | 12 <!-- from: results/precision_audits.json:samples[1].prs_flagged --> of 60 <!-- from: results/precision_audits.json:samples[1].prs_scored --> | 5 <!-- from: results/precision_audits.json:samples[1].prs_with_real_strict --> | 8 <!-- from: results/precision_audits.json:samples[1].prs_with_real_lenient --> |
| C | v3 | held out | 5 <!-- from: results/precision_audits.json:samples[2].prs_flagged --> of 60 <!-- from: results/precision_audits.json:samples[2].prs_scored --> | 3 <!-- from: results/precision_audits.json:samples[2].prs_with_real_strict --> | 3 <!-- from: results/precision_audits.json:samples[2].prs_with_real_lenient --> |
| D | v4 | held out | 8 <!-- from: results/precision_audits.json:samples[3].prs_flagged --> of 60 <!-- from: results/precision_audits.json:samples[3].prs_scored --> | 4 <!-- from: results/precision_audits.json:samples[3].prs_with_real_strict --> | 5 <!-- from: results/precision_audits.json:samples[3].prs_with_real_lenient --> |

Read this table with its limits next to it:
- **The labels are one model's reading.** There is one reader per sample, no second reader, and no check against what maintainers later did. Strict means a clear extra; lenient also counts borderline calls. The four audit notes, with every borderline call, are in [results/audits/](results/audits/).
- **The samples are small.** On the three held-out samples together, the card flagged 25 <!-- from: results/precision_audits.json:held_out_pooled.prs_flagged --> pull requests, and 12 <!-- from: results/precision_audits.json:held_out_pooled.prs_with_real_strict --> of them held a clear extra (a range of 30% <!-- from: results/precision_audits.json:held_out_pooled.strict_interval_95[0] --> to 67% <!-- from: results/precision_audits.json:held_out_pooled.strict_interval_95[1] --> at 95% <!-- from: results/precision_audits.json:confidence_level --> confidence). The rules changed between samples, so this is a plain count, not a controlled comparison, and we do not claim a later version is better.
- **Every version was fixed on earlier samples, and the audits list what each new version still gets wrong.** For example, on sample D every new-dependency flag was a package the changed code already used.
- About 14% <!-- from: results/precision_audits.json:held_out_pooled.prs_flagged_share --> of the pull requests were flagged, so most merge requests keep the one-click path.

## Related tools
Several tools already flag changes beyond the ask. As their own pages describe them on 2026-10-11, none makes the approver decide each extra by name inside GitLab:

| Tool | What it does | What it leaves to the approver |
|---|---|---|
| CodeRabbit, Issue Assessment | Checks a pull request against its linked issue for out-of-scope changes; warns by default, can block | One override for the whole pull request |
| Prelint | Lists decisions nobody asked for, with optional Agree buttons | Approval is optional; no GitLab support on its page |
| ScopeDiff, unasked, MergeWarden | Compare a change with declared paths (ScopeDiff, MergeWarden) or with the agent's prompt (unasked), locally or in CI | Block the whole run, or only report |
| GitLab Code Review Flow | Reviews a merge request from its title, description and diff | The linked issue is not one of its inputs |

Itemator's claim is narrower than detection: one thread per extra, a typed name, in GitLab, against the linked issue.

## Which lifecycle stages it touches
We count a stage only where Itemator reads or writes something in it:

| Stage | What Itemator does there |
|---|---|
| Plan | Reads the linked issue and checks the change against what it says |
| Create | Reviews the merge request, opens one thread per extra, moves or removes an extra |
| Verify | Runs as a CI job on every merge request pipeline; starts a Duo flow when it finishes |
| Package | Looks up new dependencies on their public registries |
| Secure | Shows advisories and licences for new dependencies; flags committed binaries and build output |
| Configure | Reads a team policy from the target branch; the flows and skills are set up per project |
| Govern | Records who decided each extra; the policy can require a second person |

We do not touch Release or Monitor.

## Known limits
- **Draft, not a lock.** The role we hold in this project cannot turn on "All threads must be resolved", so an unnamed extra puts the merge request in Draft but does not lock the merge button. A project owner can add that setting.
- **The job is defined in the merge request's own CI file.** A merge request that rewrites the `itemator` job can hide its extras. Real use needs the job pulled in from a protected include or a pipeline execution policy that the merge request cannot edit; the role we hold here cannot set that up.
- **Author-typed names.** A solo author can type every name. The summary says when that happened, instead of hiding it. With `other_person_required` in the team policy, the author's own replies do not count; we tested that a second account's replies do.
- **Rules miss things.** For example, a one-line edit of a dependency list in `pyproject.toml` was missed until a live test found it (fixed in rules v4). The audits list more.
- **The approved event is untested.** The flow can react when a merge request is approved, but a second approver is needed to test it, and we have not.
- **No hook on merge.** GitLab's merge trigger is off by default, so no record is written at the moment of merging; the summary note lists who named what once the last extra is settled.
- **Split and remove are narrow.** Both take whole CI or config files, or a manifest whose only change is the named package; remove also takes back a file the merge request adds. Anything else is refused with a reason.
- **Anyone who can comment can answer.** On a public project any GitLab user can type a name or `not an extra`; only `split` and `remove` are limited to the author, assignees and reviewers.
- **A model follows the reaction steps.** Code decides which extras exist; the Duo model checks replies with the fixed string tests in `flows/itemator_react.yml`. It passed our live tests; we have not measured how often it misreads a reply.
- **Typing is not reading.** We have not measured whether typing a name changes what approvers do. What it changes for certain is the record: each extra says who kept it. Recall is not measured either, only precision.

## Why Python
We checked whether Itemator should be written in Rust, Go, TypeScript or C++ instead. We kept Python: speed is not the problem, and a rewrite would cost most of our remaining time for no change in any result. Research agents scored each rewrite (model estimates, not measurements):

| Language | Score for a rewrite (out of 10 <!-- from: results/language_study.json:scale.max_score -->) | Extra days | Why not |
|---|---|---|---|
| Rust | 1 <!-- from: results/language_study.json:rewrite_candidates.rust.score --> | 8 <!-- from: results/language_study.json:rewrite_candidates.rust.days_min --> to 13 <!-- from: results/language_study.json:rewrite_candidates.rust.days_max --> | No gain over a sub-millisecond run; heavy builds; a much bigger image |
| C++ | 1 <!-- from: results/language_study.json:rewrite_candidates.cpp.score --> | 7 <!-- from: results/language_study.json:rewrite_candidates.cpp.days_min --> to 13 <!-- from: results/language_study.json:rewrite_candidates.cpp.days_max --> | No mature MIT library for reading diffs |
| Go | 2 <!-- from: results/language_study.json:rewrite_candidates.go.score --> | 6 <!-- from: results/language_study.json:rewrite_candidates.go.days_min --> to 11 <!-- from: results/language_study.json:rewrite_candidates.go.days_max --> | A good language, no gain for this workload |
| TypeScript | 2 <!-- from: results/language_study.json:rewrite_candidates.typescript.score --> | 4 <!-- from: results/language_study.json:rewrite_candidates.typescript.days_min --> to 10 <!-- from: results/language_study.json:rewrite_candidates.typescript.days_max --> | No gain in bug-catching; the Duo agent environment blocks the npm registry |

On the 180 <!-- from: results/timing_rules.json:prs_timed --> real agent changes we replayed, the rules take a median of 0.48 <!-- from: results/timing_rules.json:median_ms --> thousandths of a second per change, and 0.39 <!-- from: results/timing_rules.json:total_s --> seconds for all of them. The full reasoning, with every number traced to a file, is in [docs/why-python.md](docs/why-python.md).

## Licence
MIT. See [LICENSE](LICENSE). The evaluation uses the AIDev dataset (CC BY 4.0), fetched by script and not redistributed; see [NOTICE](NOTICE).
