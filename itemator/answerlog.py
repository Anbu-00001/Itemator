"""The answer log: `python -m itemator.answerlog --out public/answers`, or `--verify answers.json` to check a downloaded copy.

Every summary note the reaction account wrote on a merge request labelled `itemator::named` becomes one entry, oldest first, and each
entry carries the SHA-256 of the one before it, so an entry cannot be changed or taken out later without the chain showing it. Each
build starts from the log this site published last: what it recorded stays, word for word and in order, and only new notes are
added after it. A note edited or deleted after it was recorded is listed as such; the entry itself is kept. Reads merge requests and
notes with the CI job token and the published log over HTTPS (nothing is written to GitLab); writes answers.json and index.html."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import html
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

from itemator import decisions as D

LABEL = "itemator::named"   # set by the reaction flow once every extra of a merge request has an answer
START = "0" * 64            # what the first entry chains to
_CHAIN = ("prev", "hash")


def entries_from(iid: int, notes: list, project_url: str) -> list:
    """One entry per summary note from the reaction account on this merge request."""
    out = []
    for n in notes:
        if not isinstance(n, dict) or n.get("system") or str((n.get("author") or {}).get("username", "")) != D.REACT_BOT:
            continue
        body = str(n.get("body") or "")
        parsed = D.parse_summary(body)
        if not parsed or not isinstance(n.get("id"), int):
            continue
        out.append({"iid": iid, "note": n["id"], "at": str(n.get("created_at", "")), "commit": parsed["sha"],
                    "items": [{k: i[k] for k in ("name", "decision", "who", "ref")} for i in parsed["items"]],
                    "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                    "url": f"{project_url}/-/merge_requests/{iid}#note_{n['id']}"})
    return out


def digest(prev: str, entry: dict) -> str:
    content = {k: v for k, v in entry.items() if k not in _CHAIN}
    return hashlib.sha256((prev + json.dumps(content, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()


def chain(entries: list) -> list:
    prev, out = START, []
    for e in entries:
        e = dict(e, prev=prev)
        e["hash"] = prev = digest(prev, e)
        out.append(e)
    return out


def verify(entries: list) -> int | None:
    """The index of the first entry whose link or hash does not hold, or None when the whole chain holds."""
    prev = START
    for i, e in enumerate(entries):
        if not isinstance(e, dict) or e.get("prev") != prev or e.get("hash") != digest(prev, e):
            return i
        prev = e["hash"]
    return None


def merge(previous: list, fresh: list) -> tuple[list, list]:
    """The previous entries unchanged and in order, then the fresh notes not yet recorded (oldest first); and the recorded
    notes that GitLab now returns edited or not at all."""
    now = {e["note"]: e for e in fresh}
    changed = []
    for e in previous:
        got = now.get(e["note"])
        if got is None:
            changed.append({"note": e["note"], "iid": e["iid"], "what": "not returned now (deleted, or the label was taken off)"})
        elif got["body_sha256"] != e["body_sha256"]:
            changed.append({"note": e["note"], "iid": e["iid"], "what": "edited after it was recorded"})
    seen = {e["note"] for e in previous}
    new = sorted((e for e in fresh if e["note"] not in seen), key=lambda e: (e["at"], e["note"]))
    return chain([{k: v for k, v in e.items() if k not in _CHAIN} for e in previous] + new), changed


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def published(url: str, opener=None):
    """The log this site published last: its entries, [] when there is none yet, or None when it cannot be read. GitLab Pages
    answers a missing file with 404, or, on a site with access control, with a redirect to its sign-in page (projects.gitlab.io/auth)."""
    opener = opener or urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(urllib.request.Request(url, headers={"User-Agent": "itemator-ci"}), timeout=D.TIMEOUT) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404 or (e.code in (301, 302) and (e.headers.get("Location") or "").startswith("https://projects.gitlab.io/auth")):
            return []
        return None
    except Exception:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        return None
    return data


def collect(api: D.Api, project_url: str) -> list:
    mrs = api.pages("merge_requests", D.PAGES, labels=LABEL, state="all", order_by="created_at", sort="asc")
    out = []
    for m in mrs:
        if isinstance(m, dict) and isinstance(m.get("iid"), int):
            out += entries_from(m["iid"], D.notes_of(api, m["iid"])[0], project_url)
    return out


def page(log: dict) -> str:
    e = html.escape
    rows = log["entries"]
    n_items = sum(len(x["items"]) for x in rows)
    out = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
           "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">",
           "<title>Every recorded answer</title><style>body{font:16px/1.5 system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem}"
           "table{border-collapse:collapse;width:100%;font-size:.92rem}td,th{border-bottom:1px solid #ddd;padding:.3rem .4rem;text-align:left;vertical-align:top}"
           ".m{color:#555}code{overflow-wrap:anywhere}.t{overflow-x:auto}</style></head><body>",
           "<h1>Every recorded answer</h1>",
           f"<p>Every answer a person gave to an extra, as the reaction flow summed it up on the merge request: {n_items} "
           f"answer{'' if n_items == 1 else 's'} in {len(rows)} summary note{'' if len(rows) == 1 else 's'}. Each entry carries the SHA-256 of the "
           "one before it, and each build starts from the copy published last, so an entry cannot be changed or removed later without "
           "the chain showing it. Made by the Pages job from GitLab's own notes; nothing here is typed by hand.</p>",
           f"<p class=\"m\">This chain started {e(log['started'])}. Latest hash: <code>{e(log['head'])}</code>. Check a copy yourself: download <a href=\"answers.json\">answers.json</a> and run "
           "<code>python -m itemator.answerlog --verify answers.json</code> from the repository. <a href=\"../\">What shipped</a></p>"]
    if log["changed_after_recorded"]:
        out.append("<h2>Changed after they were recorded</h2><ul>" + "".join(
            f"<li>!{e(str(c['iid']))}, note {e(str(c['note']))}: {e(c['what'])}</li>" for c in log["changed_after_recorded"]) + "</ul>")
    out.append("<div class=\"t\"><table><tr><th>#</th><th>When (UTC)</th><th>Merge request</th><th>Extra</th><th>Answer</th><th>By</th><th>Hash</th></tr>")
    for k, x in enumerate(rows, 1):
        for j, i in enumerate(x["items"]):
            head = (f"<td>{k}</td><td>{e(x['at'][:16].replace('T', ' '))}</td><td><a href=\"{e(x['url'])}\">!{e(str(x['iid']))}</a></td>"
                    if j == 0 else "<td></td><td></td><td></td>")
            tail = f"<td><code>{e(x['hash'][:12])}</code></td>" if j == 0 else "<td></td>"
            out.append(f"<tr>{head}<td><code>{e(D.clean_name(i['name']))}</code></td><td>{e(i['decision'])}</td><td>@{e(i['who'])}</td>{tail}</tr>")
    out.append("</table></div></body></html>")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="itemator.answerlog", description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--verify", metavar="FILE", help="check the chain of a downloaded answers.json and stop")
    ap.add_argument("--api", default=os.environ.get("CI_API_V4_URL", ""))
    ap.add_argument("--project", default=os.environ.get("CI_PROJECT_ID", ""))
    ap.add_argument("--project-url", default=os.environ.get("CI_PROJECT_URL", ""))
    ap.add_argument("--previous", default=(os.environ.get("CI_PAGES_URL", "").rstrip("/") + "/answers/answers.json") if os.environ.get("CI_PAGES_URL") else "")
    ap.add_argument("--out", default="public/answers")
    a = ap.parse_args(argv)
    if a.verify:
        entries = json.loads(pathlib.Path(a.verify).read_text()).get("entries", [])
        bad = verify(entries)
        print(f"itemator answerlog: {len(entries)} entries, chain holds" if bad is None else f"itemator answerlog: chain breaks at entry {bad + 1}")
        return 0 if bad is None else 1
    token = os.environ.get("CI_JOB_TOKEN", "")
    if not (a.api and a.project and a.project_url and a.previous and token):
        print("itemator answerlog: needs CI_API_V4_URL, CI_PROJECT_ID, CI_PROJECT_URL, CI_PAGES_URL and CI_JOB_TOKEN (a CI job); nothing done")
        return 0
    previous = None
    for _ in range(3):                  # a passing network error must not stop the site; a log that cannot be read must not be overwritten
        previous = published(a.previous)
        if previous is not None:
            break
    if previous is None:
        print(f"itemator answerlog: could not read the published log at {a.previous}; not writing a new one over it")
        return 1
    started = previous.get("started") if previous else None
    previous = previous["entries"] if previous else []
    bad = verify(previous)
    if bad is not None:
        print(f"itemator answerlog: the published log's chain breaks at entry {bad + 1}; not building on it")
        return 1
    api = D.Api(a.api, a.project, token)
    entries, changed = merge(previous, collect(api, a.project_url.rstrip("/")))
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log = {"label": LABEL, "generated_at": now, "started": str(started or now),
              "head": entries[-1]["hash"] if entries else START, "entries": entries, "changed_after_recorded": changed,
              "unreadable_requests": api.failures}
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "answers.json").write_text(json.dumps(log, indent=1))
    (out / "index.html").write_text(page(log), encoding="utf-8")
    print(f"itemator answerlog: {len(previous)} kept, {len(entries) - len(previous)} added, {len(changed)} changed after recorded, "
          f"{api.failures} unreadable requests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
