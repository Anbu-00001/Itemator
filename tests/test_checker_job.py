"""T20 item 8 and item 5: the itemator job runs the checker exported from the target branch (the job script in
ci/itemator-job.yml, run with sh on a local fixture repository), and without a policy file the facts are byte-for-byte
what the checker before T20 (commit 5bddaf6) wrote for every replay record in results/replay_v4_*.json,
apart from the fourth answer (T23) in each thread stub and in the card's todo line."""
import datetime
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from itemator import ci, policy as POL
from itemator.extras import Analysis, Extra
from test_ci import Repo, isolated  # noqa: F401  (autouse fixture)

ROOT = Path(__file__).resolve().parent.parent
STUB = """import json, os, sys
a = sys.argv[1:]
with open(a[a.index("--out") + 1], "w") as fh:
    json.dump({"who": WHO, "file": os.path.abspath(__file__), "cwd": os.getcwd(), "argv": a,
               "checker": os.environ.get("ITEMATOR_CHECKER"), "sha": os.environ.get("ITEMATOR_CHECKER_SHA")}, fh)
"""


def job_script() -> str:
    """The `- |` block under `script:` of the itemator job, dedented (no YAML library: the layout is fixed)."""
    path = ROOT / "ci" / "itemator-job.yml"
    if not path.exists():
        pytest.skip("no ci/itemator-job.yml in this copy")
    lines = path.read_text().split("\n")
    i = lines.index("itemator:")
    j = next(k for k in range(i + 1, len(lines)) if lines[k].strip() == "- |" and lines[k - 1].strip() == "script:")
    body = []
    for line in lines[j + 1:]:
        if line.strip() and not line.startswith("      "):
            break
        body.append(line[6:])
    return "\n".join(body)


def stub(who):
    return {"itemator/__init__.py": "", "itemator/ci.py": f"WHO = {who!r}\n" + STUB}


def run_job(repo, base_sha, tmp_path, target="same", branch="main", **extra_env):
    """`target` (T26 F1): the sha refs/remotes/origin/main points at ("same": base_sha; None: no such ref)."""
    tip = base_sha if target == "same" else target
    if tip:
        repo.git("update-ref", "refs/remotes/origin/main", tip)
    (tmp_path / "bin").mkdir(exist_ok=True)
    if not (tmp_path / "bin" / "python").exists():
        (tmp_path / "bin" / "python").symlink_to(sys.executable)
    (tmp_path / "tmp").mkdir(exist_ok=True)
    env = {"PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin", "HOME": str(tmp_path), "TMPDIR": str(tmp_path / "tmp"),
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "CI_PROJECT_DIR": str(repo.path), "CI_MERGE_REQUEST_DIFF_BASE_SHA": base_sha,
           "CI_MERGE_REQUEST_TARGET_BRANCH_NAME": branch, **extra_env}
    r = subprocess.run(["sh", "-c", job_script()], cwd=repo.path, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads((repo.path / "itemator.json").read_text())


def test_the_job_runs_the_target_branch_checker_from_outside_the_checkout(tmp_path):
    repo = Repo(tmp_path / "repo")
    base = repo.commit({**stub("base"), "README.md": "# demo\n"})
    repo.commit(stub("merge request"))                   # the MR rewrites its own checker
    out = run_job(repo, base, tmp_path, PYTHONPATH=str(repo.path))
    assert out["who"] == "base" and out["checker"] == "base" and out["sha"] == base
    assert not out["file"].startswith(str(repo.path) + "/") and not out["cwd"].startswith(str(repo.path) + "/")
    assert out["file"] == os.path.join(out["cwd"], "itemator", "ci.py")
    assert out["argv"] == ["--repo", str(repo.path), "--out", str(repo.path / "itemator.json")]


def test_first_introduction_falls_back_to_the_merge_request_checker(tmp_path):
    repo = Repo(tmp_path / "repo")
    base = repo.commit({"README.md": "# demo\n"})
    repo.commit(stub("merge request"))
    out = run_job(repo, base, tmp_path)
    assert out["who"] == "merge request" and out["checker"] == "merge_request"


@pytest.mark.parametrize("mangle", [str.upper, lambda s: s[:39], lambda s: s + "0", lambda s: "HEAD", lambda s: ""])
def test_a_base_that_is_not_40_hex_characters_is_never_exported(tmp_path, mangle):
    repo = Repo(tmp_path / "repo")
    base = repo.commit({**stub("base"), "README.md": "# demo\n"})
    repo.commit(stub("merge request"))
    out = run_job(repo, mangle(base), tmp_path, target=None)
    assert out["who"] == "merge request" and out["checker"] == "merge_request"
    out = run_job(repo, mangle(base), tmp_path, target=base)          # T26 F1: the target tip does not need it
    assert out["who"] == "base" and out["checker"] == "base" and out["sha"] == base


def fork_tip_mr(repo):
    fork = repo.commit({**stub("fork point"), "README.md": "# demo\n"})
    tip = repo.commit(stub("target tip"))
    repo.git("checkout", "-q", "-b", "mr", fork)
    repo.commit(stub("merge request"))
    return fork, tip


def test_the_job_runs_the_checker_of_the_target_branch_tip_not_of_the_merge_base(tmp_path):
    repo = Repo(tmp_path / "repo")
    fork, tip = fork_tip_mr(repo)
    out = run_job(repo, fork, tmp_path, target=tip)
    assert out["who"] == "target tip" and out["checker"] == "base" and out["sha"] == tip


@pytest.mark.parametrize("branch", ["main", "nope", "main^{tree}", "../main", "-x"])
def test_without_the_target_ref_the_job_falls_back_to_the_merge_base(tmp_path, branch):
    repo = Repo(tmp_path / "repo")
    fork, tip = fork_tip_mr(repo)
    out = run_job(repo, fork, tmp_path, target=None, branch=branch)
    assert out["who"] == "fork point" and out["checker"] == "base" and out["sha"] == fork


def test_the_real_checker_runs_from_an_exported_copy(tmp_path):
    """`python -m itemator.ci` started in another directory, with the checkout and output as arguments."""
    r = subprocess.run([sys.executable, "-E", "-m", "itemator.ci", "--repo", str(tmp_path), "--out", str(tmp_path / "o.json")],
                       cwd=ROOT, env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=60)
    assert r.returncode == 2 and "not a merge request pipeline" in r.stderr


# ---- no policy file: the facts are what the checker before T20 wrote

def old_ci():
    r = subprocess.run(["git", "-C", str(ROOT), "show", "5bddaf6:itemator/ci.py"], capture_output=True, text=True)
    if r.returncode:
        pytest.skip("commit 5bddaf6 is not in this clone")
    spec = importlib.util.spec_from_loader("ci_before_t20", loader=None)
    mod = importlib.util.module_from_spec(spec)
    exec(compile(r.stdout, "ci_before_t20.py", "exec"), mod.__dict__)
    return mod


def cached_files() -> dict:
    out = {}
    for p in sorted((ROOT / "eval" / "cache").glob("*.json")):
        files = json.loads(p.read_text()).get("files")
        if files:
            out[hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()] = files
    return out


# T23: the stub and the card's todo line gained a fourth answer, `remove`; nothing else in the facts may differ.
OLD_TAIL = "To move it into its own MR, reply `split`. If this is not really an extra, reply `not an extra`."
NEW_TAIL = ("To move it into its own MR, reply `split`. To drop it from this MR, reply `remove`. "
            "If this is not really an extra, reply `not an extra`.")
OLD_TODO = 'Type each name in its thread to keep it, or reply "split" to move it to its own MR.'
NEW_TODO = (ci.WELCOME + ' Type each name in its thread to keep it, or reply "split" to move it to its own MR, "remove" to drop it. '
            + ci.CONSENT)    # + the consent line, and (T64) the welcome line before it
OLD_CAVEAT = "No one but the author described this change."     # T64 rewords it


MANIFEST = re.compile(r"pyproject\.toml|package\.json|requirements(?:-[^/]*)?\.txt|go\.mod|Cargo\.toml|Gemfile")
CONFIG = (".yml", ".yaml", ".toml", ".json", ".cfg", ".ini")


def offered(x: dict, by_path: dict) -> tuple:
    """T26 F4, written again here from the react prompt's Step 5a part 3: what a thread may offer."""
    name = x["path"].rsplit("/", 1)[-1]
    manifest = bool(MANIFEST.fullmatch(name))
    grouped = "detail" in x["plain_facts"]
    if x["kind"] == "ci_or_config" and x["name"] == x["path"] and not x["detail"] and not manifest and (
            name in (".gitlab-ci.yml", "Dockerfile") or name.startswith("Dockerfile.") or name.endswith(CONFIG)):
        return ("split", "remove")
    if x["kind"] == "new_dependency" and manifest and (
            not x["detail"] or (grouped and len(", ".join(d["name"] for d in x["plain_facts"]["detail"])) <= 1000)):
        return ("split", "remove")
    f = by_path.get(x["path"]) or {}
    if x["kind"] in ("stray_file", "binary_or_large_added", "build_output_added") and x["name"] == x["path"] \
            and f.get("status") == "added":
        return ("remove",)
    return ()


def new_tail(offers) -> str:
    return (("To move it into its own MR, reply `split`. " if "split" in offers else "")
            + ("To drop it from this MR, reply `remove`. " if "remove" in offers else "")
            + "If this is not really an extra, reply `not an extra`.")


def with_remove(before: dict, by_path: dict, seen: dict) -> tuple[dict, int]:
    """The facts as the checker before T20 wrote them, with only the T23 todo wording and the T26 answers put in;
    and how many strings changed."""
    out, n = json.loads(json.dumps(before)), 0
    for e in out["extras"]:
        assert e["thread_stub"].endswith(OLD_TAIL) and e["thread_stub"].count(OLD_TAIL) == 1
        offers = offered(e, by_path)
        seen[offers] = seen.get(offers, 0) + 1
        e["thread_stub"], n = e["thread_stub"][:-len(OLD_TAIL)] + new_tail(offers), n + 1
        e["thread_stub"] = e["thread_stub"].replace("To keep it, reply with its exact name. ", ci.KEEP + " ")     # T64
    if out["card"]["todo_line"] == OLD_TODO:
        out["card"]["todo_line"], n = NEW_TODO, n + 1
    for key in ("final_line", "caveat_line"):
        if OLD_CAVEAT in (out["card"].get(key) or ""):
            out["card"][key], n = out["card"][key].replace(OLD_CAVEAT, ci.AUTHOR_CAVEAT), n + 1
    return out, n


def test_replay_records_pass_through_unchanged_without_a_policy(monkeypatch):
    paths = sorted((ROOT / "results").glob("replay_v4_*.json"))
    if not paths:
        pytest.skip("no results/ in this copy")
    old, cache = old_ci(), cached_files()
    now = datetime.datetime(2026, 10, 11, tzinfo=datetime.timezone.utc)
    issues = [{"iid": 12, "ref": "#12", "title": "t", "description": "d", "author_id": 1}]
    seen = with_files = rewritten = 0
    offers = {}
    for path in paths:
        for rec in json.loads(path.read_text())["prs"]:
            v4 = rec.get("v4", rec)
            a = Analysis([Extra(x["kind"], x["path"], x["name"], x["why"], tuple(x["detail"])) for x in v4["extras"]],
                         unplaced=list(v4["unplaced"]))
            monkeypatch.setattr(ci.X, "analyse", lambda *_, **__: a)
            files = cache.get(rec["files_sha256"], [])
            with_files += bool(files)
            kw = dict(mr_iid=5, mr_title="t", mr_description="", mr_author_id=2, issues=issues,
                      issues_from="closes_issues", files=files, repo=rec["repo"], base_sha="a" * 40,
                      head_sha="b" * 40, warnings=[], now=now)
            before, changed = with_remove(old.facts(**kw), {f["filename"]: f for f in files}, offers)
            rewritten += changed
            after = ci.facts(**kw, policy=POL.Policy(sha="a" * 40), checker={"source": "base", "sha": "a" * 40})
            assert after["policy"]["ignored_extras"] == [] and after["policy"]["found"] is False
            rest = {k: v for k, v in after.items() if k not in ("policy", "checker")}
            assert json.dumps(rest, indent=2) == json.dumps(before, indent=2), rec["pr_url"]
            seen += 1
    assert seen == 240 and rewritten > 0 and offers.get(("split", "remove")) and offers.get(())
    assert with_files > 0 or not cache                  # the anchors and the scan ran on real diffs too
    print(f"{seen} replay records, {with_files} with their cached diffs, offers {offers}")


def test_the_policy_job_runs_even_when_an_earlier_job_failed():
    """The job is injected into the last stage: without `when: always` it is skipped when any earlier job fails, and the card gets no facts."""
    text = (ROOT / "ci" / "itemator-job.yml").read_text()
    assert "\n  stage: .pipeline-policy-post\n" in text
    assert '  rules:\n    - if: $CI_PIPELINE_SOURCE == "merge_request_event"\n      when: always\n' in text


def _job(repo, base, tmp_path):
    repo.git("update-ref", "refs/remotes/origin/main", base)
    (tmp_path / "bin").mkdir(exist_ok=True)
    if not (tmp_path / "bin" / "python").exists():
        (tmp_path / "bin" / "python").symlink_to(sys.executable)
    (tmp_path / "tmp").mkdir(exist_ok=True)
    env = {"PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin", "HOME": str(tmp_path), "TMPDIR": str(tmp_path / "tmp"),
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "CI_PROJECT_DIR": str(repo.path),
           "CI_MERGE_REQUEST_DIFF_BASE_SHA": base, "CI_MERGE_REQUEST_TARGET_BRANCH_NAME": "main"}
    return subprocess.run(["sh", "-c", job_script()], cwd=repo.path, env=env, capture_output=True, text=True, timeout=60)


EXTRA = ('{"extras": [{"kind": "stray_file", "path": "x.sh", "name": "x.sh", "why": "w", '
         '"anchor": {"new_path": "x.sh", "new_line": 2}, "plain_facts": {}}]}')


@pytest.mark.parametrize("code", [0, 1, 2])
def test_the_reports_never_change_the_checkers_result(tmp_path, code):
    repo = Repo(tmp_path / "repo")
    ci_py = f"import sys\na = sys.argv[1:]\nopen(a[a.index('--out') + 1], 'w').write({EXTRA!r})\nsys.exit({code})\n"
    base = repo.commit({"itemator/__init__.py": "", "itemator/ci.py": ci_py,
                        **{f"itemator/{n}": (ROOT / "itemator" / n).read_text() for n in ("glreports.py", "sci.py")}})
    r = _job(repo, base, tmp_path)
    assert r.returncode == code, r.stderr
    cq = json.loads((repo.path / "gl-code-quality-report.json").read_text())
    assert [(f["location"]["path"], f["location"]["lines"]["begin"]) for f in cq] == [("x.sh", 2)]
    assert (repo.path / "metrics.txt").read_text().startswith("itemator_extras 1\n")


def test_a_target_branch_without_the_reports_module_still_passes(tmp_path):
    repo = Repo(tmp_path / "repo")
    base = repo.commit(stub("base"))
    r = _job(repo, base, tmp_path)
    assert r.returncode == 0, r.stderr
    assert (repo.path / "itemator.json").exists() and not (repo.path / "gl-code-quality-report.json").exists()


def test_the_job_uploads_both_reports():
    text = (ROOT / "ci" / "itemator-job.yml").read_text()
    assert "    reports:\n      codequality: gl-code-quality-report.json\n      metrics: metrics.txt\n" in text
