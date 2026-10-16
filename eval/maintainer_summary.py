"""Summary of the maintainer study (eval/maintainer_notes_rubric.json): two blind labellers' readings of reviewers' notes
on the public replay's merge requests in GitLab's own codebase. The packets they read hold note text, so the label files
stay outside the repository; this writes counts, Cohen's kappa and, for each note, its reference, note id, file and the
two labels.

usage: python3 eval/maintainer_summary.py --labels <dir with L3_notes_*.json and L4_notes_*.json>"""
from __future__ import annotations

import argparse, collections, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import replay_gitlab as G
from label_summary import kappa

FRAME = G.ROOT / "results" / "maintainer_notes_frame.json"
OUT = G.ROOT / "results" / "maintainer_notes_labels.json"
SCOPE = "scope_request"


def key_of(packet: str, note_id) -> tuple[str, str, int]:
    """'C__247146__3656108151.json' or 'C__247146' -> ('C', 'gitlab-org/gitlab!247146', note id)."""
    pop, iid = packet.removesuffix(".json").split("__")[:2]
    return pop, f"gitlab-org/gitlab!{int(iid)}", int(note_id)


def load(d: pathlib.Path, who: str) -> tuple[dict, str | None]:
    """{key: entry} over every chunk file of one labeller, and the model it named."""
    out, model = {}, None
    for f in sorted(d.glob(f"{who}_notes_*.json")):
        data = json.loads(f.read_text())
        model = data.get("model") or model
        for e in data["labels"]:
            out[key_of(e["packet"], e["note_id"])] = e
    return out, model


def lists(path: str, extras: list) -> bool:
    """The card listed the file itself, or a directory that contains it."""
    return any(e.get("path") == path or ((e.get("path") or "").endswith("/") and path.startswith(e["path"])) for e in extras)


def note_file(frame_path: str | None, a: dict, b: dict) -> str | None:
    """The rubric's file: the diff note's path, else the path both labellers name, else none."""
    return frame_path or (a.get("file") if a.get("file") and a.get("file") == b.get("file") else None)


def summarize(l3: dict, l4: dict, frame: dict, extras_of, final_files_of, agent_files_of) -> dict:
    """extras_of(pop, ref): the scored card's extras (G: agent version; H, C: merged). final_files_of(ref) and
    agent_files_of(ref): the paths in the merged diff and in the agent's own version."""
    where = {(n["ref"], n["note_id"]): n for n in frame["notes"]}
    both = sorted(set(l3) & set(l4))
    pairs = [(l3[k]["label"], l4[k]["label"]) for k in both]
    scope = [k for k in both if l3[k]["label"] == l4[k]["label"] == SCOPE]
    candidate = lambda k: where[k[1:]]["candidate"]
    pops = {}
    for pop, c in sorted(frame["counts"].items()):
        mine = [k for k in both if k[0] == pop and candidate(k)]
        strict = {k[1] for k in mine if k in scope}
        either = {k[1] for k in mine if SCOPE in (l3[k]["label"], l4[k]["label"])}
        pops[pop] = {"merge_requests": c["merge_requests"], "with_a_scope_request": len(strict),
                     "wilson95": G.wilson(len(strict), c["merge_requests"]), "either_labeller": len(either)}
    control = [k for k in both if not candidate(k)]
    rows = [{"pop": k[0], "ref": k[1], "note_id": k[2], "file": note_file(where[k[1:]]["path"], l3[k], l4[k]),
             "candidate": candidate(k)} for k in scope]
    files = {}
    for pop, ref, path in sorted({(r["pop"], r["ref"], r["file"]) for r in rows if r["file"]}):
        f = files.setdefault(pop, {"files": 0, "in_final_diff": 0, "card_listed": 0, "rows": []})
        f["files"] += 1
        final = path in final_files_of(ref)
        f["in_final_diff"] += final
        listed = lists(path, extras_of(pop, ref))
        row = {"ref": ref, "file": path, "in_final_diff": final, "card_listed": listed}
        if pop == "G":
            row["in_agent_version"] = path in agent_files_of(ref)
            f["card_listed"] += listed
        else:
            f["card_listed"] += listed and final
        f["rows"].append(row)
    return {
        "what": "The maintainer study's reviewer notes, read by two blind labellers by the rubric written before any note was labelled.",
        "rubric": "eval/maintainer_notes_rubric.json",
        "agreement": {"entries": {"L3": len(l3), "L4": len(l4)}, "notes": len(both), "only_one_labeller": len(set(l3) ^ set(l4)),
                      "same_label": sum(a == b for a, b in pairs), "kappa": kappa(pairs),
                      "labels": {"L3": dict(collections.Counter(a for a, _ in pairs)), "L4": dict(collections.Counter(b for _, b in pairs))},
                      "disputed": [{"pop": k[0], "ref": k[1], "note_id": k[2], "L3": l3[k]["label"], "L4": l4[k]["label"]}
                                   for k in both if l3[k]["label"] != l4[k]["label"]]},
        "per_population": pops,
        "control": {"notes": len(control), "both_scope_request": sum(k in scope for k in control)},
        "scope_requests": rows,
        "files": files,
        "how_files_count": "G: against the agent version's card (in_agent_version, added after registration and before the labels were "
                           "combined, says whether the agent's own version had the file at all). H and C: against the merged card, "
                           "counted only where the file is still in the final diff. One row per merge request and file.",
        "limits": "Model labellers, not maintainers. The primary share counts only notes the word filter picked; the control "
                  "estimates what it misses. The card is rules v6 as already scored, not re-run.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--labels", required=True)
    a = ap.parse_args(argv)
    d = pathlib.Path(a.labels)
    (l3, m3), (l4, m4) = load(d, "L3"), load(d, "L4")
    frame = json.loads(FRAME.read_text())
    raw = (json.loads((G.ROOT / "results" / "public_replay_a1_raw.json").read_text())
           + json.loads((G.ROOT / "results" / "public_replay_a2_raw.json").read_text()))
    scored = {(r["pop"], r["ref"]): r for r in raw if not r.get("excluded")
              and r["version"] == ("agent" if r["pop"] == "G" else "merged") and r["pop"] in frame["counts"]}
    iid = lambda ref: int(ref.split("!")[1])
    final = lambda ref: {f["filename"] for f in G.to_files(G.pages(f"projects/{G.GITLAB}/merge_requests/{iid(ref)}/diffs", limit=5))}
    def agent(ref):
        v = G.agent_version(G.versions_oldest_first(G.GITLAB, iid(ref)))
        return {f["filename"] for f in G.to_files((v or {}).get("diffs"))}
    s = summarize(l3, l4, frame, lambda pop, ref: scored[(pop, ref)].get("extras") or [], final, agent)
    s["labellers"] = {"L3": m3, "L4": m4}
    OUT.write_text(json.dumps(s, indent=1) + "\n")
    print(json.dumps({k: s[k] for k in ("per_population", "control")}), {k: v for k, v in s["agreement"].items() if k != "disputed"},
          {p: {k: v for k, v in f.items() if k != "rows"} for p, f in s["files"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
