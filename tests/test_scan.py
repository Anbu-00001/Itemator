"""Scan history (itemator/scan.py): real git merges in tmp, a fake GitLab API, no network."""
import json
import os
import subprocess
import urllib.request

import pytest

from itemator import scan

API = "https://gitlab.example/api/v4"
LIST = "/projects/7/merge_requests?state=merged&target_branch=main&order_by=merged_at&sort=desc&per_page=100&page=1"
PARSER = "def parse(s):\n    return s.split(',')\n"
FIXED = "def parse(s):\n    return [x for x in s.split(',') if x]\n"
ISSUE = {"iid": 12, "project_id": 7, "title": "Parser drops trailing comma", "author": {"id": 1},
         "description": "The parser in src/parser.py keeps an empty item after a trailing comma.",
         "web_url": "https://gitlab.example/grp/showcase/-/issues/12"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for k, v in {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "T",
                 "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}.items():
        monkeypatch.setenv(k, v)

    def no_network(*a, **k):
        raise AssertionError("a test reached the network")
    monkeypatch.setattr(urllib.request, "urlopen", no_network)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def commit(repo, files, msg="change"):
    for name, content in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(content)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--no-verify", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def history(tmp_path):
    """main: base; !1 merged with a merge commit (the fix and a Dockerfile); !2 landed as one squash commit (the fix only)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commit(repo, {"src/parser.py": PARSER, "README.md": "# demo\n"})
    git(repo, "switch", "-q", "-c", "one")
    commit(repo, {"src/parser.py": FIXED, "Dockerfile": "FROM python:3.12\n"})
    git(repo, "switch", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "--no-edit", "one")
    m1 = git(repo, "rev-parse", "HEAD")
    s2 = commit(repo, {"src/parser.py": FIXED + "# keep\n"})
    return repo, m1, s2


def mr(iid, merged_at, description="Closes #12", **kw):
    return {"iid": iid, "title": f"Change {iid}", "description": description, "author": {"id": 2},
            "merged_at": merged_at, "source_branch": f"b{iid}", **kw}


def run(repo, listing, tmp_path, last=None, extra_routes=None):
    routes = {LIST: (200, listing), "/projects/7/issues/12": (200, ISSUE), **(extra_routes or {})}
    for m in listing:
        routes.setdefault(f"/projects/7/merge_requests/{m['iid']}/closes_issues?per_page=100", (200, []))
    calls = []

    def http(url, headers):
        calls.append(url[len(API):])
        status, body = routes.get(url[len(API):], (404, {"message": "404 Not found"}))
        return status, json.dumps(body).encode()
    out = tmp_path / "scan"
    env = {"CI_API_V4_URL": API, "CI_PROJECT_ID": "7", "CI_PROJECT_PATH": "grp/showcase", "CI_DEFAULT_BRANCH": "main",
           "CI_COMMIT_SHA": git(repo, "rev-parse", "HEAD")}
    code = scan.main(["--repo", str(repo), "--out", str(out)] + (["--last", str(last)] if last else []), env=env, http=http)
    report = json.loads((tmp_path / "scan.json").read_text()) if (tmp_path / "scan.json").exists() else None
    md = (tmp_path / "scan.md").read_text() if (tmp_path / "scan.md").exists() else None
    return code, report, md, calls


def test_scan_reads_each_merge_request_as_it_landed(history, tmp_path):
    repo, m1, s2 = history
    listing = [mr(1, "2026-10-01T10:00:00Z", merge_commit_sha=m1), mr(2, "2026-10-03T10:00:00Z", squash_commit_sha=s2),
               mr(3, "2026-10-02T10:00:00Z", merge_commit_sha="f" * 40), mr(4, "2026-10-04T10:00:00Z"),
               mr(5, "2026-10-05T10:00:00Z", description="No issue here.", squash_commit_sha=s2), {"iid": 6, "merged_at": None}]
    code, report, md, _ = run(repo, listing, tmp_path)
    assert code == 0
    rows = {r["iid"]: r for r in report["merge_requests"]}
    assert [r["iid"] for r in report["merge_requests"]] == [5, 4, 2, 3, 1]
    assert rows[1]["state"] == "extras" and [e["name"] for e in rows[1]["extras"]] == ["Dockerfile"] and rows[1]["issue_iids"] == [12]
    assert rows[2]["state"] == "inside_ask" and rows[2]["extras"] == [] and rows[2]["issues_from"] == "description"
    assert rows[3]["state"] == rows[4]["state"] == "unreadable" and rows[5]["state"] == "no_issue"
    assert "not in this clone" in rows[3]["reason"] and "fast-forward" in rows[4]["reason"]
    assert report["summary"] == {"merge_requests": 5, "unreadable": 2, "no_issue": 1, "with_an_issue": 2, "with_extras": 1,
                                 "extras": 1, "extras_by_kind": {rows[1]["extras"][0]["kind"]: 1}}
    assert "| with at least one extra | 1 |" in md and "| !1 Change 1 | 2026-10-01 | #12 | `Dockerfile` (" in md
    assert "!2 Change 2" not in md and "the last 5 merge requests merged into `main`" in md


def test_scan_takes_the_last_n_and_counts_a_failed_read(history, tmp_path):
    repo, m1, s2 = history
    listing = [mr(1, "2026-10-01T10:00:00Z", merge_commit_sha=m1), mr(2, "2026-10-03T10:00:00Z", squash_commit_sha=s2)]
    code, report, _, _ = run(repo, listing, tmp_path, last=1)
    assert code == 0 and [r["iid"] for r in report["merge_requests"]] == [2]
    code, report, _, _ = run(repo, listing, tmp_path, extra_routes={"/projects/7/issues/12": (403, {})})
    assert code == 0 and {r["state"] for r in report["merge_requests"]} == {"unreadable"}
    assert "HTTP 403" in report["merge_requests"][0]["reason"]


def test_scan_stops_when_the_list_cannot_be_read(history, tmp_path):
    repo, _, _ = history
    code, report, _, calls = run(repo, [], tmp_path, extra_routes={LIST: (403, {})})
    assert code == 2 and report is None and calls[:1] == [LIST]
    assert scan.main([], env={}) == 2


def test_merged_reads_pages_until_a_short_one():
    pages = {1: [{"iid": i, "merged_at": f"2026-10-01T00:00:{i % 60:02d}Z"} for i in range(100)], 2: [{"iid": 500, "merged_at": "2026-10-02T00:00:00Z"}]}
    seen = []

    class Api:
        def get(self, path, missing_ok=False):
            seen.append(path)
            return pages.get(int(path.rsplit("page=", 1)[1]), [])
    got = scan.merged(Api(), "7", "release/1.0", last=3)
    assert len(seen) == 2 and "target_branch=release%2F1.0" in seen[0]
    assert [m["iid"] for m in got] == [500, 59, 58]


def test_a_pipe_in_a_title_or_name_stays_in_its_cell(history, tmp_path):
    repo, m1, _ = history
    code, report, md, _ = run(repo, [mr(1, "2026-10-01T10:00:00Z", merge_commit_sha=m1, title="Fix | drop | rows")], tmp_path)
    line = next(l for l in md.splitlines() if l.startswith("| !1 "))
    assert code == 0 and "Fix \\| drop \\| rows" in line
    assert len([c for c in line.replace("\\|", "").split("|")]) == 6       # four cells, two outer pipes
    assert scan._cell("a|b") == "a\\|b"


def test_last_must_be_at_least_one():
    with pytest.raises(SystemExit) as e:
        scan.main(["--last", "0"], env={"CI_API_V4_URL": API, "CI_PROJECT_ID": "7"})
    assert e.value.code == 2

