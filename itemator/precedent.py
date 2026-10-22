"""Decided before: when an extra on this merge request has the same name as one a person already answered on another merge
request, its thread says what that person decided, where and when, read from the public answer log (itemator/answerlog.py).
A fact beside the question, never an answer: the person still types one here. The log is used only when its whole hash chain
holds; a log that cannot be read or does not verify adds nothing, and the job goes on."""
from __future__ import annotations

import json
import urllib.request

from itemator import answerlog as A

WORDS = {"kept": "kept", "removed": "removed", "moved": "moved to its own merge request", "dismissed": "called not an extra"}


def project_of(url: str | None) -> str | None:
    """'group/sub/project' from a merge request link ('https://gitlab.com/group/sub/project/-/merge_requests/7#note_1')."""
    if not url or "/-/merge_requests/" not in url:
        return None
    path = url.split("/-/merge_requests/")[0].split("://", 1)[-1]
    return path.split("/", 1)[1] if "/" in path else None


def short(project: str, here: str | None) -> str:
    """'showcase' for a project in the same group as this one (GitLab links 'showcase!7' within a group), else the full path."""
    if here and "/" in here and project.rsplit("/", 1)[0] == here.rsplit("/", 1)[0]:
        return project.rsplit("/", 1)[1]
    return project


def shared_urls(env: dict) -> list[str]:
    """Other projects' public answer logs (ITEMATOR_SHARED_ANSWERS, separated by spaces or commas), this project's left out."""
    own = url_of(env)
    raw = (env.get("ITEMATOR_SHARED_ANSWERS") or "").replace(",", " ").split()
    return [u for u in dict.fromkeys(raw) if u != own]


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


def find(log: dict | None, names: list[str], mr_iid: int | None) -> dict:
    """{name: the newest decision on it in another merge request}, from a log whose chain holds; {} otherwise. `mr_iid` is
    this merge request's number in the log's own project; None for another project's log, where every entry counts."""
    entries = log.get("entries") if isinstance(log, dict) else None
    if not isinstance(entries, list) or not entries or A.verify(entries) is not None:
        return {}
    wanted, out = set(names), {}
    for e in entries:                                     # oldest first, so a later decision replaces an earlier one
        if e.get("iid") == mr_iid:
            continue
        for i in e.get("items") or ():
            if isinstance(i, dict) and i.get("name") in wanted and i.get("decision") in WORDS:
                earlier = out[i["name"]]["earlier"] + [(out[i["name"]]["decision"], out[i["name"]]["iid"])] if i["name"] in out else []
                out[i["name"]] = {"decision": i["decision"], "iid": e["iid"], "who": i.get("who"),
                                  "on": str(e.get("at", ""))[:10], "url": e.get("url"), "earlier": earlier}
    for p in out.values():                                # only the earlier answers that disagree with the newest are kept
        p["differ"] = [{"decision": d, "iid": n} for d, n in p.pop("earlier") if d != p["decision"]]
    return out


def sentence(p: dict) -> str:
    who = f" by {p['who']}" if p.get("who") else ""      # a plain username, never an @, so nobody is pinged
    where = p.get("project") or ""                        # another project's reference ('group/project!7'); none for this one
    head = f"Decided in {where}" if where else "Decided before"
    log = "its public answer log" if where else "public answer log"
    line = f"{head}: {WORDS[p['decision']]} on {where}!{p['iid']}{who} on {p['on']} ({log})."
    by = {}
    for d in p.get("differ") or ():
        by.setdefault(d["decision"], []).append(f"{where}!{d['iid']}")
    if not by:
        return line
    parts = [f"{WORDS[d]} on {_listed(refs)}" for d, refs in by.items()]
    return f"{line} Earlier answers differ: {'; '.join(parts)}."


def _listed(refs: list[str], most: int = 3) -> str:
    """'!1', '!1 and !2', '!1, !2 and !3', or '!1, !2, !3 and 4 more'."""
    if len(refs) > most:
        return f"{', '.join(refs[:most])} and {len(refs) - most} more"
    return refs[0] if len(refs) == 1 else f"{', '.join(refs[:-1])} and {refs[-1]}"


def apply(report: dict, env: dict, mr_iid: int, get=fetch) -> int:
    """Add the sentence to each matching extra's thread and the fact to its plain_facts; returns how many matched."""
    extras = report.get("extras") or []
    names = [e["name"] for e in extras]
    url = url_of(env) if extras else None
    found = find(get(url), names, mr_iid) if url else {}
    elsewhere = {}                                         # {name: [decision in another project, ...]}, in the variable's order
    for other in shared_urls(env) if extras else ():
        for name, p in find(get(other), names, None).items():
            p["project_path"] = project_of(p.get("url")) or other
            p["project"] = short(p["project_path"], env.get("CI_PROJECT_PATH"))
            elsewhere.setdefault(name, []).append(p)
    for e in extras:
        lines = ([found[e["name"]]] if e["name"] in found else []) + elsewhere.get(e["name"], [])
        if lines:
            e["thread_stub"] = f"{e['thread_stub']}\n\n" + " ".join(sentence(p) for p in lines)
            e["plain_facts"]["decided_before"] = lines[0]
            if elsewhere.get(e["name"]):
                e["plain_facts"]["decided_elsewhere"] = elsewhere[e["name"]]
    report["decided_before"] = {"read": bool(url), "matched": len(found)}
    if extras and shared_urls(env):
        report["decided_before"].update(shared_logs=len(shared_urls(env)), matched_elsewhere=len(elsewhere))
    return len(found) + len(elsewhere)
