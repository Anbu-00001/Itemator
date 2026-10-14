"""The decision log: who decided each extra, collected after the merge (T43).

The reaction flow ends every merge request with one summary note ("Every extra has an answer: ...") that lists each extra
and who typed its name. This module reads those notes for the merge requests merged in a window, so a team can see
what shipped in a release and how the decisions were made. It reads only; the one write is the release description,
and only in release mode. Standard library only.

Notes are written by people as well as by the flow, so only a note whose author name starts with the reaction account's
prefix is read, and every name or title that reaches the output is cut and stripped of markdown. A note or a request that
cannot be read is counted, never guessed, and never fails the job.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

REACT_BOT = os.environ.get("ITEMATOR_REACT_BOT") or "ai-itemator-react-gitlab-ai-hackathon"   # the exact account: the project is public and anyone can comment
PAGES = 5                  # pages of 100 merge requests read per window
NOTES_PAGES = 5            # pages of 100 notes read per merge request
TIMEOUT = 15
START, END = "<!-- itemator:decisions:start -->", "<!-- itemator:decisions:end -->"
MARKER = re.compile(r"itemator:named=[0-9a-f]{40}")
_NAME = r"`([^`\n]{1,300})`"
_WHO = r"@([A-Za-z0-9_][A-Za-z0-9_.-]{0,254})"
_LINES = (
    ("kept", re.compile(r"- " + _NAME + r": kept, named by " + _WHO + r"\s*$")),
    ("kept", re.compile(r"- " + _NAME + r": kept, and a policy change was proposed in !(\d+), by " + _WHO + r"\s*$")),
    ("dismissed", re.compile(r"- " + _NAME + r": dismissed as not an extra, said " + _WHO + r"\s*$")),
    ("moved", re.compile(r"- " + _NAME + r": moved to !(\d+), by " + _WHO + r"\s*$")),
    ("removed", re.compile(r"- " + _NAME + r": removed from this merge request, by " + _WHO + r"\s*$")),
)
DECISIONS = ("kept", "dismissed", "moved", "removed")


def clean(text, limit: int = 80) -> str:
    """Text from a merge request that is shown outside backticks (a title, a user name): one line, no links, images,
    HTML, bare addresses (they would autolink) or @mentions (nobody is notified by a release), cut to `limit` characters."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    text = re.sub(r"(?i)\b[a-z][a-z0-9+.-]*:(?://|\\\\)\S*|\bwww\.\S+", "link removed", text)     # a bare address would autolink in a release
    text = re.sub(r"[`<>\[\]()!@]", "", text)
    return text[:limit].rstrip()


def clean_name(text, limit: int = 120) -> str:
    """An extra's name, shown inside backticks: one line and no backtick, so it cannot close the code span."""
    return re.sub(r"\s+", " ", str(text or "")).replace("`", "").replace("<!--", "<!-").strip()[:limit].rstrip()


def parse_summary(body):
    """The decisions in one summary note, or None when the note is not one (no marker, or no line it can read)."""
    if not isinstance(body, str) or not MARKER.search(body):
        return None
    items = []
    for line in body.split("\n"):
        for decision, rx in _LINES:
            m = rx.match(line)
            if m:
                g = m.groups()
                items.append({"name": clean_name(g[0]), "decision": decision, "who": g[-1],
                              "ref": int(g[1]) if len(g) == 3 else None})
                break
    return {"items": items} if items else None


def latest_summary(notes: list):
    """The newest summary note written by the reaction account, parsed, or None."""
    best = None
    for n in notes:
        if not isinstance(n, dict) or n.get("system") or str((n.get("author") or {}).get("username", "")) != REACT_BOT:
            continue
        parsed = parse_summary(n.get("body"))
        if parsed and (best is None or str(n.get("created_at", "")) >= best[0]):
            best = (str(n.get("created_at", "")), parsed)
    return best[1] if best else None


def entry(mr: dict, notes: list) -> dict:
    parsed = latest_summary(notes)
    author = str((mr.get("author") or {}).get("username", ""))
    items = [dict(i, by_author=(i["who"] == author)) for i in (parsed or {"items": []})["items"]]
    return {"iid": mr.get("iid"), "title": clean(mr.get("title")), "merged_at": mr.get("merged_at"), "author": clean(author, 255),
            "summary": parsed is not None, "extras": items}


def stats(entries: list) -> dict:
    items = [i for e in entries for i in e["extras"]]
    out = {"merge_requests": len(entries), "with_a_summary": len([e for e in entries if e["summary"]]), "extras": len(items),
           "by_author_alone": len([i for i in items if i["by_author"]]),
           "by_someone_else": len([i for i in items if not i["by_author"]])}
    for d in DECISIONS:
        out[d] = len([i for i in items if i["decision"] == d])
    return out


def markdown(entries: list, title: str = "Decisions in this release") -> str:
    s = stats(entries)
    lines = [f"## {title}", ""]
    if not s["merge_requests"]:
        return "\n".join(lines + ["No merge request was merged in this window."]) + "\n"
    lines.append(f"Merge requests merged: {s['merge_requests']}, of which with an Itemator summary: {s['with_a_summary']}. "
                 f"Extras decided: {s['extras']} ({s['kept']} kept, {s['dismissed']} dismissed, {s['moved']} moved, {s['removed']} removed). "
                 f"Typed by the merge request's own author: {s['by_author_alone']}; by someone else: {s['by_someone_else']}.")
    shown = [e for e in entries if e["extras"]]
    if shown:
        lines.append("")
    for e in shown:
        what = "; ".join(f"`{i['name']}` {i['decision']} by @{i['who']}" for i in e["extras"])
        lines.append(f"- !{e['iid']} {e['title']}: {what}")
    return "\n".join(lines) + "\n"


def merge_description(existing, section: str) -> str:
    """The release description with our block replaced (or appended): running twice changes nothing."""
    block = f"{START}\n{section.strip()}\n{END}"
    existing = existing or ""
    if START in existing and END in existing and existing.index(START) < existing.rindex(END):
        return existing[:existing.index(START)] + block + existing[existing.rindex(END) + len(END):]
    return (existing.rstrip() + "\n\n" if existing.strip() else "") + block + "\n"


class Api:
    """Read access to one GitLab project with a job token; `fetch(method, url, body)` returns (status, parsed json)."""

    def __init__(self, base: str, project, token: str, fetch=None):
        self.base, self.project, self.token = base.rstrip("/"), project, token
        self.host = urllib.parse.urlsplit(self.base).netloc
        self.fetch = fetch or self._fetch
        self.failures = 0
        self.listed = 0                      # merge requests the server listed, before the window is applied
        self.errors: list[str] = []          # "path: HTTP 403" or "path: unreadable", for the job log

    def _fetch(self, method, url, body=None):
        if urllib.parse.urlsplit(url).netloc != self.host:
            raise ValueError("only the GitLab server of this job is asked")
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"JOB-TOKEN": self.token, "Content-Type": "application/json", "User-Agent": "itemator-ci"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, None

    def get(self, path: str, missing_ok: bool = False, **params):
        url = f"{self.base}/projects/{self.project}/{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
        try:
            status, data = self.fetch("GET", url, None)
        except Exception:
            self.failures += 1
            self.errors.append(f"{path}: request failed")
            return None
        if status != 200:
            if not (missing_ok and status == 404):
                self.failures += 1
                self.errors.append(f"{path}: HTTP {status}")
            return None
        return data

    def pages(self, path: str, limit: int, **params) -> list:
        out = []
        for page in range(1, limit + 1):
            data = self.get(path, per_page=100, page=page, **params)
            if not isinstance(data, list):
                break
            out += data
            if len(data) < 100:
                break
        return out


def _utc(value):
    """An ISO time with any offset (tag dates come back as +05:30, merge dates as Z) as an aware UTC datetime, or None."""
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(datetime.timezone.utc)
    except (ValueError, TypeError):
        return None


def collect(api: Api, target: str, since: str, until: str) -> list:
    """Entries for the merge requests merged into `target` after `since` and up to `until` (ISO times), oldest first."""
    mrs = api.pages("merge_requests", PAGES, state="merged", target_branch=target, updated_after=since, order_by="updated_at", sort="asc")
    api.listed = len(mrs)
    lo, hi = _utc(since), _utc(until)
    inside = [m for m in mrs if isinstance(m, dict) and lo and hi and (t := _utc(m.get("merged_at"))) and lo < t <= hi]
    inside.sort(key=lambda m: _utc(m.get("merged_at")))
    return [entry(m, api.pages(f"merge_requests/{m['iid']}/notes", NOTES_PAGES, sort="asc")) for m in inside if isinstance(m.get("iid"), int)]


def window_for_tag(api: Api, tag: str):
    """(since, until) for a release: from the commit date of the previous tag (or the epoch) to the tag's own commit date."""
    tags = api.pages("repository/tags", 1, order_by="updated", sort="desc")
    dates = {t["name"]: _utc((t.get("commit") or {}).get("created_at")) for t in tags if isinstance(t, dict) and "name" in t}
    until = dates.get(tag) or datetime.datetime.now(datetime.timezone.utc)
    older = sorted(d for n, d in dates.items() if n != tag and d and d < until)
    return (older[-1] if older else datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)).isoformat(), until.isoformat()


def publish(api: Api, tag: str, section: str) -> str:
    """Put the section in the release description of `tag` (created when there is none). Returns what happened."""
    base = f"{api.base}/projects/{api.project}/releases"
    existing = api.get(f"releases/{urllib.parse.quote(tag, safe='')}", missing_ok=True)
    try:
        if isinstance(existing, dict):
            status, _ = api.fetch("PUT", f"{base}/{urllib.parse.quote(tag, safe='')}", {"description": merge_description(existing.get("description"), section)})
            return "updated" if status == 200 else f"not updated (HTTP {status})"
        status, _ = api.fetch("POST", base, {"tag_name": tag, "name": tag, "description": merge_description("", section)})
        return "created" if status in (200, 201) else f"not created (HTTP {status})"
    except Exception:
        return "not written (request failed)"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Collect who decided each extra in the merge requests merged in a window.")
    ap.add_argument("--api", default=os.environ.get("CI_API_V4_URL", ""))
    ap.add_argument("--project", default=os.environ.get("CI_PROJECT_ID", ""))
    ap.add_argument("--target", default=os.environ.get("CI_DEFAULT_BRANCH", "main"))
    ap.add_argument("--tag", default=os.environ.get("CI_COMMIT_TAG", ""), help="release mode: the window ends at this tag and the release is updated")
    ap.add_argument("--days", type=int, default=30, help="report mode: how many days back")
    ap.add_argument("--probe", action="store_true", help="print how many merge requests the server lists for a few filters, then stop")
    ap.add_argument("--out", default="decisions.json")
    ap.add_argument("--md", default="decisions.md")
    a = ap.parse_args(argv)
    token = os.environ.get("CI_JOB_TOKEN", "")
    if not (a.api and a.project and token):
        print("itemator decisions: needs CI_API_V4_URL, CI_PROJECT_ID and CI_JOB_TOKEN (a CI job); nothing done")
        return 0
    api = Api(a.api, a.project, token)
    if a.probe:
        for label, params in (("no filter", {}), ("state=merged", {"state": "merged"}), ("state=all", {"state": "all"}),
                              ("merged + target", {"state": "merged", "target_branch": a.target}),
                              ("merged + target + scope=all", {"state": "merged", "target_branch": a.target, "scope": "all"})):
            got = api.get("merge_requests", per_page=100, **params)
            print(f"probe {label}: {len(got) if isinstance(got, list) else got}")
        print("probe errors:", api.errors)
        return 0
    if a.tag:
        since, until = window_for_tag(api, a.tag)
        title = f"Decisions in {clean(a.tag, 60)}"
    else:
        now = datetime.datetime.now(datetime.timezone.utc)
        since, until = (now - datetime.timedelta(days=max(1, a.days))).isoformat(), now.isoformat()
        title = f"Decisions in the last {max(1, a.days)} days"
    entries = collect(api, a.target, since, until)
    report = {"window": {"since": since, "until": until, "target": a.target}, "stats": stats(entries), "merge_requests": entries,
              "unreadable_requests": api.failures}
    section = markdown(entries, title)
    with open(a.out, "w") as f:
        json.dump(report, f, indent=1)
    with open(a.md, "w") as f:
        f.write(section)
    done = publish(api, a.tag, section) if a.tag else "no release (report mode)"
    print(f"itemator decisions: {api.listed} listed, {report['stats']['merge_requests']} in the window, {report['stats']['extras']} extras, "
          f"{api.failures} unreadable requests{(' (' + '; '.join(api.errors[:3]) + ')') if api.errors else ''}; release: {done}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
