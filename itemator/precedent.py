"""Decided before: when an extra on this merge request has the same name as one a person already answered on another merge
request, its thread says what that person decided, where and when, read from the public answer log (itemator/answerlog.py).
A fact beside the question, never an answer: the person still types one here. The log is used only when its whole hash chain
holds; a log that cannot be read or does not verify adds nothing, and the job goes on."""
from __future__ import annotations

import json
import urllib.request

from itemator import answerlog as A

WORDS = {"kept": "kept", "removed": "removed", "moved": "moved to its own merge request", "dismissed": "called not an extra"}


def url_of(env: dict) -> str | None:
    """Where the published log is: ITEMATOR_ANSWERS_URL, else this project's Pages site."""
    if env.get("ITEMATOR_ANSWERS_URL"):
        return env["ITEMATOR_ANSWERS_URL"]
    pages = (env.get("CI_PAGES_URL") or "").rstrip("/")
    return f"{pages}/answers/answers.json" if pages else None


def fetch(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "itemator"}), timeout=10) as r:
            return json.load(r)
    except (OSError, ValueError):
        return None


def find(log: dict | None, names: list[str], mr_iid: int) -> dict:
    """{name: the newest decision on it in another merge request}, from a log whose chain holds; {} otherwise."""
    entries = log.get("entries") if isinstance(log, dict) else None
    if not isinstance(entries, list) or not entries or A.verify(entries) is not None:
        return {}
    wanted, out = set(names), {}
    for e in entries:                                     # oldest first, so a later decision replaces an earlier one
        if e.get("iid") == mr_iid:
            continue
        for i in e.get("items") or ():
            if isinstance(i, dict) and i.get("name") in wanted and i.get("decision") in WORDS:
                out[i["name"]] = {"decision": i["decision"], "iid": e["iid"], "who": i.get("who"),
                                  "on": str(e.get("at", ""))[:10], "url": e.get("url")}
    return out


def sentence(p: dict) -> str:
    who = f" by {p['who']}" if p.get("who") else ""      # a plain username, never an @, so nobody is pinged
    return f"Decided before: {WORDS[p['decision']]} on !{p['iid']}{who} on {p['on']} (public answer log)."


def apply(report: dict, env: dict, mr_iid: int, get=fetch) -> int:
    """Add the sentence to each matching extra's thread and the fact to its plain_facts; returns how many matched."""
    extras = report.get("extras") or []
    url = url_of(env) if extras else None
    found = find(get(url), [e["name"] for e in extras], mr_iid) if url else {}
    for e in extras:
        p = found.get(e["name"])
        if p:
            e["thread_stub"] = f"{e['thread_stub']}\n\n{sentence(p)}"
            e["plain_facts"]["decided_before"] = p
    report["decided_before"] = {"read": bool(url), "matched": len(found)}
    return len(found)
