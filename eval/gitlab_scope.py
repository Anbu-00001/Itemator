"""The GitLab-native scope-comment study (eval/gitlab_scope_rubric.json, registered before any note was fetched):
on merge requests GitLab Duo's Developer Flow opened in gitlab-org/gitlab, the notes people other than the author wrote,
read blind by two labellers, then the rules run on the files those notes point at. GET only, through `glab api`.

usage (repository root, glab authenticated):
    python3 eval/gitlab_scope.py --frame             # the duo/ merge requests: results/gitlab_scope_frame.json
    python3 eval/gitlab_scope.py --notes DIR         # people's notes, numbered, in shard files under DIR (not committed)
API answers are cached under eval/cache/gitlab/ (gitignored)."""
from __future__ import annotations

import argparse, concurrent.futures, json, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import replay_gitlab as G  # noqa: E402

PROJECT, PATH = 278964, "gitlab-org/gitlab"
WINDOW = ("2026-06-01T00:00:00Z", "2026-10-18T00:00:00Z")
FRAME = ROOT / "results" / "gitlab_scope_frame.json"
SHARD = 60                    # notes per shard file
NOTE_MAX = 1500               # characters of a note a labeller sees
KEYWORDS = ("unrelated", "out of scope", "separate pr", "separate mr", "not needed", "unnecessary")
_PAGE = """{ project(fullPath: "%s") { mergeRequests(state: %s, createdAfter: "%s", createdBefore: "%s", first: 100%s) {
  count pageInfo { endCursor hasNextPage } nodes { iid state sourceBranch createdAt } } } }"""


def graphql(query: str) -> dict:
    r = None
    for _ in range(5):
        r = subprocess.run(["glab", "api", "graphql", "-f", f"query={query}"], capture_output=True, text=True)
        if r.returncode == 0:
            d = json.loads(r.stdout)
            if "errors" not in d:
                return d["data"]
    raise RuntimeError(f"GraphQL failed: {(r.stderr + r.stdout)[:300] if r else ''}")


def listing(state: str) -> tuple[int, list]:
    rows, after, count = [], "", None
    while True:
        m = graphql(_PAGE % (PATH, state, *WINDOW, after))["project"]["mergeRequests"]
        count = m["count"] if count is None else count
        rows += m["nodes"]
        if not m["pageInfo"]["hasNextPage"]:
            return count, rows
        after = f', after: "{m["pageInfo"]["endCursor"]}"'


def frame() -> dict:
    out = {"project": PATH, "window": WINDOW, "counts": {}, "rows": []}
    for state in ("merged", "closed", "opened"):
        count, rows = listing(state) if state != "opened" else (None, [])
        if state == "opened":
            count = graphql((_PAGE % (PATH, state, *WINDOW, "")).replace("first: 100", "first: 1"))["project"]["mergeRequests"]["count"]
        else:
            assert len(rows) == count, (state, len(rows), count)        # never a silently cut list
        duo = [r for r in rows if r["sourceBranch"].startswith("duo/")]
        out["counts"][state] = {"all": count, "duo": len(duo) if state != "opened" else None}
        out["rows"] += [{"iid": int(r["iid"]), "state": r["state"], "branch": r["sourceBranch"], "created_at": r["createdAt"]} for r in duo]
    return out


def is_flow_account(username: str) -> bool:
    return (username or "").startswith("duo-")


def human_notes(mr: dict, notes: list) -> list:
    author = (mr.get("author") or {}).get("username")
    keep = []
    for n in notes or []:
        who = (n.get("author") or {}).get("username")
        if n.get("system") or who == author or G.is_bot(who) or is_flow_account(who):
            continue
        pos = n.get("position") or {}
        keep.append({"note_id": n["id"], "author": who, "created_at": n["created_at"], "type": n.get("type"),
                     "file": pos.get("new_path") or pos.get("old_path"), "body": n.get("body") or ""})
    return keep


def changed_paths(iid: int) -> list:
    rows = G.pages(f"projects/{PROJECT}/merge_requests/{iid}/diffs", limit=30)
    return sorted({r.get("new_path") or r.get("old_path") for r in rows if isinstance(r, dict)})


def tie(note: dict, paths: list):
    """A diff note's own file; a general note's file only when it names exactly one changed path."""
    if note["file"]:
        return note["file"]
    named = [p for p in paths if p in note["body"]]
    return named[0] if len(named) == 1 else None


def keyword(body: str) -> bool:
    b = body.lower()
    return any(k in b for k in KEYWORDS)


def prefetch(rows: list, workers: int = 4) -> None:
    """Fill the cache in parallel (GET only); notes() then reads from it in order."""
    def one(iid):
        mr = G.get(f"projects/{PROJECT}/merge_requests/{iid}")
        if mr and human_notes(mr, G.notes_of(PROJECT, iid)):
            changed_paths(iid)
    with concurrent.futures.ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, [r["iid"] for r in rows]))


def notes(out_dir: pathlib.Path) -> dict:
    fr = json.loads(FRAME.read_text())
    prefetch(fr["rows"])
    items = []
    for row in fr["rows"]:
        mr = G.get(f"projects/{PROJECT}/merge_requests/{row['iid']}")
        if not mr:
            continue
        hn = human_notes(mr, G.notes_of(PROJECT, row["iid"]))
        if not hn:
            continue
        paths = changed_paths(row["iid"])
        for n in hn:
            items.append({"iid": row["iid"], "state": row["state"], "title": mr.get("title") or "", "branch": row["branch"],
                          "url": f"https://gitlab.com/{PATH}/-/merge_requests/{row['iid']}#note_{n['note_id']}",
                          "changed_paths": paths[:80], "changed_paths_total": len(paths), **n, "tied_file": tie(n, paths),
                          "keyword": keyword(n["body"])})
    out_dir.mkdir(parents=True, exist_ok=True)
    for k in range(0, len(items), SHARD):
        part = items[k:k + SHARD]
        lines = [f"# Shard {k // SHARD + 1}: notes {k + 1} to {k + len(part)} of {len(items)}", ""]
        for pos, it in enumerate(part, start=k + 1):
            body = it["body"] if len(it["body"]) <= NOTE_MAX else it["body"][:NOTE_MAX] + " [cut]"
            shown = ", ".join(it["changed_paths"]) + (f" (and {it['changed_paths_total'] - 80} more)" if it["changed_paths_total"] > 80 else "")
            lines += [f"## Note {pos}", f"- merge request: !{it['iid']} ({it['state']}) {it['title']}", f"- url: {it['url']}",
                      f"- by: {it['author']} on {it['created_at'][:10]}; " + (f"on the line of file `{it['file']}`" if it["file"] else "a general note"),
                      f"- files the merge request changes: {shown}", "", "```text", body.replace("```", "'''"), "```", ""]
        (out_dir / f"shard-{k // SHARD + 1:02d}.md").write_text("\n".join(lines))
    (out_dir / "notes.json").write_text(json.dumps(items, indent=1))
    return {"merge_requests_read": len(fr["rows"]), "with_people_notes": len({i["iid"] for i in items}), "notes": len(items),
            "keyword_tied": sum(1 for i in items if i["keyword"] and i["tied_file"]), "shards": -(-len(items) // SHARD)}


SEED, SAMPLE = 20261018, 1500
NOT_FOUND: list = []
GHOST = "ghost1"


def flagged_bots(usernames: set) -> set:
    """Authors GitLab itself marks as bots (the user's `bot` field), plus the Ghost User (amendment 2)."""
    names, bots, seen = sorted(usernames), set(), set()
    for k in range(0, len(names), 100):
        quoted = ", ".join(json.dumps(n) for n in names[k:k + 100])
        for u in graphql(f"{{ users(usernames: [{quoted}], first: 100) {{ nodes {{ username bot }} }} }}")["users"]["nodes"]:
            seen.add(u["username"])
            if u["bot"] is True:
                bots.add(u["username"])
    NOT_FOUND[:] = sorted(set(names) - seen)        # renamed or blocked accounts: their bot flag cannot be read, so kept
    return bots | {GHOST}


def write_shards(items: list, out_dir: pathlib.Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for k in range(0, len(items), SHARD):
        part = items[k:k + SHARD]
        lines = [f"# Shard {k // SHARD + 1}: notes {k + 1} to {k + len(part)} of {len(items)}", ""]
        for pos, it in enumerate(part, start=k + 1):
            body = it["body"] if len(it["body"]) <= NOTE_MAX else it["body"][:NOTE_MAX] + " [cut]"
            shown = ", ".join(it["changed_paths"]) + (f" (and {it['changed_paths_total'] - 80} more)" if it["changed_paths_total"] > 80 else "")
            lines += [f"## Note {pos}", f"- merge request: !{it['iid']} ({it['state']}) {it['title']}", f"- url: {it['url']}",
                      f"- by: {it['author']} on {it['created_at'][:10]}; " + (f"on the line of file `{it['file']}`" if it["file"] else "a general note"),
                      f"- files the merge request changes: {shown}", "", "```text", body.replace("```", "\'\'\'"), "```", ""]
        (out_dir / f"shard-{k // SHARD + 1:02d}.md").write_text("\n".join(lines))


def sample(all_notes: pathlib.Path, out_dir: pathlib.Path) -> dict:
    """Amendment 2: drop bot-flagged and deleted authors, then a seeded sample plus every keyword note, shuffled."""
    import random
    items = json.loads(all_notes.read_text())
    bots = flagged_bots({i["author"] for i in items})
    left = [i for i in items if i["author"] not in bots]
    rng = random.Random(SEED)
    kw = [i for i in left if i["keyword"]]
    rest = [i for i in left if not i["keyword"]]
    drawn = rng.sample(left, SAMPLE)
    chosen = {id(i) for i in drawn} | {id(i) for i in kw}
    labelled = [i for i in left if id(i) in chosen]
    rng.shuffle(labelled)
    for n, i in enumerate(labelled, start=1):
        i["position"], i["in_random_draw"] = n, any(i is d for d in drawn)
    write_shards(labelled, out_dir)
    (out_dir / "sample.json").write_text(json.dumps(labelled, indent=1))
    return {"notes": len(items), "bot_or_ghost_authors": sorted(bots), "authors_not_found_kept": NOT_FOUND, "notes_after_exclusion": len(left), "keyword_notes": len(kw),
            "random_draw": SAMPLE, "labelled": len(labelled), "shards": -(-len(labelled) // SHARD), "not_keyword_left": len(rest)}


_LINE = re.compile(r"^NOTE (\d+) \| (yes|no|unclear) \| (.*?) \| (.*)$")


def labels(reports: pathlib.Path, tier: str) -> dict:
    """The labellers' NOTE lines of one tier (H or S), by note number; a number labelled twice is an error."""
    out = {}
    for f in sorted(reports.glob(f"L-{tier}-*.md")):
        for line in f.read_text().splitlines():
            m = _LINE.match(line.strip().strip("`"))
            if m:
                n = int(m.group(1))
                assert n not in out, (tier, n, f.name)
                out[n] = {"answer": m.group(2), "file": m.group(3).strip(), "quote": m.group(4).strip()}
    return out


def adjudication(shards: pathlib.Path, reports: pathlib.Path) -> dict:
    """Amendment-2 numbering: the notes the two tiers split on, plus every 7th note, for the adjudicator."""
    items = {i["position"]: i for i in json.loads((shards / "sample.json").read_text())}
    h, s = labels(reports, "H"), labels(reports, "S")
    missing = {"H": sorted(set(items) - set(h)), "S": sorted(set(items) - set(s))}
    split = sorted(n for n in items if n in h and n in s and h[n]["answer"] != s[n]["answer"])
    sample = sorted(n for n in items if n % 7 == 0)
    todo = sorted(set(split) | set(sample) | set(missing["H"]) | set(missing["S"]))
    fence = "`" * 3
    lines = ["# Notes to adjudicate (split answers, every 7th note, and any note a labeller missed)", ""]
    for n in todo:
        it = items[n]
        body = it["body"] if len(it["body"]) <= NOTE_MAX else it["body"][:NOTE_MAX] + " [cut]"
        lines += [f"## Note {n}" + (" (sample)" if n % 7 == 0 else ""), f"- merge request: !{it['iid']} ({it['state']}) {it['title']}",
                  f"- by: {it['author']}; " + (f"on the line of file `{it['file']}`" if it["file"] else "a general note"),
                  "- files the merge request changes: " + ", ".join(it["changed_paths"][:40]), "", fence + "text",
                  body.replace(fence, "'" * 3), fence,
                  f"- Haiku: {h.get(n, {}).get('answer', 'MISSING')} | {h.get(n, {}).get('file', '-')}",
                  f"- Sonnet: {s.get(n, {}).get('answer', 'MISSING')} | {s.get(n, {}).get('file', '-')}", ""]
    both_yes = sorted(n for n in items if h.get(n, {}).get("answer") == "yes" and s.get(n, {}).get("answer") == "yes")
    agree = sum(1 for n in items if n in h and n in s and h[n]["answer"] == s[n]["answer"])
    return {"lines": lines, "missing": missing, "split": split, "sample": sample, "both_yes": both_yes, "agree": agree, "n": len(items)}


_ADJ = re.compile(r"^NOTE (\d+) \| (yes|no|unclear) \| (.*?) \| agrees: (\w+) \| (.*)$")


def adjudicated(reports: pathlib.Path) -> dict:
    out = {}
    for line in (reports / "ADJ.md").read_text().splitlines():
        m = _ADJ.match(line.strip().strip("`"))
        if m:
            out[int(m.group(1))] = {"answer": m.group(2), "file": m.group(3).strip(), "agrees": m.group(4)}
    return out


def final_labels(shards: pathlib.Path, reports: pathlib.Path) -> dict:
    """The rubric's rule: a scope comment when both labellers say yes; a split goes to the adjudicator."""
    h, s, a = labels(reports, "H"), labels(reports, "S"), adjudicated(reports)
    out = {}
    for n in h:
        if h[n]["answer"] == s[n]["answer"]:
            out[n] = {"answer": h[n]["answer"], "by": "both", "file": s[n]["file"]}
        else:
            assert n in a, f"split note {n} has no adjudication"
            out[n] = {"answer": a[n]["answer"], "by": "adjudicator", "file": a[n]["file"]}
    return out


def version_at(iid: int, when: str):
    """The newest diff version created at or before the note, else the oldest (rubric: files)."""
    vs = sorted(G.get(f"projects/{PROJECT}/merge_requests/{iid}/versions") or [], key=lambda v: v["created_at"])
    if not vs:
        return None
    before = [v for v in vs if v["created_at"] <= when]
    v = (before or vs[:1])[-1]
    return G.rebuilt(PROJECT, G.get(f"projects/{PROJECT}/merge_requests/{iid}/versions/{v['id']}") or {})


def task_of(mr: dict, notes: list) -> tuple[str, str]:
    n = G.flow_issue(notes, "duo-developer-gitlab-org", mr.get("source_branch"))
    raw = G.get(f"projects/{PROJECT}/issues/{n}") if n else None
    if raw:
        return f"{raw.get('title') or ''}\n{raw.get('description') or ''}", "flow_issue"
    for k in G.CI.closing_refs(mr.get("description")):
        raw = G.get(f"projects/{PROJECT}/issues/{k}")
        if raw:
            return f"{raw.get('title') or ''}\n{raw.get('description') or ''}", "closing_link"
    return f"{mr.get('title') or ''}\n{mr.get('description') or ''}", "mr_text"


def score_note(it: dict, file: str | None) -> dict:
    import aidev_recall as A
    row = {"position": it["position"], "url": it["url"], "iid": it["iid"], "state": it["state"], "path": file,
           "kind": A.listable_kind(file) if file else None, "in_random_draw": it["in_random_draw"], "keyword": it["keyword"]}
    if not file:
        return dict(row, scored=False, why="no file")
    mr = G.get(f"projects/{PROJECT}/merge_requests/{it['iid']}") or {}
    v = version_at(it["iid"], it["created_at"])
    files = G.to_files((v or {}).get("diffs") or [])
    if not files:
        return dict(row, scored=False, why="no readable version")
    if file not in {f["filename"] for f in files}:
        return dict(row, scored=False, why="not in the change then")
    task, src = task_of(mr, G.notes_of(PROJECT, it["iid"]))
    res = A.X.analyse(task, files, repo=PATH, version=6)
    return dict(row, scored=True, task_from=src, hit=A.listed(res.extras, file), files=len(files))


def scored_share(rows: list) -> dict:
    s = [r for r in rows if r.get("scored")]
    k = sum(1 for r in s if r["hit"])
    return {"comments": len(s), "listed": k, "wilson95": G.wilson(k, len(s)) if s else None}


def score(shards: pathlib.Path, reports: pathlib.Path) -> dict:
    items = {i["position"]: i for i in json.loads((shards / "sample.json").read_text())}
    final = final_labels(shards, reports)
    read_route = []
    for n, lab in sorted(final.items()):
        if lab["answer"] != "yes":
            continue
        it = items[n]
        file = it["file"] or (lab["file"] if lab["file"] in it["changed_paths"] else None) or it["tied_file"]
        read_route.append(dict(score_note(it, file), by=lab["by"]))
    keyword_route = [dict(score_note(it, it["file"] or it["tied_file"]), label=final[n]["answer"])
                     for n, it in sorted(items.items()) if it["keyword"] and (it["file"] or it["tied_file"])]
    listable = [r for r in read_route if r["kind"]]
    h, s = labels(reports, "H"), labels(reports, "S")
    return {
        "rubric": "eval/gitlab_scope_rubric.json", "rules_version": 6, "labelled_notes": len(items),
        "read_route": {"scope_comments": len(read_route), "primary_listable_kind": scored_share(listable),
                       "all": scored_share(read_route), "not_scored": {w: sum(1 for r in read_route if r.get("why") == w)
                                                               for w in ("no file", "no readable version", "not in the change then")},
                       "by_state": {st: scored_share([r for r in read_route if r["state"] == st]) for st in ("merged", "closed")},
                       "in_random_draw": sum(1 for r in read_route if r["in_random_draw"])},
        "keyword_route": {"notes": len(keyword_route), "all": scored_share(keyword_route),
                          "listable_kind": scored_share([r for r in keyword_route if r["kind"]]),
                          "labelled_not_scope": sum(1 for r in keyword_route if r["label"] != "yes")},
        "agreement": {"both_yes": sum(1 for n in h if h[n]["answer"] == s[n]["answer"] == "yes"),
                      "both_no": sum(1 for n in h if h[n]["answer"] == s[n]["answer"] == "no"),
                      "same_answer": sum(1 for n in h if h[n]["answer"] == s[n]["answer"]),
                      "split": sum(1 for n in h if h[n]["answer"] != s[n]["answer"])},
        "rows": read_route, "keyword_rows": keyword_route,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", action="store_true")
    ap.add_argument("--notes")
    ap.add_argument("--sample", nargs=2, metavar=("ALL_NOTES_JSON", "DIR"))
    ap.add_argument("--score", nargs=2, metavar=("SHARDS_DIR", "REPORTS_DIR"))
    a = ap.parse_args(argv)
    if a.frame:
        fr = frame()
        FRAME.write_text(json.dumps(fr, indent=1) + "\n")
        print(json.dumps(fr["counts"]))
    if a.notes:
        print(json.dumps(notes(pathlib.Path(a.notes))))
    if a.sample:
        print(json.dumps(sample(pathlib.Path(a.sample[0]), pathlib.Path(a.sample[1]))))
    if a.score:
        out = score(pathlib.Path(a.score[0]), pathlib.Path(a.score[1]))
        (ROOT / "results" / "gitlab_scope_v6.json").write_text(json.dumps(out, indent=1) + "\n")
        print(json.dumps({k: v for k, v in out.items() if not k.endswith("rows")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
