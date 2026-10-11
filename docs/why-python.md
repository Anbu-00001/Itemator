# Why Itemator is written in Python

Large systems are moving to Rust, so we checked whether Itemator should too. We asked six research agents to study Rust, C++, Go and TypeScript, and we measured the one thing a faster language would change: how long the rules take. We kept Python. The reasons, in order of weight:

## 1. Speed is not the problem
On the 180 real agent changes we replayed, the rules take a median of 0.48 <!-- from: results/timing_rules.json:median_ms --> thousandths of a second per change, and 80 <!-- from: results/timing_rules.json:max_ms --> thousandths for the largest (504 <!-- from: results/timing_rules.json:slowest.files --> files). All 180 <!-- from: results/timing_rules.json:prs_timed --> together take 0.39 <!-- from: results/timing_rules.json:total_s --> seconds. The only slow part of Itemator is waiting for the network, and no language speeds that up. Reproduce it with `.venv/bin/python -I eval/time_rules.py`.

## 2. A rewrite would change no result and cost most of our time
The agents' estimates for porting the rules, the CI job, the tests and the replay (the full range across their reports):

| Language | Score for a rewrite (out of 10 <!-- from: results/language_study.json:scale.max_score -->) | Extra days | Main reason |
|---|---|---|---|
| Rust | 1 <!-- from: results/language_study.json:rewrite_candidates.rust.score --> | 8 <!-- from: results/language_study.json:rewrite_candidates.rust.days_min --> to 13 <!-- from: results/language_study.json:rewrite_candidates.rust.days_max --> | No gain over a sub-millisecond run; heavy builds |
| C++ | 1 <!-- from: results/language_study.json:rewrite_candidates.cpp.score --> | 7 <!-- from: results/language_study.json:rewrite_candidates.cpp.days_min --> to 13 <!-- from: results/language_study.json:rewrite_candidates.cpp.days_max --> | No mature MIT library for reading diffs |
| Go | 2 <!-- from: results/language_study.json:rewrite_candidates.go.score --> | 6 <!-- from: results/language_study.json:rewrite_candidates.go.days_min --> to 11 <!-- from: results/language_study.json:rewrite_candidates.go.days_max --> | A good language, no gain for this workload |
| TypeScript | 2 <!-- from: results/language_study.json:rewrite_candidates.typescript.score --> | 4 <!-- from: results/language_study.json:rewrite_candidates.typescript.days_min --> to 10 <!-- from: results/language_study.json:rewrite_candidates.typescript.days_max --> | No gain in bug-catching; the Duo agent environment blocks the npm registry |

These are model-made estimates. We had 15 <!-- from: results/language_study.json:scale.days_left_at_study --> days left, and the three measurement rounds we published came from the Python code.

## 3. GitLab's own platform runs Python
GitLab's default Duo flow image carries Python, Go, Ruby, Node and Java, and no Rust or C/C++ compiler. GitLab's AI backend is 93.54 <!-- from: results/language_study.json:gitlab_language_share_percent.duo_ai_gateway_python -->% Python, and the organisers' reference project is 62.83 <!-- from: results/language_study.json:gitlab_language_share_percent.hackathon_reference_project_python -->% Python. GitLab's AI Catalog tooling is JavaScript (99.77 <!-- from: results/language_study.json:gitlab_language_share_percent.ai_catalog_component_javascript -->%), but its Duo agent environment blocks the npm registry. Among the live hackathon entries, 44 <!-- from: results/language_study.json:hackathon_field.python_led --> lead with Python, 28 <!-- from: results/language_study.json:hackathon_field.javascript_or_typescript_led --> with JavaScript or TypeScript, 3 <!-- from: results/language_study.json:hackathon_field.go --> with Go and 2 <!-- from: results/language_study.json:hackathon_field.rust --> with Rust.

## 4. A port has real traps
Regular expressions differ between languages (Go and Rust have no look-around, and string splitting, JSON output and sorting differ in small ways), so a port would have to prove it gives byte-identical answers on the 180 <!-- from: results/timing_rules.json:prs_timed --> real changes. A Rust port of the replay would have to compile DuckDB from C++.

## What a compiled language would give, and when we would use one
The honest gain is a single installable file for companies, which a pinned Python container image gives most of. If a customer has changes of thousands of files, the rules are one self-contained function (issue text and changed files in, extras out); the 180 <!-- from: results/timing_rules.json:prs_timed --> cached changes and the three measurement rounds would be the acceptance tests for a port.
