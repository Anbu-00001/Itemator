"""Maintainer study (eval/maintainer_notes_rubric.json): reviewers' notes on the public replay's merge requests in
GitLab's own codebase, filtered by a fixed word list, packed for two blind labellers. Everything comes from the replay's
cache (eval/cache/gitlab/); packets hold note text, so they are written OUTSIDE the repository (--out).

usage: python3 eval/maintainer_notes.py --out <private dir>        (frame counts go to results/maintainer_notes_frame.json)"""
from __future__ import annotations

import argparse, json, pathlib, random, re, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import replay_gitlab as G

SCOPE = re.compile(r"(?i)\b(?:remov(?:e|ed|ing)|revert(?:ed|ing)?|unrelated|out[- ]of[- ]scope|scope|separate (?:mr|merge request)|"
                   r"split|not (?:needed|necessary|required)|unnecessary|follow[- ]?up|why (?:is|was|are|were|do|did) (?:this|these|we|you))\b")
FRAME = G.ROOT / "results" / "maintainer_notes_frame.json"
CONTROL, SEED = 150, 20261018


def reviewer_notes(mr: dict, notes: list) -> list:
    """Notes by someone other than the merge request's author: no system notes, bots, duo- accounts or GitLabDuo."""
    author = (mr.get("author") or {}).get("username")
    def reviewer(n):
        u = (n.get("author") or {}).get("username") or ""
        return u != author and not G.is_bot(u) and not u.startswith("duo-") and u != "GitLabDuo"
    return [n for n in notes if not n.get("system") and (n.get("body") or "").strip() and reviewer(n)]


def note_path(n: dict) -> str | None:
    return (n.get("position") or {}).get("new_path") if n.get("type") == "DiffNote" else None


def rows_of(raw_a1: list, raw_a2: list) -> list:
    """The scored merge requests: G on its agent version, H and C on their merged version."""
    keep = lambda r, pop, version: r["pop"] == pop and r["version"] == version and not r.get("excluded")
    return [r for r in raw_a1 if keep(r, "G", "agent") or keep(r, "H", "merged")] + [r for r in raw_a2 if keep(r, "C", "merged")]


def frame(rows: list, mr_of, notes_of) -> tuple[list, dict]:
    """Every reviewer note of every row, marked as matching SCOPE or not, plus the counts."""
    out, counts = [], {}
    for r in rows:
        mr = mr_of(r)
        ns = reviewer_notes(mr, notes_of(r))
        c = counts.setdefault(r["pop"], {"merge_requests": 0, "reviewer_notes": 0, "candidates": 0})
        c["merge_requests"] += 1
        c["reviewer_notes"] += len(ns)
        for n in ns:
            hit = bool(SCOPE.search(n["body"]))
            c["candidates"] += hit
            out.append({"pop": r["pop"], "ref": r["ref"], "note_id": n["id"], "path": note_path(n), "candidate": hit})
    return out, counts


def control(notes: list, n: int = CONTROL, seed: int = SEED) -> list:
    rest = sorted((x for x in notes if not x["candidate"]), key=lambda x: x["note_id"])
    return rest if len(rest) <= n else sorted(random.Random(seed).sample(rest, n), key=lambda x: x["note_id"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    raw1 = json.loads((G.ROOT / "results" / "public_replay_a1_raw.json").read_text())
    raw2 = json.loads((G.ROOT / "results" / "public_replay_a2_raw.json").read_text())
    rows = rows_of(raw1, raw2)
    iid = lambda r: int(r["ref"].split("!")[1])
    mrs = {r["ref"]: G.get(f"projects/{G.GITLAB}/merge_requests/{iid(r)}") or {} for r in rows}
    notes = {r["ref"]: G.notes_of(G.GITLAB, iid(r)) for r in rows}
    allnotes, counts = frame(rows, lambda r: mrs[r["ref"]], lambda r: notes[r["ref"]])
    chosen = [x for x in allnotes if x["candidate"]] + [dict(x, control=True) for x in control(allnotes)]
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    by_id = {n["id"]: n for ns in notes.values() for n in ns}
    row_of = {r["ref"]: r for r in rows}
    names = []
    for x in chosen:
        mr, r = mrs[x["ref"]], row_of[x["ref"]]
        n = int(r["issue_refs"][0].lstrip("#")) if r.get("issue_refs") else None
        issue = (G.get(f"projects/{G.GITLAB}/issues/{n}") or {}) if n else {}
        name = f"{x['pop']}__{x['ref'].split('!')[1]}__{x['note_id']}.json"
        (out / name).write_text(json.dumps({"ref": x["ref"], "note_id": x["note_id"], "path": x["path"],
                                            "note": by_id[x["note_id"]]["body"][:3000], "mr_title": mr.get("title") or "",
                                            "mr_description": (mr.get("description") or "")[:4000],
                                            "issue": f"{issue.get('title') or ''}\n{(issue.get('description') or '')[:4000]}"},
                                           indent=1, ensure_ascii=False) + "\n")
        names.append(name)
    rubric = json.loads((G.ROOT / "eval" / "maintainer_notes_rubric.json").read_text())
    (out / "INDEX.json").write_text(json.dumps({"rubric": {k: rubric[k] for k in ("labels", "file")}, "packets": names}, indent=1) + "\n")
    FRAME.write_text(json.dumps({"what": "Maintainer study frame (eval/maintainer_notes_rubric.json): counts only.", "counts": counts,
                                 "control": len(chosen) - sum(x["candidate"] for x in chosen),
                                 "notes": sorted(({"ref": x["ref"], "note_id": x["note_id"], "path": x["path"], "candidate": x["candidate"],
                                                   "control": bool(x.get("control"))} for x in chosen), key=lambda x: x["note_id"])},
                                indent=1) + "\n")
    print(counts, len(chosen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
