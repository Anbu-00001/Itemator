"""Label packets for the public replay (eval/public_replay_label_rubric.json): for each sampled merge request, the issue,
the merge request's title and description, and the diff the card was computed from, with the listed extras marked.
Packets hold other projects' diff text, so they are written OUTSIDE the repository (--out) and never committed.
Everything comes from the replay's cache (eval/cache/gitlab/); no new request is made for a cached answer.

usage: python3 eval/label_packets.py --raw results/public_replay_a1_raw.json --out <private dir>"""
from __future__ import annotations

import argparse, json, pathlib, random, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import replay_gitlab as G

RUBRIC = G.ROOT / "eval" / "public_replay_label_rubric.json"
FILE_LIMIT, TOTAL_LIMIT = 6000, 60000


def sample(raw: list, seed: int = 20261017) -> dict:
    """The rubric's sample: every flagged G agent row (80 drawn if more), every flagged F agent row after the per-project
    cap, 30 flagged H rows, and 20 unflagged G agent rows for misses; each list drawn from sorted references."""
    def rows(pop, version, flagged):
        return sorted((r for r in raw if r["pop"] == pop and r["version"] == version and not r.get("excluded")
                       and bool(r.get("extras")) == flagged), key=lambda r: r["ref"])
    def draw(xs, n):
        return xs if len(xs) <= n else sorted(random.Random(seed).sample(xs, n), key=lambda r: r["ref"])
    f_capped = {r["ref"] for r in G.capped(rows("F", "agent", True) + rows("F", "agent", False), 5)}
    return {"G_flagged": draw(rows("G", "agent", True), 80),
            "F_flagged": [r for r in rows("F", "agent", True) if r["ref"] in f_capped],
            "H_flagged": draw(rows("H", "merged", True), 30),
            "G_unflagged": draw(rows("G", "agent", False), 20)}


def diff_text(files: list, marked: set) -> str:
    """The listed extras' files first (so a long diff never cuts them), then the rest, within the size limits."""
    out, total = [], 0
    dirs = [m for m in marked if m.endswith("/")]      # a grouped extra names a directory; "./" (the root) starts no file name
    files = sorted(files, key=lambda f: not (f["filename"] in marked or any(f["filename"].startswith(d) for d in dirs)))
    for f in files:
        head = f"### {f['filename']} ({f['status']}){'  <- LISTED EXTRA' if f['filename'] in marked else ''}\n"
        body = f["patch"] or "(no diff shown: binary, withheld or empty)\n"
        if len(body) > FILE_LIMIT:
            body = body[:FILE_LIMIT] + f"\n... ({len(body) - FILE_LIMIT} more characters cut)\n"
        if total + len(head) + len(body) > TOTAL_LIMIT:
            out.append(f"... ({len(files) - len(out)} more files not shown)\n")
            break
        out.append(head + body)
        total += len(head) + len(body)
    return "\n".join(out)


def packet(row: dict, frame_rows: dict) -> dict:
    """Rebuild the scored diff for one row through the replay's own (cached) calls."""
    pid, iid = frame_rows[row["ref"]], int(row["ref"].split("!")[1])
    mr = G.get(f"projects/{pid}/merge_requests/{iid}")
    issues, _ = G.linked(row["pop"], pid, mr, G.notes_of(pid, iid))
    if row["version"] == "agent":
        files = G.to_files(G.agent_version(G.versions_oldest_first(pid, iid))["diffs"])
    else:
        files = G.to_files(G.pages(f"projects/{pid}/merge_requests/{iid}/diffs", limit=5))
    marked = {e["path"] for e in row.get("extras") or []}
    return {"ref": row["ref"], "pop": row["pop"], "version": row["version"],
            "issue": "\n\n".join(f"# {i['ref']}: {i['title']}\n{i['description']}" for i in issues),
            "mr_title": mr.get("title") or "", "mr_description": (mr.get("description") or "")[:8000],
            "listed_extras": row.get("extras") or [], "diff": diff_text(files, marked)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--raw", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--amendment", type=int, default=1)
    a = ap.parse_args(argv)
    G.AMENDMENT = a.amendment
    raw = json.loads(pathlib.Path(a.raw).read_text())
    fr = json.loads((G.CACHE / "frame_private.json").read_text())
    pid_of = {}
    for pop, rows in fr["rows"].items():
        for r in rows:
            pid_of[f"{'gitlab-org/gitlab' if r['project'] == G.GITLAB else G.anon(r['project'])}!{r['iid']}"] = r["project"]
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    s = sample(raw)
    index = {}
    for group, rows in s.items():
        index[group] = []
        for r in rows:
            p = packet(r, pid_of)
            name = f"{group}__{r['ref'].replace('/', '_').replace('!', '_')}.json"
            (out / name).write_text(json.dumps(p, indent=1, ensure_ascii=False) + "\n")
            index[group].append(name)
    (out / "INDEX.json").write_text(json.dumps({"rubric": json.loads(RUBRIC.read_text()), "groups": index}, indent=1) + "\n")
    print({g: len(v) for g, v in index.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
