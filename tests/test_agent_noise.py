"""The agent-commit noise run (eval/agent_noise.py): grouping, counting and the rule, on small made-up rows."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import agent_noise as AN  # noqa: E402

DOCKER = "@@ -1,1 +1,2 @@\n FROM python:3.12\n+FROM node:latest\n"
PLAIN = "@@ -1,1 +1,2 @@\n x = 1\n+y = 2\n"


def row(sha, name, patch, author="bot-a", pr=1):
    return {"sha": sha, "pr_id": pr, "author": author, "filename": name, "status": "modified", "patch": patch}


def test_rows_are_grouped_by_commit():
    g = AN.commits([row("a", "Dockerfile", DOCKER), row("a", "x.py", PLAIN), row("b", "y.py", PLAIN, author="bot-b", pr=2)])
    assert sorted(g) == ["a", "b"] and len(g["a"]["files"]) == 2 and g["b"]["author"] == "bot-b" and g["b"]["pr"] == 2


def test_a_commit_counts_once_however_many_files_fire():
    m = AN.measure(AN.commits([row("a", "Dockerfile", DOCKER), row("a", "sub/Dockerfile", DOCKER), row("b", "y.py", PLAIN)]))
    mv = m["checks"]["moving"]
    assert (mv["read"], mv["spoke"], mv["readable"], mv["readable_spoke"]) == (2, 1, 1, 1)
    assert mv["examples"][0]["commit"] == "a" and mv["by_agent"]["bot-a"] == {"read": 2, "spoke": 1}


def test_commits_without_a_patch_are_counted_and_left_out():
    m = AN.measure(AN.commits([row("a", "img.png", ""), row("b", "y.py", PLAIN)]))
    assert m["commits_without_patch"] == 1 and m["checks"]["moving"]["read"] == 1


def test_the_rule_needs_both_the_share_and_the_interval():
    rows = [row(f"c{i}", "y.py", PLAIN) for i in range(200)] + [row(f"d{i}", "Dockerfile", DOCKER) for i in range(2)]
    ok = AN.measure(AN.commits(rows))["checks"]["moving"]
    assert ok["spoke"] == 2 and ok["rule"] == "met"
    bad = AN.measure(AN.commits([row(f"c{i}", "y.py", PLAIN) for i in range(20)] + [row("d", "Dockerfile", DOCKER)]))["checks"]["moving"]
    assert bad["share"] > 0.03 and bad["rule"] == "not met"


def test_the_run_writes_the_file(tmp_path):
    data = tmp_path / "d.json"
    data.write_text(json.dumps([row("a", "Dockerfile", DOCKER)]))
    out = tmp_path / "o.json"
    assert AN.main(["--data", str(data), "--out", str(out)]) == 0
    got = json.loads(out.read_text())
    assert got["file_rows"] == 1 and got["checks"]["moving"]["spoke"] == 1
