"""Leg 2 of the "does Itemator catch real problems" work (eval/aidev_revert_rubric.json, registered before any revert was
looked for): in the public AIDev dataset, is an agent pull request one of whose commits a different pull request later
reverted more likely to carry an extra the rules (v6, frozen) list than a pull request of the same agent that was not
reverted? Read-only; nothing is posted. Patches and task text stay in eval/cache/ (gitignored); results hold ids,
counts and yes/no only.

usage (repository root):
    python3 eval/aidev_revert.py --frame    # which PRs are reverted, undone inside themselves, controls: results/aidev_revert_frame.json
    python3 eval/aidev_revert.py --score    # the rules on each: results/aidev_revert_v6.json (network-bound, resumable)
    python3 eval/aidev_revert.py --score --commit-details pr_commit_details.parquet   # file rows from the parquet, not the API"""
from __future__ import annotations

import argparse, collections, concurrent.futures, json, math, pathlib, random, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
from itemator import extras as X  # noqa: E402
import aidev_recall as A  # noqa: E402

FRAME = ROOT / "results" / "aidev_revert_frame.json"
OUT = ROOT / "results" / "aidev_revert_v6.json"
SEED = 20261019
CONTROLS_PER = 3
_REVERTS = re.compile(r"This reverts commit ([0-9a-fA-F]{12,40})")


# ---------------------------------------------------------------- pure parts (tests/test_aidev_revert.py)

def reverted_shas(message: str) -> list[str]:
    """The commit ids a message says it reverts (git revert writes `This reverts commit <sha>`), lower-cased."""
    return [m.lower() for m in _REVERTS.findall(message or "")]


def find_reverts(commits: list[dict]) -> dict:
    """`commits`: {sha, pr_id, message} rows. A reverted sha is one that belongs to exactly one pull request: given in
    full, or as a prefix of at least 12 digits that matches exactly one sha. Returns {"cross": {A: [B, ...]},
    "inside": [A, ...]}: A reverted by a different pull request B, and A reverted by one of its own commits."""
    owner = collections.defaultdict(set)
    for c in commits:
        owner[c["sha"].lower()].add(int(c["pr_id"]))
    shas = sorted(owner)
    cross, inside = collections.defaultdict(set), set()
    for c in commits:
        for ref in reverted_shas(c["message"]):
            hits = [ref] if ref in owner else [s for s in shas if s.startswith(ref)]      # the pattern already needs 12 digits
            if len(hits) != 1 or len(owner[hits[0]]) != 1:
                continue
            a, b = next(iter(owner[hits[0]])), int(c["pr_id"])
            (inside.add(a) if a == b else cross[a].add(b))
    return {"cross": {a: sorted(bs) for a, bs in sorted(cross.items())}, "inside": sorted(inside - set(cross))}


def draw_controls(members: list[dict], pool: list[dict], exclude: set, seed: int = SEED, per: int = CONTROLS_PER) -> dict:
    """For each member (sorted by id), up to `per` pull requests of the same agent and state, not excluded and not
    already used as a control; drawn with random.Random(seed). Returns {member id: [control ids]}."""
    rng = random.Random(seed)
    by = collections.defaultdict(list)
    for p in sorted(pool, key=lambda p: p["id"]):
        if p["id"] not in exclude:
            by[(p["agent"], p["state"])].append(p["id"])
    used, out = set(), {}
    for m in sorted(members, key=lambda m: m["id"]):
        free = [i for i in by[(m["agent"], m["state"])] if i not in used]
        pick = rng.sample(free, min(per, len(free)))
        used.update(pick)
        out[m["id"]] = sorted(pick)
    return out


def newcombe(k1: int, n1: int, k2: int, n2: int, z: float = 1.96) -> dict:
    """The difference of two shares (first minus second) with Newcombe's hybrid-score 95% interval."""
    if not n1 or not n2:
        return {"difference": None, "interval": None}
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = A.G.wilson(k1, n1, z)
    l2, u2 = A.G.wilson(k2, n2, z)
    d = p1 - p2
    return {"difference": round(d, 4), "interval": [round(d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), 4),
                                                    round(d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2), 4)]}


def share(rows: list) -> dict:
    n = len(rows)
    k = sum(1 for r in rows if r["extra"])
    return {"pull_requests": n, "with_an_extra": k, "share": round(k / n, 4) if n else None, "wilson95": A.G.wilson(k, n) if n else None}


def compare(members: list, controls: list) -> dict:
    m, c = share(members), share(controls)
    return {"members": m, "controls": c, **newcombe(m["with_an_extra"], m["pull_requests"], c["with_an_extra"], c["pull_requests"])}


def kind_of(extra) -> str:
    k = getattr(extra, "kind", "") or ""
    return {"new_dependency": "dependency", "ci_or_config": "ci_or_config", "tests_removed": "tests_removed",
            "agent_instructions": "agent_instructions"}.get(k, "other")


def score_pr(pr: dict, rows: list, task: tuple, repo: str, version: int = X.RULES_VERSION) -> dict:
    """One pull request: the rules on its files at the last commit. `rows`: its commit-file rows in commit order."""
    base = {"id": pr["id"], "agent": pr["agent"], "state": pr["state"], "task_from": task[1]}
    if not rows:
        return dict(base, readable=False)
    files = A.net_files(rows, rows[-1]["sha"])
    if not files:
        return dict(base, readable=False)
    res = X.analyse(task[0], files, repo=repo, version=version)
    return dict(base, readable=True, extra=bool(res.extras), kinds=sorted({kind_of(e) for e in res.extras}),
                n=len(res.extras), kinds_all=[kind_of(e) for e in res.extras])


def score_or_error(pr: dict, get_rows, task: tuple, repo: str) -> dict:
    """score_pr, but a pull request whose file rows the API will not give (an error after every retry) is counted as unreadable
    with `api_error` set, so the run finishes and the cases are listed apart (rubric amendment_2)."""
    try:
        rows = get_rows()
    except RuntimeError:
        return {"id": pr["id"], "agent": pr["agent"], "state": pr["state"], "task_from": task[1], "readable": False, "api_error": True}
    return score_pr(pr, rows, task, repo)


def summarize(groups: dict) -> dict:
    out = {}
    for name, (members, controls) in groups.items():
        m = [r for r in members if r["readable"]]
        c = [r for r in controls if r["readable"]]
        out[name] = dict(compare(m, c), unreadable={"members": len(members) - len(m), "controls": len(controls) - len(c)},
                         api_errors={"members": sum(1 for r in members if r.get("api_error")), "controls": sum(1 for r in controls if r.get("api_error"))},
                         by_agent={a: compare([r for r in m if r["agent"] == a], [r for r in c if r["agent"] == a])
                                   for a in sorted({r["agent"] for r in m})},
                         by_task={t: compare([r for r in m if r["task_from"] == t], [r for r in c if r["task_from"] == t])
                                  for t in sorted({r["task_from"] for r in m + c})},
                         kinds={g: dict(collections.Counter(k for r in rs for k in r["kinds"])) for g, rs in (("members", m), ("controls", c))})
    return out


# ---------------------------------------------------------------- reading the dataset (network; cached)

def pull_requests() -> list[dict]:
    import duckdb
    f = A.parquet("hao-li/AIDev", "pull_request")
    cur = duckdb.connect().execute("SELECT id, agent, state, CAST(merged_at AS VARCHAR) AS merged_at FROM read_parquet(?)", [str(f)])
    return [{"id": int(i), "agent": a, "state": "merged" if m else s} for i, a, s, m in cur.fetchall()]


def commits() -> list[dict]:
    import duckdb
    f = A.parquet("hao-li/AIDev", "pr_commits")
    cur = duckdb.connect().execute("SELECT sha, CAST(pr_id AS BIGINT), message FROM read_parquet(?)", [str(f)])
    return [{"sha": s, "pr_id": p, "message": m} for s, p, m in cur.fetchall()]


def build_frame() -> dict:
    prs, cms = pull_requests(), commits()
    rv = find_reverts(cms)
    by_id = {p["id"]: p for p in prs}
    cross = {a: bs for a, bs in rv["cross"].items() if a in by_id}
    inside = [a for a in rv["inside"] if a in by_id]
    reverting = {b for bs in cross.values() for b in bs}
    exclude = set(cross) | set(inside) | reverting
    primary = [by_id[a] for a in cross]
    selfs = [by_id[a] for a in inside]
    c1 = draw_controls(primary, prs, exclude)
    c2 = draw_controls(selfs, prs, exclude | {i for v in c1.values() for i in v})
    return {"pull_requests_in_dataset": len(prs), "commits_in_dataset": len(cms), "reverted_by_a_different_pr": len(cross),
            "undone_inside_itself": len(inside), "by_agent": dict(collections.Counter(by_id[a]["agent"] for a in cross)),
            "primary": [{"id": a, "reverted_by": bs} for a, bs in cross.items()], "inside": inside,
            "controls_primary": {str(k): v for k, v in c1.items()}, "controls_inside": {str(k): v for k, v in c2.items()}}


def one_pr(pid: int) -> dict:
    """Its commit-file rows from the dataset API (one pr_id per query, cached page by page) and the task text."""
    rows = A.rows_where("hao-li/AIDev", "pr_commit_details", f'"pr_id"={int(pid)}')
    return {"rows": [{k: r.get(k) for k in ("sha", "filename", "status", "patch")} for r in rows]}


def score(workers: int = 4, commit_details: str | None = None) -> dict:
    """`commit_details`: path of the dataset's pr_commit_details parquet; when given, the file rows come from it (one scan,
    amendment 3) instead of the API."""
    fr = json.loads(FRAME.read_text())
    prs = {p["id"]: p for p in pull_requests()}
    ids = sorted({r["id"] for r in fr["primary"]} | set(fr["inside"]) | {i for v in fr["controls_primary"].values() for i in v}
                 | {i for v in fr["controls_inside"].values() for i in v})
    texts = {r["id"]: r for r in A.pq_rows("hao-li/AIDev", "pull_request", "id, html_url, title, body", "id", ids)}
    links = {r["pr_id"]: r["issue_id"] for r in A.pq_rows("hao-li/AIDev-7.6M", "related_issue", "pr_id, issue_id", "pr_id", ids)}
    issues = {r["id"]: r for r in A.pq_rows("hao-li/AIDev-7.6M", "issue", "id, title, body", "id", sorted(set(links.values())))}

    local = None
    if commit_details:
        import aidev_local
        local = aidev_local.commit_rows(commit_details, ids)

    def run(pid):
        t = texts.get(pid) or {}
        repo = "/".join((t.get("html_url") or "///").split("/")[3:5])
        task = A.task_text(issues.get(links.get(pid)), t)
        get_rows = (lambda: local.get(pid, [])) if local is not None else (lambda: one_pr(pid)["rows"])
        return score_or_error(prs[pid], get_rows, task, repo)

    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        scored = dict(zip(ids, ex.map(run, ids)))
    pick = lambda xs: [scored[i] for i in xs]
    ctl = lambda d: [scored[i] for v in d.values() for i in v]
    groups = {"reverted_by_a_different_pr": (pick([r["id"] for r in fr["primary"]]), ctl(fr["controls_primary"])),
              "undone_inside_itself": (pick(fr["inside"]), ctl(fr["controls_inside"]))}
    return {"rubric": "eval/aidev_revert_rubric.json", "rules_version": X.RULES_VERSION, "frame": {k: v for k, v in fr.items() if not isinstance(v, (list, dict)) or k == "by_agent"},
            "summary": summarize(groups)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--commit-details", help="path of the dataset's pr_commit_details parquet (amendment 3): read file rows from it, not the API")
    a = ap.parse_args(argv)
    if a.frame:
        fr = build_frame()
        FRAME.write_text(json.dumps(fr, indent=1) + "\n")
        print(json.dumps({k: v for k, v in fr.items() if not isinstance(v, (list, dict)) or k == "by_agent"}))
    if a.score:
        out = score(commit_details=a.commit_details)
        OUT.write_text(json.dumps(out, indent=1) + "\n")
        print(json.dumps({k: {x: y for x, y in v.items() if x in ("members", "controls", "difference", "interval", "unreadable")}
                          for k, v in out["summary"].items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
