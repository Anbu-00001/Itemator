"""Counts the model calls of card runs from the Duo session record and checks what the run posted
(eval/card_model_calls_rubric.json, registered before any run of the edited flow). Read-only: GET calls through glab.

usage (repository root):
    python3 eval/card_model_calls.py --before                           # the three registered before sessions
    python3 eval/card_model_calls.py --after SESSION:IID [SESSION:IID ...]   # fresh runs; IID = the merge request
Both write results/card_model_calls.json (the arm given is replaced, the other kept)."""
from __future__ import annotations

import argparse, hashlib, json, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUBRIC = ROOT / "eval" / "card_model_calls_rubric.json"
FLOW = ROOT / "flows" / "itemator_card.yml"
OUT = ROOT / "results" / "card_model_calls.json"
PROJECT = 87291130
BEFORE = {"9641668": "139", "9650392": "166", "9651403": "174"}
LABELS = {"extras": "itemator::needs-names", "no_issue": "itemator::no-issue", "inside_ask": "itemator::inside-ask",
          "author_wrote_issue": "itemator::second-reader", "unplaced_only": "itemator::unplaced"}
DRAFTED = {"extras", "no_issue"}


# ---------------------------------------------------------------- pure parts (tests/test_card_model_calls.py)

def count_calls(checkpoints: list) -> dict:
    """Model calls = AI messages in the fullest snapshot of the conversation; tool calls = what those messages asked for."""
    best, most = [], -1
    for c in checkpoints or []:
        ck = c["checkpoint"]
        ck = json.loads(ck) if isinstance(ck, str) else ck
        msgs = [m.get("kwargs", m) for conv in ck["channel_values"].get("conversation_history", {}).values() for m in conv]
        if len(msgs) > most:
            best, most = msgs, len(msgs)
    ai = [m for m in best if m.get("type") == "AIMessage"]
    return {"model_calls": len(ai), "tool_calls": sum(len(m.get("tool_calls") or []) for m in ai),
            "models": sorted({(m.get("response_metadata") or {}).get("model_name") or "unknown" for m in ai})}


def copied_keys(flow_text: str) -> list[str]:
    """The FACTS.card keys the flow tells the model to copy, in order of first mention."""
    seen = []
    for k in re.findall(r"FACTS\.card\.(\w+)", flow_text):
        if k not in seen:
            seen.append(k)
    return seen


def check_run(facts: dict, keys: list[str], card_body: str, items: int, labels: list, title: str) -> dict:
    """What the posted card, the extra notes, the label and the title must equal, from the job's own facts."""
    card = facts.get("card") or {}
    missing = [k for k in keys if isinstance(card.get(k), str) and card[k] and card[k] not in card_body]
    state = facts.get("state")
    want_label = LABELS.get(state)
    draft = title.lower().startswith(("draft:", "[draft]", "(draft)"))
    return {"state": state, "card_lines_missing": missing, "card_matches": not missing,
            "extras": len(facts.get("extras") or []), "notes_and_threads": items,
            "items_match": items == len(facts.get("extras") or []),
            "label_ok": want_label in labels if want_label else None,
            "draft_ok": (draft if state in DRAFTED else True)}


def is_progress_note(body: str) -> bool:
    """The platform's own "card has started" note, which the bot posts before the flow writes anything."""
    return "card has started" in (body or "")


def summarise(runs: list[dict]) -> dict:
    n = [r["model_calls"] for r in runs]
    t = [r["tool_calls"] for r in runs]
    return {"runs": len(runs), "model_calls": n, "tool_calls": t, "mean_model_calls": round(sum(n) / len(n), 2) if n else None,
            "max_model_calls": max(n) if n else None, "modelled_credits": round(sum(n) * 0.3125, 2)}


def verdict(before: list[dict], after: list[dict]) -> dict:
    """The registered primary outcome: every after run has fewer model calls than the smallest before run that has the same
    number of extras or fewer, and the after mean is below the before mean."""
    out = {}
    for a in after:
        pool = [b["model_calls"] for b in before if b.get("extras") is None or a.get("extras") is None or b["extras"] <= a["extras"]]
        out[a["session"]] = bool(pool) and a["model_calls"] < min(pool)
    sb, sa = summarise(before), summarise(after)
    smallest = min((b["model_calls"] for b in before), default=None)
    post_hoc = {"note": "not registered: every after run against the smallest before run of any extras count",
                "each_after_run_below_the_smallest_before_run": {a["session"]: smallest is not None and a["model_calls"] < smallest for a in after}}
    lower = sa["mean_model_calls"] is not None and sb["mean_model_calls"] is not None and sa["mean_model_calls"] < sb["mean_model_calls"]
    return {"each_after_run_below_its_comparable_before_run": out, "after_mean_below_before_mean": lower, "cut": bool(out) and all(out.values()) and lower,
            "post_hoc": post_hoc}


# ---------------------------------------------------------------- reading GitLab (GET)

def glab(path: str):
    r = subprocess.run(["glab", "api", path], capture_output=True, text=True, timeout=120)
    if r.returncode:
        raise RuntimeError(f"{path}: {r.stderr.strip()[:200]}")
    return json.loads(r.stdout)


def read_run(session: str, iid: str) -> dict:
    flow_keys = copied_keys(FLOW.read_text())
    calls = count_calls(glab(f"ai/duo_workflows/workflows/{session}/checkpoints?per_page=100"))
    mr = glab(f"projects/{PROJECT}/merge_requests/{iid}")
    run = {"session": session, "mr": int(iid), **calls}
    jobs = glab(f"projects/{PROJECT}/pipelines/{mr['head_pipeline']['id']}/jobs?per_page=100") if mr.get("head_pipeline") else []
    job = next((j for j in jobs if j["name"] == "itemator"), None)
    if not job:
        return dict(run, checked=None, note="no itemator job on the head pipeline")
    facts = glab(f"projects/{PROJECT}/jobs/{job['id']}/artifacts/itemator.json")
    discussions = glab(f"projects/{PROJECT}/merge_requests/{iid}/discussions?per_page=100")
    notes = [n for d in discussions for n in d["notes"] if not n.get("system")]
    card = next((n for n in notes if "itemator:head=" in (n.get("body") or "")), None)
    bot = card["author"]["username"] if card else None
    items = [n for n in notes if bot and n["author"]["username"] == bot and n is not card and "itemator:head=" not in (n.get("body") or "")
             and not is_progress_note(n.get("body"))]
    run["extras"] = len(facts.get("extras") or [])
    run["checked"] = check_run(facts, flow_keys, card["body"] if card else "", len(items), mr.get("labels") or [], mr.get("title") or "")
    return run


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", action="store_true")
    ap.add_argument("--after", nargs="+", metavar="SESSION:IID")
    a = ap.parse_args(argv)
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    if a.before:
        old["before"] = [read_run(s, i) for s, i in BEFORE.items()]
    if a.after:
        old["after"] = [read_run(*x.split(":")) for x in a.after]
    if old.get("before") and old.get("after"):
        old["comparison"] = {"before": summarise(old["before"]), "after": summarise(old["after"]), **verdict(old["before"], old["after"])}
    old["summary"] = {"rubric": "eval/card_model_calls_rubric.json", "predictions": "eval/card_model_calls_rubric.json",
                      "predictions_sha256": hashlib.sha256(RUBRIC.read_bytes()).hexdigest()}
    OUT.write_text(json.dumps(old, indent=1) + "\n")
    print(json.dumps({k: v for k, v in old.items() if k != "summary"}, indent=1)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
