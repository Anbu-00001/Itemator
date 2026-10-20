"""The decision log: who decided each extra, collected after the merge (T43).

The reaction flow ends every merge request with one summary note ("Every extra has an answer: ...") that lists each extra
and who typed its name. This module reads those notes for the merge requests merged in a window, so a team can see
what shipped in a release and how the decisions were made. It reads only; the one write is the release description,
and only in release mode. Standard library only. Every time in the window is UTC.

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

from itemator import sci as SCI
from itemator import weight as W

REACT_BOT = os.environ.get("ITEMATOR_REACT_BOT") or "ai-itemator-react-gitlab-ai-hackathon"   # the exact account: the project is public and anyone can comment
CARD_BOT = os.environ.get("ITEMATOR_CARD_BOT") or "ai-itemator-card-gitlab-ai-hackathon"      # the account that opens each extra's thread
REASON = 200               # characters of a person's reason shown
ITEMATOR_JOB = "itemator"  # the policy-injected job whose artifact itemator.json holds each extra's measured weight
PIPELINES = 5              # a merge request's newest pipelines read for those artifacts
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
    """The decisions in one summary note and the commit it answered, or None when the note is not one (no marker, or no line
    it can read)."""
    marker = MARKER.search(body) if isinstance(body, str) else None
    if not marker:
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
    return {"items": items, "sha": marker.group(0).rsplit("=", 1)[1]} if items else None


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


_THREAD = re.compile(r"itemator:extra=(.{1,300}?)\s*(?:\)|-->)\s*$", re.M)     # the marker as "[//]: # (...)" or "<!-- ... -->"
_ANSWER_WORD = {"dismissed": "not an extra", "moved": "split", "removed": "remove"}


def _first_line(body: str) -> str:
    """The react prompt's T1 for the reply's first line: backticks out, spaces off both ends, one trailing full stop off."""
    line = re.sub(r"@ai-itemator-\S+", "", re.sub("`", "", str(body or "").split("\n", 1)[0])).strip()
    return line[:-1].strip() if line.endswith(".") else line


def reasons(discussions: list, items: list) -> dict:
    """{extra name: the reason its decider wrote}: the lines after the first of the reply that decided it, in that extra's own
    thread (opened by the card account), by the person the summary names. Their own words, cleaned; nothing is inferred."""
    out = {}
    who_of = {(i["name"], i["decision"]): i["who"] for i in items}
    for d in discussions:
        notes = d.get("notes") if isinstance(d, dict) else None
        if not notes or str((notes[0].get("author") or {}).get("username", "")) != CARD_BOT:
            continue
        m = _THREAD.search(str(notes[0].get("body") or ""))
        name = clean_name(m.group(1)) if m else None
        for (n, decision), who in who_of.items():
            if n != name or n in out:
                continue
            want = n if decision == "kept" else _ANSWER_WORD.get(decision)
            for r in notes[1:]:
                body = str(r.get("body") or "")
                first = _first_line(body)
                if str((r.get("author") or {}).get("username", "")) != who or "\n" not in body.strip() or want is None:
                    continue
                if (first == want if decision == "kept" else first.lower() == want):
                    reason = clean(body.split("\n", 1)[1], REASON)
                    if reason:
                        out[n] = reason
                    break
    return out


def report_weight(extra: dict):
    """{bytes, at_least} for one extra of an itemator.json report: the sum of what the job measured for its weighed packages
    (itemator/weight.py), or None when none was weighed. "at least" when a package was not weighed or a size was not given."""
    packages = (((extra.get("plain_facts") or {}).get("registry") or {}).get("packages")) or []
    ws = [p["weight"] for p in packages if isinstance(p, dict) and (p.get("weight") or {}).get("weight") == "ok"]
    if not ws or not all(type(w.get("bytes")) is int for w in ws):
        return None
    return {"bytes": sum(w["bytes"] for w in ws),
            "at_least": len(ws) < len(packages) or any(w.get("capped") or w.get("of", 0) > w.get("sized", 0) for w in ws)}


def job_report(api: "Api", pipeline_id: int):
    """The itemator job's own report (itemator.json) in one pipeline, or None when the job or its artifact is missing."""
    jobs = api.get(f"pipelines/{pipeline_id}/jobs", per_page=100, include_retried="true") or []
    job = next((j for j in jobs if isinstance(j, dict) and j.get("name") == ITEMATOR_JOB and isinstance(j.get("id"), int)), None)
    report = api.get(f"jobs/{job['id']}/artifacts/itemator.json", missing_ok=True) if job else None
    return report if isinstance(report, dict) else None


def unanswered_at_merge(api: "Api", iid: int, head_sha: str | None = None):
    """The extras the job listed on the commit the merge request was merged with (`head_sha`, its newest pipeline for that
    commit); None when that report is missing (artifacts are kept 30 days) or no pipeline ran on that commit."""
    pls = api.get(f"merge_requests/{iid}/pipelines", per_page=PIPELINES) or []
    pls = [p for p in pls if isinstance(p, dict) and isinstance(p.get("id"), int)] if isinstance(pls, list) else []
    pl = next((p for p in pls if not head_sha or p.get("sha") == head_sha), None)
    report = job_report(api, pl["id"]) if pl else None
    if report is None:
        return None
    return [clean_name(e.get("name")) for e in (report.get("extras") or []) if isinstance(e, dict) and e.get("name")]


def notes_of(api: "Api", iid: int) -> tuple[list, bool]:
    """A merge request's notes, and whether GitLab returned all of them (a failed read must not look like "no answer")."""
    before = api.failures
    notes = api.pages(f"merge_requests/{iid}/notes", NOTES_PAGES, sort="asc")
    return notes, api.failures == before


def measured_weights(api: "Api", iid: int) -> dict:
    """{extra name: weight} from the itemator job's own artifact (itemator.json) in the merge request's newest pipelines, never
    from note text, which carries names and paths the author chose. The newest report naming an extra wins, so a dependency
    later removed is read from the pipeline before its removal. Artifacts are kept 30 days (ci/itemator-job.yml)."""
    out: dict = {}
    for pl in (api.get(f"merge_requests/{iid}/pipelines", per_page=PIPELINES) or [])[:PIPELINES]:
        if not isinstance(pl, dict) or not isinstance(pl.get("id"), int):
            continue
        report = job_report(api, pl["id"])
        for e in (report or {}).get("extras", []) if isinstance(report, dict) else ():
            name = clean_name(e.get("name")) if isinstance(e, dict) else None
            w = report_weight(e) if name and name not in out else None
            if w:
                out[name] = w
    return out


def merger(mr: dict) -> str | None:
    """Who merged it: the person who pressed merge or set auto-merge (GitLab's merge_user, else merged_by), cleaned; None if not given."""
    who = clean(str(((mr.get("merge_user") or mr.get("merged_by") or {}).get("username")) or ""), 255)
    return who or None


def entry(mr: dict, notes: list, weights_of=None, unanswered_of=None, discussions_of=None) -> dict:
    """`weights_of()` (measured_weights for this merge request) is asked only when a dependency could have been kept or removed.
    `unanswered_of()` (unanswered_at_merge) only when no summary answers the commit that was merged: `unanswered` is then the
    extras the job listed on that commit that no summary answered ([] when none), or None when it cannot be told."""
    parsed = latest_summary(notes)
    author = str((mr.get("author") or {}).get("username", ""))
    items = [dict(i, by_author=(i["who"] == author)) for i in (parsed or {"items": []})["items"]]
    measured = weights_of() if weights_of and any(i["decision"] in ("kept", "removed") for i in items) else {}
    for i in items:
        if i["name"] in measured:
            i["weight"] = measured[i["name"]]
    why = reasons(discussions_of(), items) if discussions_of and items else {}
    for i in items:
        if i["name"] in why:
            i["reason"] = why[i["name"]]
    if parsed is not None and (not mr.get("sha") or parsed["sha"] == mr.get("sha")):
        unanswered = []                     # a summary is written only once every extra of that commit has an answer
    else:
        listed = unanswered_of() if unanswered_of else None
        answered = {i["name"] for i in items}
        unanswered = None if listed is None else [n for n in listed if n not in answered]
    return {"iid": mr.get("iid"), "title": clean(mr.get("title")), "merged_at": mr.get("merged_at"), "author": clean(author, 255),
            "summary": parsed is not None, "extras": items, "unanswered": unanswered, "merger": merger(mr)}


def stats(entries: list) -> dict:
    items = [i for e in entries for i in e["extras"]]
    out = {"merge_requests": len(entries), "with_a_summary": len([e for e in entries if e["summary"]]), "extras": len(items),
           "by_author_alone": len([i for i in items if i["by_author"]]),
           "by_someone_else": len([i for i in items if not i["by_author"]])}
    for d in DECISIONS:
        out[d] = len([i for i in items if i["decision"] == d])
    out["merged_unanswered"] = len([e for e in entries if e.get("unanswered")])
    out["unanswered_extras"] = sum(len(e.get("unanswered") or []) for e in entries)
    out["no_report"] = len([e for e in entries if e.get("unanswered") is None])
    return out


def weights(entries: list) -> dict:
    """The weight the cards gave the new dependencies, summed by decision: what `removed` kept out of every fresh install
    of the target branch, and what `kept` let in. The same measure on both sides, from the same cards."""
    out = {}
    for d in ("kept", "removed"):
        ws = [i["weight"] for e in entries for i in e["extras"] if i["decision"] == d and i.get("weight")]
        out[d] = {"dependencies": len(ws), "bytes": sum(w["bytes"] for w in ws), "at_least": any(w["at_least"] for w in ws)}
    return out


def unanswered_line(s: dict) -> str:
    """Said even when it is 0: the extras that reached the target branch with no recorded answer."""
    n, x = s["merged_unanswered"], s["unanswered_extras"]
    line = (f"Merged without a recorded answer for every extra: {n} merge request{'' if n == 1 else 's'} "
            f"({x} extra{'' if x == 1 else 's'}, from the job's own report on the commit that was merged)")
    gone = s["no_report"]
    return line + (f"; could not tell for {gone} (job reports are kept 30 days)." if gone else ".")


def markdown(entries: list, title: str = "Decisions in this release") -> str:
    s = stats(entries)
    lines = [f"## {title}", ""]
    if not s["merge_requests"]:
        return "\n".join(lines + ["No merge request was merged in this window."]) + "\n"
    lines.append(f"Merge requests merged: {s['merge_requests']}, of which with an Itemator summary: {s['with_a_summary']}. "
                 f"Extras decided: {s['extras']} ({s['kept']} kept, {s['dismissed']} dismissed, {s['moved']} moved, {s['removed']} removed). "
                 f"Typed by the merge request's own author: {s['by_author_alone']}; by someone else: {s['by_someone_else']}.")
    w = weights(entries)
    if w["kept"]["dependencies"] or w["removed"]["dependencies"]:
        def said(x):
            return f"{'at least' if x['at_least'] else 'about'} {W.human(x['bytes'])} ({x['dependencies']} new {'dependency' if x['dependencies'] == 1 else 'dependencies'})"
        lines.append(f"What new dependencies add to every fresh install, as the job measured each before the merge: removed, "
                     f"{said(w['removed'])}; kept, {said(w['kept'])}. Each counts everything it brings along, so this is an upper bound.")
        if w["removed"]["bytes"]:
            lines.append(f"What the removals keep out, {SCI.said(w['removed'])} per fresh install.")
    lines.append(unanswered_line(s))
    shown = [e for e in entries if e["extras"] or e.get("unanswered")]
    if shown:
        lines.append("")
    for e in shown:
        what = "; ".join(f"`{i['name']}` {i['decision']} by @{i['who']}" + (f", saying: {i['reason']}" if i.get("reason") else "")
                         for i in e["extras"]) or \
            "merged without a recorded answer: " + ", ".join(f"`{n}`" for n in e["unanswered"])
        lines.append(f"- !{e['iid']} {e['title']}: {what}" + (f"; merged by @{e['merger']}" if e.get("merger") else ""))
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

    def _fetch(self, method, url, body=None, token=True):
        if urllib.parse.urlsplit(url).netloc != self.host:
            raise ValueError("only the GitLab server of this job is asked")
        headers = {"Content-Type": "application/json", "User-Agent": "itemator-ci", **({"JOB-TOKEN": self.token} if token else {})}
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, None

    def get(self, path: str, missing_ok: bool = False, **params):
        url = f"{self.base}/projects/{self.project}/{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
        try:
            status, data = self.fetch("GET", url, None)
            if status in (401, 403) and self.fetch == self._fetch:    # a public project's read the job token may not cover
                status, data = self._fetch("GET", url, None, token=False)
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
    return [entry_of(api, m) for m in inside if isinstance(m.get("iid"), int)]


def entry_of(api: Api, m: dict) -> dict:
    notes, complete = notes_of(api, m["iid"])
    return entry(m, notes, lambda: measured_weights(api, m["iid"]),
                 (lambda: unanswered_at_merge(api, m["iid"], m.get("sha"))) if complete else None,
                 lambda: api.pages(f"merge_requests/{m['iid']}/discussions", NOTES_PAGES))


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
    report = {"window": {"since": since, "until": until, "target": a.target}, "stats": stats(entries), "weight": weights(entries),
              "merge_requests": entries,
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
