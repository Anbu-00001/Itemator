"""Public replay (eval/public_replay_cases.json, written before the run): what Itemator's card would have listed on public
merge requests that GitLab Duo's Developer Flow opened from an issue, and on merged merge requests people wrote.
It calls itemator.ci.facts, the function the CI job runs, with rules v6, no team policy and no registry look-up: no
model, no Duo credits. GET only, through `glab api`; nothing is posted anywhere.

usage (repository root, glab authenticated):
    python3 eval/replay_gitlab.py --frame        # who is in G, F and H: results/public_replay_frame.json
    python3 eval/replay_gitlab.py --score        # the card's extras for each: results/public_replay_raw.json
    python3 eval/replay_gitlab.py --summarize    # counts: results/public_replay.json
Diffs and API answers are cached under eval/cache/gitlab/ (gitignored) and never committed. Field projects are replaced
by a short hash in every committed file; their references go to --private-refs (default under the cache)."""
from __future__ import annotations

import argparse, concurrent.futures, datetime, hashlib, json, math, pathlib, re, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from itemator import ci as CI  # noqa: E402

CASES = ROOT / "eval" / "public_replay_cases.json"
CACHE = ROOT / "eval" / "cache" / "gitlab"
FRAME = ROOT / "results" / "public_replay_frame.json"
RAW = ROOT / "results" / "public_replay_raw.json"
OUT = ROOT / "results" / "public_replay.json"
GITLAB = 278964
FIELD_GROUP = 142538134
OURS = {87291130, 87623122}
WINDOW = ("2026-09-01T00:00:00Z", "2026-10-01T00:00:00Z")
FIELD_BEFORE = "2026-10-16T00:00:00Z"
FLOW = {"G": "duo-developer-gitlab-org", "F": "duo-developer-gitlab-ai-hackathon"}
MAX_FILES = 300
AMENDMENT = 0          # 1: --amendment 1 (eval/public_replay_cases.json, "amendment_1"); its own result files
NOW = datetime.datetime(2026, 10, 16, tzinfo=datetime.timezone.utc)
_BRANCH_ISSUE = re.compile(r"^duo/[^/]+/(\d+)-")
_MENTIONED = re.compile(r"^mentioned in issue #(\d+)\s*$")


# ------------------------------------------------------------------ pure parts (tests/test_replay_gitlab.py)

def to_files(diffs: list) -> list[dict]:
    """GitLab's diff entries as the file list the rules take (the CI job's field names)."""
    out = []
    for d in diffs or []:
        withheld = bool(d.get("too_large") or d.get("collapsed"))
        patch = d.get("diff") or None
        if withheld:
            patch = None
        status = ("added" if d.get("new_file") else "removed" if d.get("deleted_file")
                  else "renamed" if d.get("renamed_file") else "modified")
        lines = (patch or "").splitlines()
        f = {"filename": d.get("new_path") or d.get("old_path"), "status": status, "patch": patch if patch is None or patch.endswith("\n") else patch + "\n",
             "additions": sum(1 for x in lines if x.startswith("+") and not x.startswith("+++")),
             "deletions": sum(1 for x in lines if x.startswith("-") and not x.startswith("---"))}
        if status == "renamed":
            f["previous_filename"] = d.get("old_path")
        if withheld:
            f["withheld"] = True
        out.append(f)
    return out


def flow_made(notes: list, account: str) -> bool:
    return any(n.get("system") and (n.get("author") or {}).get("username") == account for n in notes or [])


def any_duo_account(notes: list) -> bool:
    return any(n.get("system") and (n.get("author") or {}).get("username", "").startswith("duo-") for n in notes or [])


def is_bot(username: str) -> bool:
    u = (username or "").lower()
    return "bot" in u or u.startswith(("project_", "group_"))


def agent_commit(c: dict) -> bool:
    return c.get("author_name") == "Duo Developer" or "service_account" in (c.get("author_email") or "")


def agent_version(versions: list):
    """`versions`: diff versions oldest first, each {"commits": [...], "diffs": [...]}. The newest one whose commits are
    all the flow's and that changes at least one file; None when there is none. A version with a person's commit ends it."""
    best = None
    for v in versions:
        commits = v.get("commits") or []
        if not commits or not all(agent_commit(c) for c in commits):
            break
        if v.get("diffs"):
            best = v
    return best


def flow_issue(notes: list, account: str, branch: str):
    """The issue the flow was started from: its own note 'mentioned in issue #N', else N in duo/<kind>/<N>-..."""
    for n in notes or []:
        if n.get("system") and (n.get("author") or {}).get("username") == account:
            m = _MENTIONED.match((n.get("body") or "").strip())
            if m:
                return int(m.group(1))
    m = _BRANCH_ISSUE.match(branch or "")
    return int(m.group(1)) if m else None


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def anon(project_id) -> str:
    return hashlib.sha256(f"itemator-field-{project_id}".encode()).hexdigest()[:8]


def capped(rows: list, cap: int) -> list:
    """Each project's first `cap` rows by created_at (the field's per-project cap)."""
    seen, out = {}, []
    for r in sorted(rows, key=lambda r: (r["project"], r["created_at"])):
        seen[r["project"]] = seen.get(r["project"], 0) + 1
        if seen[r["project"]] <= cap:
            out.append(r)
    return out


# ------------------------------------------------------------------ GitLab (GET only, cached)

def get(path: str):
    key = CACHE / (hashlib.sha1(path.encode()).hexdigest() + ".json")
    if key.exists():
        return json.loads(key.read_text())
    err = ""
    for attempt in range(6):
        r = subprocess.run(["glab", "api", path], capture_output=True, text=True)
        if r.returncode == 0:
            data = json.loads(r.stdout or "null")
            break
        err = (r.stderr + r.stdout)[:300]
        if re.search(r"\b(401|403|404)\b", err):
            data = None
            break
        time.sleep(5 * (attempt + 1))
    else:
        raise RuntimeError(f"GET {path}: {err}")
    CACHE.mkdir(parents=True, exist_ok=True)
    key.write_text(json.dumps(data))
    return data


def pages(path: str, limit: int = 60) -> list:
    out = []
    for page in range(1, limit + 1):
        b = get(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        if not b:
            break
        out += b
        if len(b) < 100:
            break
    return out


def notes_of(pid, iid):
    return pages(f"projects/{pid}/merge_requests/{iid}/notes?sort=asc&order_by=created_at", limit=10)


_CLOSING_URL = re.compile(r"(?i)\b(?:clos(?:e|es|ed|ing)|fix(?:es|ed|ing)?|resolv(?:e|es|ed|ing)|implement(?:s|ed|ing)?)\b[:\s]+"
                          r"https://gitlab\.com/gitlab-org/gitlab/-/(?:issues|work_items)/(\d+)")


def closing_links(description) -> list[int]:
    """Amendment 2: same-project issues after a closing word, written as #N (itemator.ci.closing_refs) or as the issue's URL."""
    out = list(CI.closing_refs(description))
    for m in _CLOSING_URL.finditer(description or ""):
        if int(m.group(1)) not in out:
            out.append(int(m.group(1)))
    return out


def frame_c(sept: list) -> list[dict]:
    """Amendment 2, population C: merged in the September window, labelled 'Community contribution', not on a duo/
    branch, not a bot, no system note by a duo- account, and a closing link (closing_links) to an issue whose closed_by
    lists this merge request; the first such issue is the one the card reads."""
    rows = []
    for m in sept:
        if "Community contribution" not in (m.get("labels") or []) or m["source_branch"].startswith("duo/") or is_bot(m["author"]["username"]):
            continue
        confirmed = [n for n in closing_links(m.get("description"))
                     if any(x.get("iid") == m["iid"] for x in (get(f"projects/{GITLAB}/issues/{n}/closed_by") or []))]
        if not confirmed or any_duo_account(notes_of(GITLAB, m["iid"])):
            continue
        rows.append({"project": GITLAB, "iid": m["iid"], "created_at": m["created_at"], "issue_iid": confirmed[0]})
    return rows


# ------------------------------------------------------------------ frame

def frame() -> dict:
    sept = pages(f"projects/{GITLAB}/merge_requests?state=merged&merged_after={WINDOW[0]}&merged_before={WINDOW[1]}"
                 "&order_by=merged_at&sort=asc", limit=80)
    rows = {"G": [], "F": [], "H": []}
    counts = {"september_merged": len(sept)}
    duo = [m for m in sept if m["source_branch"].startswith("duo/")]
    counts["G_duo_branch"] = len(duo)
    for m in duo:
        if flow_made(notes_of(GITLAB, m["iid"]), FLOW["G"]):
            rows["G"].append({"project": GITLAB, "iid": m["iid"], "created_at": m["created_at"]})
    people = [m for m in sept if not m["source_branch"].startswith("duo/") and not is_bot(m["author"]["username"])]
    for m in people:
        refs = CI.closing_refs(m.get("description"))
        if not refs:
            continue
        if not any(any(x.get("iid") == m["iid"] for x in (get(f"projects/{GITLAB}/issues/{n}/closed_by") or [])) for n in refs):
            continue
        if any_duo_account(notes_of(GITLAB, m["iid"])):
            continue
        rows["H"].append({"project": GITLAB, "iid": m["iid"], "created_at": m["created_at"]})
    field = pages(f"groups/{FIELD_GROUP}/merge_requests?state=all&scope=all&created_before={FIELD_BEFORE}", limit=80)
    counts["field_mrs"] = len(field)
    fduo = [m for m in field if m["project_id"] not in OURS and m["source_branch"].startswith("duo/")]
    counts["F_duo_branch"] = len(fduo)
    for m in fduo:
        if flow_made(notes_of(m["project_id"], m["iid"]), FLOW["F"]):
            rows["F"].append({"project": m["project_id"], "iid": m["iid"], "created_at": m["created_at"]})
    counts.update({f"{k}_selected": len(v) for k, v in rows.items()})
    return {"counts": counts, "rows": rows}


# ------------------------------------------------------------------ score

def linked(pop: str, pid, mr: dict, notes: list, issue_iid=None):
    if issue_iid is not None:                    # amendment 2 (C): the closing link the frame confirmed with closed_by
        raw = get(f"projects/{pid}/issues/{issue_iid}")
        return ([CI._issue(raw, pid)], "closing_link_confirmed") if raw else ([], "none")
    closes = get(f"projects/{pid}/merge_requests/{mr['iid']}/closes_issues") or []
    if closes:
        return [CI._issue(i, pid) for i in closes], "closes_issues"
    issues = [CI._issue(raw, pid) for raw in (get(f"projects/{pid}/issues/{n}") for n in CI.closing_refs(mr.get("description"))) if raw]
    if issues:
        return issues, "description"
    if pop in FLOW:
        n = flow_issue(notes, FLOW[pop], mr["source_branch"])
        raw = get(f"projects/{pid}/issues/{n}") if n else None
        if raw:
            return [CI._issue(raw, pid)], "flow_issue"
    return [], "none"


def rebuilt(pid, d: dict) -> dict:
    """Amendment 1: GitLab no longer serves the diff of a superseded version, so it is rebuilt from the repository
    (compare from the version's base commit to its head commit); a version GitLab still serves is left as it is."""
    if d.get("diffs") or not (d.get("base_commit_sha") and d.get("head_commit_sha")):
        return d
    c = get(f"projects/{pid}/repository/compare?from={d['base_commit_sha']}&to={d['head_commit_sha']}&straight=true") or {}
    return dict(d, diffs=c.get("diffs") or [], diffs_from="compare")


def versions_oldest_first(pid, iid) -> list:
    out = []
    for v in reversed(get(f"projects/{pid}/merge_requests/{iid}/versions") or []):
        d = get(f"projects/{pid}/merge_requests/{iid}/versions/{v['id']}") or {}
        if AMENDMENT >= 1:
            d = rebuilt(pid, d)
        out.append(d)
        commits = d.get("commits") or []
        if commits and not all(agent_commit(c) for c in commits):
            break
    return out


def card(pid, path, mr, issues, src, files, base, head) -> dict:
    rep = CI.facts(mr_iid=mr["iid"], mr_title=mr.get("title") or "", mr_description=mr.get("description") or "",
                   mr_author_id=(mr.get("author") or {}).get("id"), issues=issues, issues_from=src, files=files, repo=path,
                   base_sha=base or "", head_sha=head or "", warnings=[], now=NOW)
    return {"state": rep["state"], "extras": [{"name": e["name"], "kind": e["kind"], "path": e["path"]} for e in rep["extras"]],
            "unplaced": len(rep["unplaced"])}


def score_one(pop: str, row: dict) -> list[dict]:
    pid, iid = row["project"], row["iid"]
    mr = get(f"projects/{pid}/merge_requests/{iid}")
    if not mr:
        return [{"pop": pop, "ref": f"{'gitlab-org/gitlab' if pid == GITLAB else anon(pid)}!{iid}", "project": pid if pid == GITLAB else anon(pid),
                 "created_at": row["created_at"], "issues_from": "none", "version": "any", "excluded": "merge request not readable"}]
    proj = get(f"projects/{pid}?simple=true") or {}
    path = proj.get("path_with_namespace")
    notes = notes_of(pid, iid)
    issues, src = linked(pop, pid, mr, notes, row.get("issue_iid"))
    ref = f"{'gitlab-org/gitlab' if pid == GITLAB else anon(pid)}!{iid}"
    base = {"pop": pop, "ref": ref, "project": pid if pid == GITLAB else anon(pid), "created_at": row["created_at"],
            "state_mr": mr.get("state"), "issues_from": src, "issue_refs": [i["ref"] for i in issues]}
    if not issues:
        return [dict(base, version="any", excluded="no readable issue")]
    out = []
    wanted = json.loads(CASES.read_text())["populations"][pop]["versions"]
    if "agent" in wanted:
        v = agent_version(versions_oldest_first(pid, iid))
        if v is None:
            out.append(dict(base, version="agent", excluded="no version with only the flow's commits"))
        else:
            files = to_files(v["diffs"])
            out.append(dict(base, version="agent", files=len(files), withheld=sum(1 for f in files if f.get("withheld")), diffs_from=v.get("diffs_from", "version"),
                            **({"excluded": f"over {MAX_FILES} files"} if len(files) > MAX_FILES else
                               card(pid, path, mr, issues, src, files, v.get("base_commit_sha"), v.get("head_commit_sha")))))
    if {"merged", "merged_or_latest"} & set(wanted):
        files = to_files(pages(f"projects/{pid}/merge_requests/{iid}/diffs", limit=5))
        refs = mr.get("diff_refs") or {}
        out.append(dict(base, version="merged" if mr.get("state") == "merged" else "latest", files=len(files),
                        withheld=sum(1 for f in files if f.get("withheld")),
                        **({"excluded": f"over {MAX_FILES} files"} if len(files) > MAX_FILES else
                           card(pid, path, mr, issues, src, files, refs.get("base_sha"), refs.get("head_sha")))))
    return out


def score(fr: dict, workers: int = 4) -> list[dict]:
    jobs = [(pop, r) for pop in ("G", "F", "H", "C") for r in fr["rows"].get(pop, [])
            if AMENDMENT != 2 or pop == "C"]                # amendment 2 scores only C; G, F and H are unchanged
    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        return [x for got in ex.map(lambda j: score_one(*j), jobs) for x in got]


# ------------------------------------------------------------------ summary

def share(rows: list) -> dict:
    n = len(rows)
    k = sum(1 for r in rows if r.get("extras"))
    kinds = {}
    for r in rows:
        for e in r.get("extras") or []:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    by_job = [r for r in rows if r["issues_from"] in ("closes_issues", "description")]
    return {"scored": n, "flagged": k, "share": round(k / n, 3) if n else None, "wilson95": wilson(k, n),
            "extras": sum(len(r.get("extras") or []) for r in rows), "extras_by_kind": dict(sorted(kinds.items())),
            "linked_by_the_ci_job_itself": len(by_job), "flagged_among_those": sum(1 for r in by_job if r.get("extras"))}


def summarize(raw: list, cap: int) -> dict:
    out = {"what": json.loads(CASES.read_text())["what"], "limits": json.loads(CASES.read_text())["limits"], "rules_version": CI.X.RULES_VERSION}
    for pop in [p for p in ("G", "F", "H", "C") if any(r["pop"] == p for r in raw)]:
        rows = [r for r in raw if r["pop"] == pop]
        out[pop] = {"merge_requests": len({r["ref"] for r in rows}),
                    "excluded": {why: len({r["ref"] for r in rows if r.get("excluded") == why}) for why in sorted({r["excluded"] for r in rows if r.get("excluded")})}}
        for version in sorted({r["version"] for r in rows if not r.get("excluded")}):
            scored = [r for r in rows if r["version"] == version and not r.get("excluded")]
            out[pop][version] = share(scored)
            if pop == "F":
                out[pop][version + "_capped"] = share(capped(scored, cap))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", action="store_true"); ap.add_argument("--score", action="store_true"); ap.add_argument("--summarize", action="store_true")
    ap.add_argument("--private-refs", default=str(CACHE / "field_refs.json"))
    ap.add_argument("--amendment", type=int, default=0); ap.add_argument("--frame-c", action="store_true")
    a = ap.parse_args(argv)
    global AMENDMENT, RAW, OUT
    if a.amendment:
        AMENDMENT = a.amendment
        RAW, OUT = RAW.with_name(f"public_replay_a{a.amendment}_raw.json"), OUT.with_name(f"public_replay_a{a.amendment}.json")
    if a.frame:
        fr = frame()
        pathlib.Path(a.private_refs).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(a.private_refs).write_text(json.dumps(fr["rows"]["F"], indent=1) + "\n")
        public = {"counts": fr["counts"], "rows": {p: [dict(r, project=r["project"] if r["project"] == GITLAB else anon(r["project"])) for r in fr["rows"][p]] for p in fr["rows"]}}
        FRAME.write_text(json.dumps(public, indent=1) + "\n")
        (CACHE / "frame_private.json").write_text(json.dumps(fr, indent=1) + "\n")
        print(json.dumps(fr["counts"]))
    if a.frame_c:
        priv = json.loads((CACHE / "frame_private.json").read_text())
        sept = pages(f"projects/{GITLAB}/merge_requests?state=merged&merged_after={WINDOW[0]}&merged_before={WINDOW[1]}"
                     "&order_by=merged_at&sort=asc", limit=80)
        priv["rows"]["C"] = frame_c(sept)
        priv["counts"]["C_community_label"] = sum(1 for m in sept if "Community contribution" in (m.get("labels") or []))
        priv["counts"]["C_selected"] = len(priv["rows"]["C"])
        (CACHE / "frame_private.json").write_text(json.dumps(priv, indent=1) + "\n")
        FRAME.with_name("public_replay_frame_c.json").write_text(json.dumps({"counts": {k: v for k, v in priv["counts"].items() if k.startswith("C_")},
                                                                            "rows": priv["rows"]["C"]}, indent=1) + "\n")
        print({k: v for k, v in priv["counts"].items() if k.startswith("C_")})
    if a.score:
        if RAW.exists():
            print(f"{RAW.name} exists: the replay runs once"); return 1
        fr = json.loads((CACHE / "frame_private.json").read_text())
        RAW.write_text(json.dumps(score(fr), indent=1) + "\n")
        print("wrote", RAW.name)
    if a.summarize:
        cap = json.loads(CASES.read_text())["populations"]["F"]["per_project_cap"]
        OUT.write_text(json.dumps(summarize(json.loads(RAW.read_text()), cap), indent=1) + "\n")
        print("wrote", OUT.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
