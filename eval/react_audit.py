"""Every answer the reaction flow recorded on a live merge request, checked against the same tests run as code
(itemator/replycheck.py). Writes results/react_audit_v1.json. Reads through `glab api`, GET only.

  python eval/react_audit.py            # showcase and second-project, every merge request with a comment or the card account as reviewer

A merge request is read when the card account is one of its reviewers or anyone commented on it. An extra
agrees when the flow recorded the answer and the person the tests give; `pending` is an answer the tests find that the
flow has not recorded (no run since that reply), and `missed` is the flow recording an answer the tests do not give."""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from itemator import replycheck as V  # noqa: E402

ROLES = {"anbuchelvanganesan.cse2024": "entrant", "anbuchelvannew": "second_account"}   # the entrant's own two accounts
PROJECTS = {"showcase": (87291130, ("ai-itemator-card-gitlab-ai-hackathon", "ai-itemator-react-gitlab-ai-hackathon")),
            "second-project": (87943563, ("ai-itemator-card-two-gitlab-ai-hackathon", "ai-itemator-react-two-gitlab-ai-hackathon"))}


def reviewed(pid: int, card: str) -> list[int]:
    out = []
    for page in range(1, 11):
        mrs = V.glab(f"projects/{pid}/merge_requests?state=all&per_page=100&page={page}")
        out += [m["iid"] for m in mrs if any(r["username"] == card for r in m.get("reviewers") or []) or m.get("user_notes_count")]
        if len(mrs) < 100:
            break
    return sorted(out)


def main() -> int:
    people: dict = {}

    def is_person(uid):
        if uid not in people:
            try:
                people[uid] = V.glab(f"users/{uid}").get("bot") is False
            except Exception:
                people[uid] = False
        return people[uid]

    rows = []
    for label, (pid, bots) in PROJECTS.items():
        for iid in reviewed(pid, bots[0]):
            mr = V.glab(f"projects/{pid}/merge_requests/{iid}")
            ds = V.glab(f"projects/{pid}/merge_requests/{iid}/discussions?per_page=100")
            for e in V.audit(mr, ds, is_person, bots):
                rec, want = e["recorded"], e["tests"]
                state = ("agree" if e["agree"] else "differ" if rec and want else "missed" if rec
                         else "pending" if want else "open")
                rows.append({"project": label, "mr": iid, "name": e["name"], "state": state,
                             "recorded": rec and {k: rec[k] for k in ("answer", "who", "note")},
                             "tests": want and {k: want[k] for k in ("answer", "who", "note")}})
    count = {s: sum(r["state"] == s for r in rows) for s in ("agree", "differ", "missed", "pending", "open")}
    out = {"what": "answers the reaction flow recorded on live merge requests, against its own tests run as code",
           "code": "itemator/replycheck.py", "extras": len(rows), "count": count,
           "recorded": count["agree"] + count["differ"] + count["missed"],
           "recorded_by": {k: sum(ROLES.get(r["recorded"]["who"], "others") == k for r in rows if r["recorded"])
                           for k in ("entrant", "second_account", "others")},
           "rows": rows}
    (ROOT / "results" / "react_audit_v1.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: out[k] for k in ("extras", "recorded", "count")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
