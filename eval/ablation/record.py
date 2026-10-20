"""Reads one finished ablation run from the Duo session record and the merge request (GET only) and appends it to
eval/ablation/state/ablation_runs.json: model calls, tool calls, seconds, what the flow posted.

usage: python3 eval/ablation/record.py TASK ARM SESSION"""
from __future__ import annotations

import json, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import card_model_calls as C  # noqa: E402

P = 87291130
RUNS = ROOT / "eval" / "ablation" / "state" / "ablation_runs.json"


def posted(discussions: list, accounts: tuple) -> dict:
    """What the flow's accounts wrote on the merge request: the card note, the thread count (diff notes and 'not attached' notes
    carrying an extra marker) and the names in the markers."""
    notes = [n for d in discussions for n in d["notes"] if not n["system"] and any(a in n["author"]["username"] for a in accounts)]
    names = [m for n in notes for m in re.findall(r"itemator:extra=([^\)\n]+)\)", n["body"])]
    return {"notes_by_flow": len(notes), "extra_markers": len(names), "extras_named": sorted(set(names)),
            "has_card": any("itemator:head=" in n["body"] for n in notes)}


def seconds(system_notes: list) -> float | None:
    from datetime import datetime
    st = [n["created_at"] for n in system_notes if n["body"].startswith("started session")]
    en = [n["created_at"] for n in system_notes if n["body"].startswith("completed session")]
    if not st or not en:
        return None
    f = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
    return round((f(en[-1]) - f(st[0])).total_seconds(), 1)


def glab(path):
    r = subprocess.run(["glab", "api", path], capture_output=True, text=True, timeout=120)
    return json.loads(r.stdout)


def main(task, arm, session):
    st = json.loads((ROOT / "eval" / "ablation" / "state" / "ablation_state.json").read_text())[f"{task}{arm}"]
    iid = st["iid"]
    calls = C.count_calls(glab(f"ai/duo_workflows/workflows/{session}/checkpoints"))
    disc = glab(f"projects/{P}/merge_requests/{iid}/discussions?per_page=100")
    notes = [n for d in disc for n in d["notes"] if n["system"] and session in n["body"]]
    mr = glab(f"projects/{P}/merge_requests/{iid}")
    row = {"task": task, "arm": arm, "mr": iid, "session": session, **calls, "seconds": seconds(notes),
           "posted": posted(disc, ("ai-itemator-card", "ai-itemator-probe")), "labels": mr["labels"], "title": mr["title"]}
    runs = json.loads(RUNS.read_text()) if RUNS.exists() else []
    runs = [r for r in runs if r["session"] != session] + [row]
    RUNS.write_text(json.dumps(runs, indent=1))
    print(json.dumps(row))


if __name__ == "__main__":
    main(*sys.argv[1:4])
