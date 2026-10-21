"""End to end, live (eval/e2e_live_rubric.json, pushed before the run): a person opens a staged merge request with the card
trigger on and nobody asks for the card; it must start by itself when the pipeline finishes, and its threads must carry
the 'Decided before' line and a file only the other checker (Overreach) named. Card run only. Raw record:
results/e2e_live.json.

usage (repository root, glab authenticated; spends Duo credits, one card run): python3 eval/e2e_live.py --credit-stop 346"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import react_study as R  # noqa: E402

OUT = R.ROOT / "results" / "e2e_live.json"
P = R.P
BRANCH = "demo/e2e-live"
LINE = "What it does, as the card's model read the diff (check it): "
DECIDED = "Decided before: kept on !278 by francisdevasargunam on 2026-10-21 (public answer log)."
PING = ('import json\nimport urllib.request\n\n\ndef ping(event):\n    """Report one usage event."""\n'
        '    urllib.request.urlopen("https://example.org/collect", data=json.dumps({"e": event}).encode(), timeout=2)\n')


def checks(notes: list, threads: dict, after: dict, opener: str) -> dict:
    """`notes`: the merge request's notes oldest first ({system, body, author}); `threads`: {extra name: first note body};
    `opener`: the person who opened it. Any other author outside Itemator's two flows (Code Review, a Developer flow) fails E6."""
    card = [i for i, n in enumerate(notes) if n["author"].startswith("ai-itemator-card") and not n["system"]]
    first = card[0] if card else len(notes)
    asked = any(("requested review" in n["body"] and n["system"]) or ("@ai-" in n["body"] and not n["author"].startswith("ai-"))
                for n in notes[:first])
    usage = next((b for name, b in threads.items() if "usage_ping.py" in name), "")
    others = [n for n in notes if n["author"] != opener and not n["author"].startswith(("ai-itemator-card", "ai-itemator-react"))]
    return {"E1_started_by_itself": bool(card) and not asked,
            "E2_decided_before": DECIDED in threads.get("rich", ""),
            "E3_other_checker": "named by another checker" in usage and "Overreach named it" in usage,
            "E4_read_line": bool(threads) and all(LINE in b for b in threads.values()),
            "E5_draft": any(n["system"] and n["author"].startswith("ai-itemator-card") and "marked this merge request as **draft**" in n["body"]
                            for n in notes),
            "E6_nothing_else": not any(after.get(R.TRIG[w]) for w in ("card", "react")) and not others}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--credit-stop", type=float, required=True)
    a = ap.parse_args()
    rec = {"staged": True, "branch": BRANCH, "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "meter_before": R.meter()}
    if rec["meter_before"] is not None and rec["meter_before"] > a.credit_stop:
        raise SystemExit(f"meter {rec['meter_before']} is above the stop {a.credit_stop}; nothing was run")
    issue = R.api(f"projects/{P}/issues", "POST", title="Parser: drop the empty item after a trailing comma",
                  description="`parse` in `examples/parser.py` returns an empty last item after a trailing comma. Drop it. Nothing else is asked.")
    rec["issue_iid"] = issue["iid"]
    R.api(f"projects/{P}/repository/branches", "POST", branch=BRANCH, ref="main")
    py = (R.ROOT / "pyproject.toml").read_text().replace("dependencies = []", 'dependencies = ["rich>=13"]', 1)
    try:
        R.trigger("card", True)
        R.commit(BRANCH, "Drop the empty item after a trailing comma", [
            {"action": "create", "file_path": "examples/parser.py",
             "content": "def parse(s):\n    \"\"\"Split on commas and drop the empty item a trailing comma leaves.\"\"\"\n"
                        "    items = s.split(',')\n    return items[:-1] if s.endswith(',') else items\n"},
            {"action": "update", "file_path": "pyproject.toml", "content": py},
            {"action": "create", "file_path": "examples/usage_ping.py", "content": PING}])
        mr = R.api(f"projects/{P}/merge_requests", "POST", source_branch=BRANCH, target_branch="main",
                   title="Drop the empty item after a trailing comma", description=f"Closes #{issue['iid']}\n\nStaged for the end-to-end live check.")
        iid = rec["mr_iid"] = mr["iid"]
        rec["mr_url"] = mr["web_url"]
        rec["card_done"] = R.wait_session_done(iid, "card", 1800)
    finally:
        R.trigger("card", False)
    time.sleep(5)
    notes = [{"system": n["system"], "body": n["body"], "author": n["author"]["username"], "at": n["created_at"]}
             for n in sorted(R.api(f"projects/{P}/merge_requests/{iid}/notes?per_page=100") or [], key=lambda n: n["created_at"])]
    threads = {}
    for d in R.discussions(iid):
        f = d["notes"][0]
        if f["author"]["username"].startswith("ai-itemator-card") and not f["system"] and "reply with its exact name" in f["body"]:
            name = f["body"][f["body"].index("`") + 1:].split("`", 1)[0]
            threads[name] = f["body"]
    rec["threads"] = threads
    rec["card_note"] = next((n["body"] for n in notes if n["author"].startswith("ai-itemator-card") and not n["system"]
                             and "reply with its exact name" not in n["body"] and "has started" not in n["body"]), None)
    rec["triggers_after"] = after = R.trigger_states()
    rec["checks"] = checks(notes, threads, after, mr["author"]["username"])
    rec["meter_after"] = R.meter()
    rec["left_open"] = "staged; left open and unmerged as the public record"
    OUT.write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec["checks"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
