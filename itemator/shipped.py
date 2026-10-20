"""The deployment page: for each deployment of an environment, which merge requests shipped in it, which extras each one had, and who named
each. Reads deployments and merge requests with the CI job token (nothing is written to GitLab); writes `public/index.html` (a static page for
GitLab Pages) and `shipped.json`.

A deployment's merge requests come from GitLab's own list (`deployments/:id/merge_requests`) when it has one; GitLab's documentation says that list
is not always filled, so otherwise they are the merge requests merged into the target branch between the previous successful deployment and this
one (the same window code as the decision log). The page says which of the two it used for each deployment."""
from __future__ import annotations

import argparse
import datetime
import html
import json
import os
import pathlib
import sys

from itemator import decisions as D

DEPLOYMENTS = 8        # successful deployments shown


def deployments(api: D.Api, environment: str) -> list:
    """The latest successful deployments of the environment, newest first (one more than shown: the oldest only gives a window start)."""
    got = api.get("deployments", environment=environment, status="success", order_by="created_at", sort="desc", per_page=DEPLOYMENTS + 1)
    return [d for d in got if isinstance(d, dict) and isinstance(d.get("id"), int)] if isinstance(got, list) else []


def _from_gitlab_list(api: D.Api, deployment_id: int) -> list | None:
    got = api.get(f"deployments/{deployment_id}/merge_requests", missing_ok=True, per_page=100)
    mrs = [m for m in got if isinstance(m, dict) and isinstance(m.get("iid"), int)] if isinstance(got, list) else []
    return mrs or None


def shipped(api: D.Api, target: str, deployment: dict, previous: dict | None) -> dict:
    """The entries for one deployment and where the list came from."""
    until = deployment.get("created_at") or ""
    since = (previous or {}).get("created_at") or "1970-01-01T00:00:00Z"
    mrs = _from_gitlab_list(api, deployment["id"])
    if mrs is not None:
        entries = [D.entry_of(api, m) for m in mrs]
        source = "GitLab's list for the deployment"
    else:
        entries = D.collect(api, target, since, until)
        source = "merge requests merged since the previous deployment"
    return {"deployment": deployment["id"], "iid": deployment.get("iid"), "created_at": until, "ref": D.clean((deployment.get("ref") or ""), 60),
            "sha": str((deployment.get("sha") or ""))[:12], "source": source, "stats": D.stats(entries), "weight": D.weights(entries),
            "merge_requests": entries}


def build(api: D.Api, environment: str, target: str) -> dict:
    deps = deployments(api, environment)
    rows = [shipped(api, target, d, deps[i + 1] if i + 1 < len(deps) else None) for i, d in enumerate(deps[:DEPLOYMENTS])]
    return {"environment": D.clean(environment, 60), "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "deployments": rows, "unreadable_requests": api.failures}


def _weight_words(x: dict) -> str:
    return f"{'at least' if x['at_least'] else 'about'} {D.W.human(x['bytes'])}"


def _item(i: dict) -> str:
    e = html.escape
    w = f" ({e(_weight_words(i['weight']))} on every fresh install)" if i.get("weight") else ""
    return f"<code>{e(i['name'])}</code>{w} {e(i['decision'])} by @{e(i['who'])}"


def page(report: dict) -> str:
    """A static HTML page; every string that came from GitLab is escaped."""
    e = html.escape
    out = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
           "<title>What shipped</title><style>body{font:16px/1.5 system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem}"
           "h2{margin-top:2rem}li{margin:.3rem 0}.m{color:#555}</style></head><body>",
           f"<h1>What shipped to {e(report['environment'])}</h1>",
           "<p>Each deployment, the merge requests in it, the extras each had beyond its issue, and who typed a name for each. "
           "Made by Itemator's deployment job from GitLab's own records; nothing here is typed by hand.</p>"]
    if not report["deployments"]:
        out.append("<p>No successful deployment yet.</p>")
    removed = [d["weight"]["removed"] for d in report["deployments"] if d.get("weight") and d["weight"]["removed"]["dependencies"]]
    if removed:
        total = {"bytes": sum(x["bytes"] for x in removed), "at_least": any(x["at_least"] for x in removed)}
        n = sum(x["dependencies"] for x in removed)
        out.append(f"<p><strong>Kept out by a reviewer's <code>remove</code>: {e(_weight_words(total))} on every fresh install</strong>, "
                   f"{n} new {'dependency' if n == 1 else 'dependencies'} with what {'it' if n == 1 else 'they'} would have brought along, "
                   "as the job measured each before the merge (the same measure for what was kept, below). An upper bound: some of those "
                   "packages may already be installed for another reason.</p>")
    if report["deployments"]:
        merged = [m for d in report["deployments"] for m in d["merge_requests"]]
        n = len(report["deployments"])
        line = D.unanswered_line(D.stats(merged))
        out.append(f"<p><strong>In the {n} deployment{'' if n == 1 else 's'} below, {e(line[0].lower() + line[1:])}</strong> "
                   "Itemator keeps, moves or removes nothing until a person replies, so this is what went in without one.</p>")
    for d in report["deployments"]:
        s = d["stats"]
        out.append(f"<h2>Deployment {e(str(d['iid'] or d['deployment']))} <span class=\"m\">{e(d['created_at'])}, commit {e(d['sha'])}</span></h2>")
        out.append(f"<p class=\"m\">{s['merge_requests']} merge request{'' if s['merge_requests'] == 1 else 's'}, {s['extras']} extras decided "
                   f"({s['kept']} kept, {s['dismissed']} dismissed, {s['moved']} moved, {s['removed']} removed). List: {e(d['source'])}.</p><ul>")
        for m in d["merge_requests"]:
            what = "; ".join(_item(i) for i in m["extras"])
            if m["extras"]:
                tail = what
            elif m.get("unanswered"):
                tail = "<strong>merged without a recorded answer</strong>: " + ", ".join(f"<code>{e(n)}</code>" for n in m["unanswered"])
            else:
                tail = "no extras" if m.get("unanswered") == [] else "could not tell (no job report left, or a record GitLab did not return)"
            out.append(f"<li>!{e(str(m['iid']))} {e(m['title'])}: {tail}</li>")
        out.append("</ul>")
    out.append("<p class=\"m\">Merge requests merged into the default branch are listed with the extras they had. A commit pushed straight to the default branch is a deployment too, but it has no merge request, so none is listed for it.</p>")
    out.append("</body></html>")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Write the deployment page page.")
    ap.add_argument("--api", default=os.environ.get("CI_API_V4_URL", ""))
    ap.add_argument("--project", default=os.environ.get("CI_PROJECT_ID", ""))
    ap.add_argument("--environment", default=os.environ.get("CI_ENVIRONMENT_NAME", "production"))
    ap.add_argument("--target", default=os.environ.get("CI_DEFAULT_BRANCH", "main"))
    ap.add_argument("--out", default="public")
    a = ap.parse_args(argv)
    token = os.environ.get("CI_JOB_TOKEN", "")
    if not (a.api and a.project and token):
        print("itemator shipped: needs CI_API_V4_URL, CI_PROJECT_ID and CI_JOB_TOKEN (a CI job); nothing done")
        return 0
    api = D.Api(a.api, a.project, token)
    report = build(api, a.environment, a.target)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page(report))
    (out / "shipped.json").write_text(json.dumps(report, indent=1))
    n = sum(d["stats"]["merge_requests"] for d in report["deployments"])
    print(f"itemator shipped: {len(report['deployments'])} deployments, {n} merge requests, {api.failures} unreadable requests"
          f"{(' (' + '; '.join(api.errors[:3]) + ')') if api.errors else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
