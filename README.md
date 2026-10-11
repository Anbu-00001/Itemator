# Itemator

**One click for what was asked. A name for anything more.**

When an agent or a new teammate opens a merge request, someone approves it, often without reading. Itemator lists what the change did beyond its linked issue. A GitLab Duo flow offers to move each extra into its own merge request, and the approver keeps an extra only by typing its name. Changes that stay inside the issue keep the normal one-click approval.

**Status:** in development for GitLab's *Life After Code* hackathon (Path A, Supervised). Every number in this README sits next to a pointer to the results file that produced it; a CI check enforces that.

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
