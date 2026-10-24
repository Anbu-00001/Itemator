"""One passing and one failing fixture per check of tools/hardcode_audit.py, in temporary directories."""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "hardcode_audit.py"
spec = importlib.util.spec_from_file_location("hardcode_audit", SCRIPT)
assert spec and spec.loader
audit = importlib.util.module_from_spec(spec)
sys.modules["hardcode_audit"] = audit
spec.loader.exec_module(audit)

GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
           "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.com"}
SIGN = "Signed-off-by: T <t@example.com>"
RESULTS = {"summary": {"flagged": 16, "sample": 60, "rate": 0.2667}, "prs": [{"n": 7}]}


def write(root: Path, files: dict) -> Path:
    for name, content in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content if isinstance(content, str) else json.dumps(content))
    return root


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=GIT_ENV)


def repo(root: Path, files: dict, message: str = f"Start\n\n{SIGN}\n") -> Path:
    write(root, files)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return root


def msgs(check, root: Path) -> list[str]:
    return [str(f) for f in check(root)]


FROM = "<!-- from: results/a.json:{} -->"


# ---- check 1: numbers trace to results
def test_numbers_pass(tmp_path):
    readme = (
        f"Flagged 16 of 60 {FROM.format('summary.flagged')}{FROM.format('summary.sample')}\n"
        f"That is 27% {FROM.format('summary.rate')} and 26.7% {FROM.format('summary.rate')}\n"
        f"Seven {FROM.format('prs[0].n')} is spelled out but 7 is not\n"
        "Needs Python 3.12 and duckdb==1.5.6 and >=3.12, v1.2.3, released 2026-10-10 or Oct 27 2026, in 2026.\n"
        "Fixes issue 12, PR #34 and !56 at https://example.com/pull/99.\n"
        "1. A numbered list item\n"
    )
    write(tmp_path, {"README.md": readme.replace("is not\n", "is not " + FROM.format("prs[0].n") + "\n"), "results/a.json": RESULTS})
    assert msgs(audit.check_numbers, tmp_path) == []


def test_numbers_product_versions_exempt_but_counts_not(tmp_path):
    write(tmp_path, {"README.md": "Runs on GitLab 18.5 and duckdb 1.5.\nRuns on GitLab 5 times.\n"})
    assert [o[:11] for o in msgs(audit.check_numbers, tmp_path)] == ["README.md:2"]


def test_numbers_advisory_ids_exempt_but_counts_not(tmp_path):
    write(tmp_path, {"README.md": "PHP2Shell is CVE-2026-109618; OSV has MAL-2023-1681.\nCVE lists 7 flaws.\n"})
    assert [o[:11] for o in msgs(audit.check_numbers, tmp_path)] == ["README.md:2"]


def test_numbers_licence_versions_exempt_but_counts_not(tmp_path):
    write(tmp_path, {"README.md": "Data is CC BY 4.0; code is MIT, deps Apache-2.0 or GPL-3.0.\nCC BY flagged 4 PRs.\n"})
    assert [o[:11] for o in msgs(audit.check_numbers, tmp_path)] == ["README.md:2"]


def test_numbers_fail_without_source(tmp_path):
    write(tmp_path, {"README.md": "ok\nWe flagged 16 of 60 PRs.\n", "results/a.json": RESULTS})
    out = msgs(audit.check_numbers, tmp_path)
    assert len(out) == 2 and all(o.startswith("README.md:2:") for o in out)


def test_numbers_fail_wrong_value(tmp_path):
    write(tmp_path, {"docs/x.md": f"We flagged 17 {FROM.format('summary.flagged')}\n", "results/a.json": RESULTS})
    out = msgs(audit.check_numbers, tmp_path)
    assert any("docs/x.md:1:" in o and "'17'" in o for o in out)


def test_numbers_fail_stale_comment_and_bad_path(tmp_path):
    write(tmp_path, {"README.md": f"No number here {FROM.format('summary.flagged')}\nTwelve 5 {FROM.format('summary.nope')}\n",
                     "results/a.json": RESULTS})
    out = msgs(audit.check_numbers, tmp_path)
    assert any(o.startswith("README.md:1:") and "matches no number" in o for o in out)
    assert any(o.startswith("README.md:2:") and "does not resolve" in o for o in out)


def test_numbers_integers_are_exact(tmp_path):
    write(tmp_path, {"README.md": f"About 16 {FROM.format('summary.rate')}\n", "results/a.json": RESULTS})
    assert msgs(audit.check_numbers, tmp_path)


# ---- check 2: pre-registration
def prereg_files(tamper: bool = False) -> dict:
    pred = b'{"prs": []}'
    digest = hashlib.sha256(pred).hexdigest()
    return {"results/pred.json": pred.decode() + (" " if tamper else ""),
            "results/out.json": {"summary": {"predictions": "results/pred.json", "predictions_sha256": digest}}}


def test_prereg_pass(tmp_path):
    write(tmp_path, prereg_files())
    assert msgs(audit.check_prereg, tmp_path) == []


def test_prereg_fail_when_predictions_changed(tmp_path):
    write(tmp_path, prereg_files(tamper=True))
    out = msgs(audit.check_prereg, tmp_path)
    assert len(out) == 1 and out[0].startswith("results/out.json:") and "pre-registered hash" in out[0]


def test_prereg_fail_when_target_missing(tmp_path):
    files = prereg_files()
    del files["results/pred.json"]
    write(tmp_path, files)
    assert any("does not exist" in o for o in msgs(audit.check_prereg, tmp_path))


# ---- check 3: nothing seeded shown as live
def test_seeded_pass(tmp_path):
    write(tmp_path, {"README.md": "The numbers in `demo/run.json` are seeded, not live.\n\n- fixtures/a.txt is a simulated input\n",
                     "demo/run.json": "{}", "fixtures/a.txt": "x"})
    assert msgs(audit.check_seeded, tmp_path) == []


def test_seeded_fail_file_shown_as_live(tmp_path):
    write(tmp_path, {"README.md": "Look at the run in demo/run.json.\nIt seeded nothing here.\n", "demo/run.json": "{}"})
    out = msgs(audit.check_seeded, tmp_path)
    assert len(out) == 1 and out[0].startswith("README.md:1:")


def test_seeded_results_entry(tmp_path):
    results = {"prs": [{"pr_url": "https://example.com/o/r/pull/5", "seeded": True}]}
    ok = {"README.md": "The PR https://example.com/o/r/pull/5 is a seeded example.\n", "results/a.json": results}
    bad = {"README.md": "The PR https://example.com/o/r/pull/5 was caught live.\n", "results/a.json": results}
    write(tmp_path / "ok", ok)
    write(tmp_path / "bad", bad)
    assert msgs(audit.check_seeded, tmp_path / "ok") == []
    assert len(msgs(audit.check_seeded, tmp_path / "bad")) == 1


def test_seeded_number_sourced_from_seeded_entry(tmp_path):
    results = {"prs": [{"n": 7, "seeded": True}]}
    write(tmp_path, {"README.md": f"Caught 7 {FROM.format('prs[0].n')} live.\n", "results/a.json": results})
    assert len(msgs(audit.check_seeded, tmp_path)) == 1


# ---- check 4: banned words
def test_banned_pass(tmp_path):
    write(tmp_path, {"README.md": "Itemator lists extras. The gateway and trustworthy words are not whole words.\n",
                     "AGENTS.md": "Uses GitLab Credits. The cost is 500 credits per month.\n",
                     "docs/a.md": "Nothing to see.\n"})
    assert msgs(audit.check_banned, tmp_path) == []


@pytest.mark.parametrize("word", ["Guardian", "gate", "PROOF", "receipts", "Evidence", "ledger", "witness", "canary",
                                  "trust", "earned", "calibrated", "autopilot", "sentinel", "verdict", "risk score", "risk-scores", "credit"])
def test_banned_fail(tmp_path, word):
    write(tmp_path, {"README.md": "fine\n", "docs/a.md": f"line one\nan {word} here\n"})
    out = msgs(audit.check_banned, tmp_path)
    assert len(out) == 1 and out[0].startswith("docs/a.md:2:")


def test_banned_credits_need_billing(tmp_path):
    write(tmp_path, {"AGENTS.md": "A run earns credits for the team.\n"})
    out = msgs(audit.check_banned, tmp_path)
    assert len(out) == 1 and out[0].startswith("AGENTS.md:1:") and "credits" in out[0]


# ---- check 5: commit hygiene
def test_commits_pass(tmp_path):
    repo(tmp_path, {"a.txt": "x"})
    assert msgs(audit.check_commits, tmp_path) == []


def test_commits_fail_unsigned(tmp_path):
    repo(tmp_path, {"a.txt": "x"}, message="Start\n")
    out = msgs(audit.check_commits, tmp_path)
    assert len(out) == 1 and "no Signed-off-by" in out[0]


def test_commits_fail_coauthor(tmp_path):
    repo(tmp_path, {"a.txt": "x"}, message=f"Start\n\nCo-Authored-By: Bot <bot@example.com>\n{SIGN}\n")
    out = msgs(audit.check_commits, tmp_path)
    assert len(out) == 1 and "Co-Authored-By" in out[0]


SERVICE = "service_account_group_121124982_0123456789abcdef0123456789abcdef@noreply.gitlab.com"


def test_commits_exempt_a_service_account_commit_from_the_sign_off(tmp_path):
    repo(tmp_path, {"a.txt": "x"})
    write(tmp_path, {"b.txt": "y"})
    git(tmp_path, "add", "-A")
    git(tmp_path, "-c", f"user.email={SERVICE}", "commit", "-q", "-m", "Policy: stop asking about x", "--author", f"Flow <{SERVICE}>")
    assert msgs(audit.check_commits, tmp_path) == []


def test_commits_service_account_exemption_is_not_a_coauthor_exemption(tmp_path):
    repo(tmp_path, {"a.txt": "x"})
    write(tmp_path, {"b.txt": "y"})
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "Co\n\nCo-Authored-By: B <b@example.com>", "--author", f"Flow <{SERVICE}>")
    out = msgs(audit.check_commits, tmp_path)
    assert len(out) == 1 and "Co-Authored-By" in out[0]


def test_commits_a_lookalike_email_is_not_exempt(tmp_path):
    repo(tmp_path, {"a.txt": "x"})
    write(tmp_path, {"b.txt": "y"})
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "No sign-off", "--author", "Flow <service_account_group_1_abc@noreply.gitlab.com>")
    out = msgs(audit.check_commits, tmp_path)
    assert len(out) == 1 and "no Signed-off-by" in out[0]


def test_commits_an_email_that_only_contains_the_service_account_pattern_is_not_exempt(tmp_path):
    repo(tmp_path, {"a.txt": "x"})
    write(tmp_path, {"b.txt": "y"})
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "No sign-off", "--author", f"Flow <me.{SERVICE}>")
    out = msgs(audit.check_commits, tmp_path)
    assert len(out) == 1 and "no Signed-off-by" in out[0]


def _merge(tmp_path, message):
    repo(tmp_path, {"a.txt": "x"})
    git(tmp_path, "checkout", "-q", "-b", "side")
    write(tmp_path, {"b.txt": "y"})
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", f"Side\n\n{SIGN}\n")
    git(tmp_path, "checkout", "-q", "main")
    write(tmp_path, {"c.txt": "z"})
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", f"Main\n\n{SIGN}\n")
    git(tmp_path, "merge", "-q", "--no-ff", "side", "-m", message)


def test_commits_exempt_the_merge_button_commit(tmp_path):
    _merge(tmp_path, "Merge branch 'side' into 'main'\n\nSide\n\nSee merge request group/proj!7")
    assert msgs(audit.check_commits, tmp_path) == []


def test_commits_exempt_a_button_merge_of_two_edits_to_neighbouring_lines_of_one_file(tmp_path):
    repo(tmp_path, {"a.txt": "one\ntwo\nthree\nfour\nfive\nsix\n"})
    git(tmp_path, "checkout", "-q", "-b", "side")
    write(tmp_path, {"a.txt": "one\nTWO\nthree\nfour\nfive\nsix\n"})
    git(tmp_path, "commit", "-q", "-am", f"Side\n\n{SIGN}\n")
    git(tmp_path, "checkout", "-q", "main")
    write(tmp_path, {"a.txt": "one\ntwo\nthree\nFOUR\nfive\nsix\n"})
    git(tmp_path, "commit", "-q", "-am", f"Main\n\n{SIGN}\n")
    git(tmp_path, "merge", "-q", "--no-ff", "side", "-m", "Merge branch 'side' into 'main'\n\nSee merge request group/proj!7")
    assert msgs(audit.check_commits, tmp_path) == []


def test_commits_a_merge_that_carries_a_change_of_its_own_needs_a_sign_off(tmp_path):
    repo(tmp_path, {"a.txt": "x"})
    git(tmp_path, "checkout", "-q", "-b", "side")
    write(tmp_path, {"b.txt": "y"})
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", f"Side\n\n{SIGN}\n")
    git(tmp_path, "checkout", "-q", "main")
    write(tmp_path, {"c.txt": "z"})
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", f"Main\n\n{SIGN}\n")
    git(tmp_path, "merge", "-q", "--no-ff", "--no-commit", "side")
    write(tmp_path, {"sneaky.txt": "not in either parent"})
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "Merge branch 'side' into 'main'\n\nSee merge request group/proj!7")
    out = msgs(audit.check_commits, tmp_path)
    assert len(out) == 1 and "no Signed-off-by" in out[0]


def test_commits_another_groups_service_account_is_not_exempt(tmp_path):
    repo(tmp_path, {"a.txt": "x"})
    write(tmp_path, {"b.txt": "y"})
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "No sign-off", "--author", "Flow <service_account_group_999_0123456789abcdef0123456789abcdef@noreply.gitlab.com>")
    out = msgs(audit.check_commits, tmp_path)
    assert len(out) == 1 and "no Signed-off-by" in out[0]


def test_commits_a_merge_without_the_merge_request_line_needs_a_sign_off(tmp_path):
    _merge(tmp_path, "Merge branch 'side'")
    out = msgs(audit.check_commits, tmp_path)
    assert len(out) == 1 and "no Signed-off-by" in out[0]


def test_commits_a_single_parent_commit_saying_see_merge_request_needs_a_sign_off(tmp_path):
    repo(tmp_path, {"a.txt": "x"})
    write(tmp_path, {"b.txt": "y"})
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "Squash\n\nSee merge request group/proj!7")
    out = msgs(audit.check_commits, tmp_path)
    assert len(out) == 1 and "no Signed-off-by" in out[0]


def test_commits_fail_outside_git(tmp_path):
    assert msgs(audit.check_commits, tmp_path)


# ---- check 6: licences
PYPROJECT = '[project]\nname = "x"\ndependencies = ["duckdb==1.5.6"]\n[project.optional-dependencies]\ndev = ["pytest>=8"]\neval = ["Foo_Bar[extra]; python_version>\'3.9\'"]\n'


def lic(**entries) -> dict:
    return {k: v for k, v in entries.items()}


def test_licences_pass(tmp_path):
    write(tmp_path, {"pyproject.toml": PYPROJECT, "tools/licences.json": {"duckdb": {"spdx": "MIT"}, "pytest": {"spdx": "MIT"}, "foo-bar": {"spdx": "MIT"}}})
    assert msgs(audit.check_licences, tmp_path) == []


def test_licences_fail_unlisted_and_non_mit(tmp_path):
    write(tmp_path, {"pyproject.toml": PYPROJECT, "tools/licences.json": {"duckdb": {"spdx": "MIT"}, "pytest": {"spdx": "GPL-3.0-only"}}})
    out = msgs(audit.check_licences, tmp_path)
    assert any("pytest is GPL-3.0-only" in o for o in out) and any("Foo_Bar".lower().replace("_", "-") in o for o in out)


def test_licences_dev_only_needs_reason_and_dev_group(tmp_path):
    base = {"duckdb": {"spdx": "MIT"}, "foo-bar": {"spdx": "MIT"}}
    ok = {**base, "pytest": {"spdx": "MPL-2.0", "dev_only": True, "reason": "test runner, never shipped"}}
    no_reason = {**base, "pytest": {"spdx": "MPL-2.0", "dev_only": True}}
    runtime = {"duckdb": {"spdx": "MPL-2.0", "dev_only": True, "reason": "claimed"}, "pytest": {"spdx": "MIT"}, "foo-bar": {"spdx": "MIT"}}
    for name, table in (("ok", ok), ("no_reason", no_reason), ("runtime", runtime)):
        write(tmp_path / name, {"pyproject.toml": PYPROJECT, "tools/licences.json": table})
    assert msgs(audit.check_licences, tmp_path / "ok") == []
    assert any("no reason" in o for o in msgs(audit.check_licences, tmp_path / "no_reason"))
    assert any("not a dev group" in o for o in msgs(audit.check_licences, tmp_path / "runtime"))


# ---- check 7: secrets
def token(prefix: str, n: int) -> str:
    return prefix + "a1B2" * (n // 4)


def test_secrets_pass(tmp_path):
    repo(tmp_path, {"a.py": "x = 1\n", ".env.example": "KEY=\n", "n.txt": "glpat- and ghp_ alone are fine\n"})
    assert msgs(audit.check_secrets, tmp_path) == []


@pytest.mark.parametrize("content", [
    "t = '" + "glpat-" + "a1B2" * 5 + "'\n",
    "t = '" + "ghp_" + "a1B2" * 9 + "'\n",
    "t = '" + "github_pat_" + "a1B2" * 6 + "'\n",
    "-----BEGIN " + "RSA PRIVATE KEY-----\nabc\n",
])
def test_secrets_fail_patterns(tmp_path, content):
    repo(tmp_path, {"ok.txt": "fine\n", "src/leak.txt": "line\n" + content})
    out = msgs(audit.check_secrets, tmp_path)
    assert len(out) == 1 and out[0].startswith("src/leak.txt:2:")


def test_secrets_fail_tracked_env(tmp_path):
    repo(tmp_path, {".env": "A=1\n", "ok.txt": "x\n"})
    out = msgs(audit.check_secrets, tmp_path)
    assert out == [".env: a .env file is tracked in git"]


def test_secrets_untracked_env_is_not_tracked(tmp_path):
    repo(tmp_path, {".gitignore": ".env\n", ".env": "A=1\n"})
    assert msgs(audit.check_secrets, tmp_path) == []


# ---- check 8: attribution
AIDEV = {"summary": {"dataset": "hao-li/AIDev@v3"}}
GOOD_NOTICE = "Data: AIDev, licence CC BY 4.0.\n"


def test_attribution_pass_and_not_applicable(tmp_path):
    write(tmp_path / "ok", {"results/a.json": AIDEV, "NOTICE": GOOD_NOTICE, "README.md": "See [NOTICE](NOTICE).\n"})
    write(tmp_path / "na", {"results/a.json": {"summary": {"x": 1}}, "README.md": "No link.\n"})
    assert msgs(audit.check_attribution, tmp_path / "ok") == []
    assert msgs(audit.check_attribution, tmp_path / "na") == []


def test_attribution_fail_no_link(tmp_path):
    write(tmp_path, {"results/a.json": AIDEV, "NOTICE": GOOD_NOTICE, "README.md": "Mentions NOTICE in prose only.\n"})
    assert msgs(audit.check_attribution, tmp_path) == ["README.md: does not link NOTICE"]


def test_attribution_fail_notice_missing_terms(tmp_path):
    write(tmp_path, {"results/a.json": AIDEV, "NOTICE": "Data: AIDev.\n", "README.md": "[n](./NOTICE)\n"})
    out = msgs(audit.check_attribution, tmp_path)
    assert len(out) == 1 and "'CC BY 4.0'" in out[0]
    write(tmp_path / "none", {"results/a.json": AIDEV, "README.md": "[n](NOTICE)\n"})
    assert any("missing" in o for o in msgs(audit.check_attribution, tmp_path / "none"))


# ---- command line
def run_cli(root: Path):
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root)], capture_output=True, text=True, env=GIT_ENV)


def test_cli_exit_codes(tmp_path):
    repo(tmp_path / "good", {"README.md": "Plain words only.\n"})
    repo(tmp_path / "bad", {"README.md": "Plain words only.\n", "docs/a.md": "A verdict.\n"})
    good, bad = run_cli(tmp_path / "good"), run_cli(tmp_path / "bad")
    assert good.returncode == 0 and "FAIL" not in good.stdout
    assert bad.returncode == 1 and "FAIL  4. Banned words" in bad.stdout and "docs/a.md:1:" in bad.stdout


# ---- check 1 beyond the README: AGENTS.md, skills, the text of the web pages; --also for the Devpost text
def test_numbers_are_read_in_agents_skills_and_what_a_page_shows(tmp_path):
    write(tmp_path, {"README.md": "", "results/a.json": RESULTS, "AGENTS.md": "Flag 16 at most.\n",
                     "skills/x/SKILL.md": "Say 60.\n", "web/p.html": '<p>27%</p>\n<input\n  placeholder="918">\n<b title="x 5">y</b>\n'})
    got = msgs(audit.check_numbers, tmp_path)
    assert got == ["AGENTS.md:1: '16' has no <!-- from: results/<file>.json:<json.path> --> on this line",
                   "skills/x/SKILL.md:1: '60' has no <!-- from: results/<file>.json:<json.path> --> on this line",
                   "web/p.html:1: '27%' has no <!-- from: results/<file>.json:<json.path> --> on this line",
                   "web/p.html:2: '918' has no <!-- from: results/<file>.json:<json.path> --> on this line",
                   "web/p.html:4: '5' has no <!-- from: results/<file>.json:<json.path> --> on this line"]


def test_a_page_is_read_as_shown_with_its_sources_and_without_code(tmp_path):
    page = ('<!doctype html>\n<style>\n.a { width: 640px; }\n</style>\n<p data-n="3" class="c2">27% '
            f'{FROM.format("summary.rate")}</p>\n<script>\nconst n = 42;\n</script>\n<p>On CPython 3.12.</p>\n')
    write(tmp_path, {"README.md": "", "results/a.json": RESULTS, "web/p.html": page})
    assert msgs(audit.check_numbers, tmp_path) == []
    assert audit.shown_text(Path("p.html"), page).count("\n") == page.count("\n")       # line numbers stay the page's own


def test_an_example_line_is_exempt_and_only_that_line(tmp_path):
    write(tmp_path, {"README.md": "", "results/a.json": RESULTS, "skills/x/SKILL.md": "e.g. `1 thing beyond #12` <!-- example -->\nSay 60.\n"})
    assert msgs(audit.check_numbers, tmp_path) == ["skills/x/SKILL.md:2: '60' has no <!-- from: results/<file>.json:<json.path> --> on this line"]


def test_also_lists_numbers_the_repository_does_not_source_and_never_fails(tmp_path, capsys):
    write(tmp_path, {"README.md": f"Flagged 16 {FROM.format('summary.flagged')} and 27% {FROM.format('summary.rate')}\n",
                     "results/a.json": RESULTS, "draft.md": "16 flagged, 27%, and 12 of 12 asked.\nFor example 3 things <!-- example -->\n"})
    got = msgs(lambda r: audit.check_also(r, [r / "draft.md"]), tmp_path)
    assert got == [f"{tmp_path / 'draft.md'}:1: '12' is not a number the repository shows with a source"] * 2
    assert audit.main(["--root", str(tmp_path), "--only", "1", "--also", str(tmp_path / "draft.md")]) == 0
    assert "REVIEW  2 number(s)" in capsys.readouterr().out
