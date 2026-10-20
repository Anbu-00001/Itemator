"""The weight study (eval/aidev_weight_rubric.json, registered before it ran): when an AI agent's pull request adds a PyPI or npm
dependency that its task did not name (a new-dependency extra under rules v6), how much does that one line bring along? For a
seeded sample of such lines, one per pull request, the same lookup the CI job makes today (itemator/registry.py, itemator/weight.py):
the deps.dev resolved graph and each package's download size. Read-only; nothing is posted. Runs in the manual CI job
`weight-study` (.gitlab-ci.yml); the Hugging Face Space (hf_runner/server.py, job `weight`) can no longer take new code.

usage: python3 eval/aidev_weight.py --commit-details PARQUET [--lines N]"""
from __future__ import annotations

import argparse, datetime, json, pathlib, random, statistics, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
import aidev_local  # noqa: E402
import aidev_recall as A  # noqa: E402
import aidev_revert as R  # noqa: E402
from itemator import registry as RG, weight as W, extras as X  # noqa: E402

OUT = ROOT / "results" / "aidev_weight_v1.json"
SEED = 20261019
LINES = 300
CHUNK = 500


# ---------------------------------------------------------------- pure parts (tests/test_aidev_weight.py)

def first_line(extras: list, by_path: dict) -> dict | None:
    """The first new-dependency extra, in the rules' order, that names a PyPI or npm package the registry can be asked about."""
    for e in extras:
        if e.kind != "new_dependency":
            continue
        for item in (e,):
            req = RG.request_for(item, by_path)
            if req.get("ecosystem") in W.SYSTEM and "lookup" not in req and RG.valid_name(req["ecosystem"], req["name"]):
                return req
    return None


def pct(values: list, q: float):
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))]


def summarize(rows: list) -> dict:
    """`rows`: one per sampled line, {pr, agent, state, ecosystem, name, version_from, lookup, found, weight}."""
    ok = [r for r in rows if (r.get("weight") or {}).get("weight") == "ok"]
    pk = [r["weight"]["packages"] for r in ok]
    by = [r["weight"]["bytes"] for r in ok]

    def block(rs):
        p = [r["weight"]["packages"] for r in rs]
        b = [r["weight"]["bytes"] for r in rs]
        return {"lines": len(rs), "median_packages": statistics.median(p) if p else None, "p90_packages": pct(p, 0.9),
                "median_bytes": statistics.median(b) if b else None, "p90_bytes": pct(b, 0.9),
                "ten_or_more_packages": sum(1 for x in p if x >= 10), "ten_mb_or_more": sum(1 for x in b if x >= 10_000_000)}
    heaviest = sorted(ok, key=lambda r: -r["weight"]["bytes"])[:3]
    merged = [r for r in ok if r["state"] == "merged"]
    return {"sampled_lines": len(rows), "weighed": len(ok),
            "not_weighed": {k: sum(1 for r in rows if r.get("why_not") == k) for k in sorted({r.get("why_not") for r in rows if r.get("why_not")})},
            "all": block(ok), "by_ecosystem": {e: block([r for r in ok if r["ecosystem"] == e]) for e in sorted({r["ecosystem"] for r in ok})},
            "merged": dict(block(merged), total_bytes=sum(r["weight"]["bytes"] for r in merged)),
            "brings_others": sum(1 for x in pk if x > 1), "total_bytes": sum(by),
            "heaviest": [{"pr": r["pr"], "name": r["name"], "ecosystem": r["ecosystem"], "packages": r["weight"]["packages"],
                          "bytes": r["weight"]["bytes"], "state": r["state"]} for r in heaviest]}


def why_not(rec: dict) -> str | None:
    if rec.get("lookup") != "ok":
        return "lookup_unavailable"
    if not rec.get("found"):
        return "not_on_registry"
    w = rec.get("weight") or {}
    return None if w.get("weight") == "ok" else f"weight_{w.get('reason') or w.get('weight')}"


# ---------------------------------------------------------------- the run

def run(commit_details: str, lines: int = LINES) -> dict:
    prs = {p["id"]: p for p in R.pull_requests()}
    order = sorted(prs)
    random.Random(SEED).shuffle(order)
    rows, scanned, t0 = [], 0, time.time()
    today = datetime.datetime.now(datetime.timezone.utc)
    for start in range(0, len(order), CHUNK):
        group = order[start:start + CHUNK]
        texts = {r["id"]: r for r in A.pq_rows("hao-li/AIDev", "pull_request", "id, html_url, title, body", "id", group)}
        links = {r["pr_id"]: r["issue_id"] for r in A.pq_rows("hao-li/AIDev-7.6M", "related_issue", "pr_id, issue_id", "pr_id", group)}
        issues = {r["id"]: r for r in A.pq_rows("hao-li/AIDev-7.6M", "issue", "id, title, body", "id", sorted(set(links.values())))}
        local = aidev_local.commit_rows(commit_details, group)
        for pid in group:
            scanned += 1
            rs = local.get(pid) or []
            files = A.net_files(rs, rs[-1]["sha"]) if rs else None
            if not files:
                continue
            t = texts.get(pid) or {}
            repo = "/".join((t.get("html_url") or "///").split("/")[3:5])
            task = A.task_text(issues.get(links.get(pid)), t)
            res = X.analyse(task[0], files, repo=repo)
            req = first_line(res.extras, {f["filename"]: f for f in files})
            if not req:
                continue
            out = RG.look_up_one(req, RG.fetch, today)
            rows.append({"pr": t.get("html_url") or pid, "agent": prs[pid]["agent"], "state": prs[pid]["state"],
                         "ecosystem": req["ecosystem"], "name": req["name"], "version_from": "pinned" if req.get("version") else "latest",
                         "lookup": out.get("lookup"), "found": out.get("found"), "weight": out.get("weight"), "why_not": why_not(out)})
            if len(rows) >= lines:
                break
        print(f"scanned {scanned}, lines {len(rows)}, {round(time.time() - t0)} s", flush=True)
        if len(rows) >= lines:
            break
    return {"rubric": "eval/aidev_weight_rubric.json", "rules_version": X.RULES_VERSION, "checked": today.strftime("%Y-%m-%d"),
            "scanned_pull_requests": scanned, "summary": summarize(rows), "rows": rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit-details", required=True)
    ap.add_argument("--lines", type=int, default=LINES)
    a = ap.parse_args(argv)
    out = run(a.commit_details, a.lines)
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["summary"])[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
