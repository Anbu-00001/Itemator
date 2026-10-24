"""The reaction flow's answer tests, in code: which reply answers each extra thread, and who gave it.

flows/itemator_react.yml steps 3 and 4 tell a model which reply counts: string tests, written as prose. This module runs
the same tests on a merge request's discussions, so every answer the flow recorded can be checked against them
afterwards: `python -m itemator.replycheck --project 87291130 --mr 278` (reads through `glab api`, GET only).
The flow does not call this module; the CI job's merge hold does (`unanswered`), so code, not the model, has the last word. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

from itemator.decisions import CARD_BOT, REACT_BOT
from itemator.stopgaps import UNTIL_OFFER

OTHER_ONLY = "A reply from the merge request author does not count."
ALWAYS_OK = "To keep it and stop asking about this file, reply `always`; that opens a merge request that changes the team policy."
ASKER_START, ASKER_END = "Only the person who wrote the linked issue (", ") can keep this."
MEMBERS_ONLY = "Only a project member with the Developer role or higher can answer here."      # ci.MEMBERS_ONLY
BUMP_START = "To move it to the new version too, reply `bump`: in `"                  # ci.thread_stub, from bump_offer
TAKE_START = "To take it out, change `"                                               # stopgaps.TAKE_OUT
UNTIL = re.compile(r"until #([1-9][0-9]{0,8})")
DEVELOPER = 30          # GitLab's access_level for Developer: the bar its own approval rules use by default
RECORDS = {"Kept:": "named", "Dismissed:": "dismissed", "Split:": "split", "Removed:": "remove", "Bumped:": "bump",
           "Taken out:": "taken_out"}
REFUSALS = ("Cannot split:", "Split failed:", "Split partly done:", "Cannot remove:", "Remove failed:", "Remove partly done:",
            "Cannot remember:", "Remember failed:", "Cannot bump:", "Bump failed:", "Bump partly done:", "Cannot keep until", "Cannot take out:")
USER = re.compile(r"@([A-Za-z0-9_.-]+)")
BOT_MENTION = re.compile(r"@ai-itemator-[A-Za-z0-9_.-]*")


def _trim(s: str, ends: str = ".") -> str:
    s = s.strip()
    return s[:-1] if s and s[-1] in ends else s


def t1(body: str) -> str:
    return _trim((body or "").split("\n", 1)[0].replace("`", ""))


def t2(body: str) -> str:
    return _trim(USER.sub("", t1(body))).strip().lower()


def name_of(first: str) -> tuple[str, str] | None:
    """(NAME, the text after the backtick that closes it) from a thread's first note, or None."""
    lines = first.split("\n")
    if lines and lines[0].startswith("(Not attached"):
        lines = lines[1:]
    m = re.search(r"`([^`]*)`", "\n".join(lines))
    return (m.group(1), "\n".join(lines)[m.end():]) if m else None


def askers(after: str) -> list | None:
    """The usernames an ASKER_ONLY thread names, [] when the list cannot be read, None when the thread is not ASKER_ONLY."""
    if ASKER_START not in after:
        return None
    part = after[after.rindex(ASKER_START) + len(ASKER_START):]
    if ASKER_END not in part:
        return []
    names = part[:part.index(ASKER_END)].split(" or ")
    if not all(re.fullmatch(r"@[A-Za-z0-9_.-]+", n) for n in names):
        return []
    return [n[1:] for n in names]


def bump_of(after: str, start: str = BUMP_START, n: int = 3) -> tuple | None:
    """(PATH, OLD, NEW) a BUMP_OK thread offers: the next three backticked texts after BUMP_START; None otherwise.
    With TAKE_START and 2: (TAKE_PATH, TAKE_LINE), what a stopgap thread asks to take out."""
    if start not in after:
        return None
    got = re.findall(r"`([^`]*)`", after[after.index(start) + len(start) - 1:])
    return tuple(got[:n]) if len(got) >= n else None


def member(m, at: str) -> bool:
    """A project member record (GET /projects/:id/members/all/:user_id) that may answer a MEMBERS_ONLY thread on the
    day `at` (the reply's created_at): Developer or higher, active, and not expired before that day."""
    if not isinstance(m, dict) or m.get("state") != "active" or not isinstance(m.get("access_level"), int):
        return False
    exp = m.get("expires_at")
    return m["access_level"] >= DEVELOPER and (exp is None or (isinstance(exp, str) and exp > (at or "")[:10]))


def threads(discussions: list, card_bot: str = CARD_BOT) -> list[dict]:
    """Step 3: the extra threads, with the flags their first note sets."""
    out = []
    for d in discussions:
        notes = d.get("notes") or []
        if not notes:
            continue
        f = notes[0]
        if f["author"]["username"] != card_bot or "reply with its exact name" not in (f.get("body") or ""):
            continue
        got = name_of(f["body"])
        if not got:
            continue
        name, after = got
        out.append({"id": d["id"], "name": name, "notes": notes, "other_only": OTHER_ONLY in after,
                    "always_ok": ALWAYS_OK in after, "askers": askers(after), "members_only": MEMBERS_ONLY in after,
                    "bump": bump_of(after), "until_ok": UNTIL_OFFER in after, "take_out": bump_of(after, TAKE_START, 2)})
    return out


def card_of(discussions: list, card_bot: str = CARD_BOT) -> list:
    for d in discussions:
        notes = d.get("notes") or []
        if notes and notes[0]["author"]["username"] == card_bot and " beyond " in (notes[0].get("body") or "") \
                and "reply with its exact name" not in notes[0]["body"]:
            return notes
    return []


def _replies(notes: list, is_person, author: str, other_only: bool, before: str | None, bots: tuple, is_member=None) -> list:
    """`is_member(user id, created_at)`: given only for a MEMBERS_ONLY thread; a reply by anyone else is left out."""
    return [n for n in notes[1:] if n["author"]["username"] not in bots and not n.get("system")
            and is_person(n["author"]["id"]) and not (other_only and n["author"]["username"] == author)
            and (before is None or n["created_at"] < before)
            and (is_member is None or is_member(n["author"]["id"], n["created_at"]))]


def record(th: dict, react_bot: str = REACT_BOT) -> dict | None:
    """The first note the flow wrote that settles this thread: {"answer", "who", "note"}."""
    for n in th["notes"][1:]:
        if n["author"]["username"] != react_bot:
            continue
        for start, kind in RECORDS.items():
            if (n.get("body") or "").startswith(start):
                line = n["body"].split("\n", 1)[0]
                cut = max(line.rfind("by @"), line.rfind("said @"))
                m = USER.match(line[line.index("@", cut):]) if cut >= 0 else None
                who = m.group(1).rstrip(".") if m else None
                return {"answer": kind, "who": who, "note": n["id"], "at": n["created_at"]}
    return None


def answer(th: dict, card: list, author: str, crew: set, is_person, before: str | None = None,
           bots: tuple = (CARD_BOT, REACT_BOT), is_member=None) -> dict | None:
    """Step 4: the reply that answers this thread, judged on the notes written before `before` (the flow's record).
    `is_member(user id, created_at)` decides a MEMBERS_ONLY thread; with no `is_member` nobody counts there."""
    members = (is_member or (lambda *_: False)) if th.get("members_only") else None
    name, asks = th["name"], th["askers"]
    ok_asker = (lambda u: asks is None or u in asks)
    refusals = [n["created_at"] for n in th["notes"][1:] if n["author"]["username"] == bots[1]
                and (n.get("body") or "").startswith(REFUSALS) and (before is None or n["created_at"] < before)]
    last_refusal = max(refusals) if refusals else ""
    for n in _replies(th["notes"], is_person, author, th["other_only"], before, bots, members):
        u, a, b = n["author"]["username"], t1(n["body"]), t2(n["body"])
        later = n["created_at"] > last_refusal
        if (a == name or BOT_MENTION.sub("", a).strip() == name) and ok_asker(u):
            return {"answer": "named", "who": u, "note": n["id"]}
        if b == "not an extra" and ok_asker(u):
            return {"answer": "dismissed", "who": u, "note": n["id"]}
        for word in ("split", "remove"):
            if b == word and b != name.lower() and u in crew and later:
                return {"answer": word, "who": u, "note": n["id"]}
        if th["always_ok"] and b == "always" and b != name.lower() and u in crew and ok_asker(u) and later:
            return {"answer": "named", "who": u, "note": n["id"], "always": True}
        if th.get("bump") and b == "bump" and b != name.lower() and u in crew and later:
            return {"answer": "bump", "who": u, "note": n["id"]}
        until = UNTIL.fullmatch(b)
        if th.get("until_ok") and until and ok_asker(u) and later:
            return {"answer": "named", "who": u, "note": n["id"], "until": int(until.group(1))}
        if th.get("take_out") and b == "taken out" and b != name.lower() and u in crew and later:
            return {"answer": "taken_out", "who": u, "note": n["id"]}
    for n in _replies(card, is_person, author, th["other_only"], before, bots, members):
        if not ok_asker(n["author"]["username"]):
            continue
        for line in (n.get("body") or "").split("\n"):
            if _trim(BOT_MENTION.sub("", line.replace("`", "")), ".,").strip() == name:
                return {"answer": "named", "who": n["author"]["username"], "note": n["id"], "from_card": True}
    return None


def audit(mr: dict, discussions: list, is_person, bots: tuple = (CARD_BOT, REACT_BOT), is_member=None) -> list[dict]:
    """For each extra (threads with one NAME are one extra): what the tests give, what the flow recorded, and whether
    they agree. `agree` is None while neither has an answer."""
    author = mr["author"]["username"]
    crew = {author} | {p["username"] for p in (mr.get("assignees") or []) + (mr.get("reviewers") or [])}
    card, rows, by_name = card_of(discussions, bots[0]), [], {}
    for th in threads(discussions, bots[0]):
        by_name.setdefault(th["name"], []).append(th)
    for name, ths in by_name.items():
        rec = next((r for r in (record(t, bots[1]) for t in ths) if r), None)
        want = next((a for a in (answer(t, card, author, crew, is_person, rec["at"] if rec else None, bots, is_member) for t in ths) if a), None)
        if rec and want:
            agree = rec["answer"] == want["answer"] and rec["who"] == want["who"]
        elif rec or want:
            agree = False
        else:
            agree = None
        rows.append({"name": name, "threads": len(ths), "recorded": rec, "tests": want, "agree": agree})
    return rows


def unanswered(rows: list) -> list:
    """The extras the string tests give no answer for. The merge hold (itemator/ci.py `hold`) stays on while this is not
    empty, so a thread resolved by hand, or an answer the model misread, cannot lift it."""
    return [r["name"] for r in rows if not r["tests"]]


def glab(path: str):
    return json.loads(subprocess.run(["glab", "api", path], capture_output=True, text=True, check=True).stdout)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="itemator.replycheck", description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--project", required=True)
    ap.add_argument("--mr", type=int, action="append", required=True)
    a = ap.parse_args(argv)
    people: dict = {}

    def is_person(uid):
        if uid not in people:
            try:
                people[uid] = glab(f"users/{uid}").get("bot") is False
            except Exception:
                people[uid] = False
        return people[uid]

    members: dict = {}

    def is_member(uid, at):
        if uid not in members:
            try:
                members[uid] = glab(f"projects/{a.project}/members/all/{uid}")
            except Exception:
                members[uid] = None
        return member(members[uid], at)

    out = []
    for iid in a.mr:
        mr = glab(f"projects/{a.project}/merge_requests/{iid}")
        ds = glab(f"projects/{a.project}/merge_requests/{iid}/discussions?per_page=100")
        out.append({"project": a.project, "mr": iid, "extras": audit(mr, ds, is_person, is_member=is_member)})
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
