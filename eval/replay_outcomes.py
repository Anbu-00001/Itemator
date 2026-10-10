"""Kill test 1c: what happened upstream to each flagged extra.

Reads the frozen predictions (results/replay_predictions.json, committed in
cf0d762, sha256 checked below) and looks up, for every extra of every flagged
PR, its upstream outcome with read-only GitHub REST GETs (`gh api`), cached
under eval/cache/outcomes/ (gitignored). Writes results/replay_outcomes.json.

One label per extra; the first that applies wins, in this order:
  reverted            a later commit or PR on the default branch reverts this PR
  removed_later       within 90 days of the merge, a later commit removed or undid the extra
  objected_in_review  a human reviewer comment on this PR names the extra or its file and
                      asks to drop, split or justify it (hand-checked, quoted in OBJECTIONS)
  kept                merged, and still present at min(merged_at + 90 days, AS_OF_CAP)
  pr_not_merged       the PR was closed (or is still open) unmerged
  unknown             with a reason

Mechanical presence check, at the as-of commit (the default branch's last
commit at or before min(merged_at + 90 days, AS_OF_CAP)):
  new_dependency       the package name still appears in the manifest
  tests_removed        the deleted test file is still absent
  public_api_removed   no def/class/export of the name in that file
  ci_or_config,
  file_outside_ask     the file still exists and >= 50% of the PR's distinctive added
                       lines (stripped, >= 4 characters) are still in it; a file the
                       PR deleted is still absent
When the check fails, the commits on that path between the merge and the as-of
date are read (patches, at most MAX_PATCHES per path) to find the one commit
that deleted the file, dropped the name, or removed >= 50% of the PR's added
lines. A commit whose message starts with "Revert" and names this PR (number,
title or merge commit) makes the label `reverted`. Reverts after the window are
looked for with two searches per merged PR.

Objections and stated close reasons are judgements. They are recorded by hand
in OBJECTIONS and CLOSE_REASONS after reading the cached comments (`--digest`),
each with the comment URL and a quote of at most 25 words. Bots do not count
as reviewers.

Run from the repository root:
    .venv/bin/python -I eval/replay_outcomes.py            # fetch what is not cached, label
    .venv/bin/python -I eval/replay_outcomes.py --digest   # also print the PR comments
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
PRED = REPO / "results" / "replay_predictions.json"
PRED_SHA256 = "4373e9f61b7b9f1a67365d5c69ec6bf64ee7f522ad0dc44f94713fdbb0c14e41"
OUT = REPO / "results" / "replay_outcomes.json"
CACHE = REPO / "eval" / "cache" / "outcomes"
FILES_CACHE = REPO / "eval" / "cache"          # T1's per-PR file lists (with patches)
DATA = REPO / "data"
MAX_CALLS = 150
MAX_PATCHES = 4
WINDOW = dt.timedelta(days=90)
AS_OF_CAP = dt.datetime(2026, 10, 10, tzinfo=dt.timezone.utc)
COUNTED = ("reverted", "removed_later", "objected_in_review")

# Hand-checked after reading the cached comments (2026-10-10): no human reviewer
# comment names a flagged extra and asks to drop, split or justify it. Key:
# (pr_url, kind, name) -> {"url", "quote"}. Left empty on purpose.
OBJECTIONS: dict[tuple[str, str, str], dict] = {}

# Stated reason for closing unmerged, when there is one. Key: pr_url.
CLOSE_REASONS: dict[str, dict] = {
    "https://github.com/microsoft/retina/pull/1704": {
        "url": "https://github.com/microsoft/retina/pull/1704#issuecomment-3135981851",
        "quote": "Signed PR: https://github.com/microsoft/retina/pull/1783 (superseded: Copilot could not sign "
                 "commits; #1783, merged 2025-07-30, has latency.go only, without test-summary)"},
    "https://github.com/dotnet/sdk/pull/49315": {
        "url": "https://github.com/dotnet/sdk/pull/49315#issuecomment-2966685141",
        "quote": "last human comment, not an explicit close reason: \"I'm not sure if it would fix the actual "
                 "issue ... Wouldn't it need to be fixed in [NuGet.Client]?\""},
}

# The mechanical check said removed_later, but reading the commit shows the PR's
# change was carried forward, not undone. Key: (pr_url, kind, name) -> the
# commit, where the change lives on, and why. The mechanical label is kept in
# the output as `mechanical_label`.
CARRIED_FORWARD: dict[tuple[str, str, str], dict] = {
    ("https://github.com/SwitchbackTech/compass/pull/484", "file_outside_ask", "packages/backend/.env.example"): {
        "url": "https://github.com/KeepSoftwareSimple/compass-calendar/commit/eef599b40277ec9048d5409ad6d095139317cd38",
        "why": "a cleanup commented out every optional EMAILER_ line; the PR's "
               "EMAILER_WAITLIST_INVITE_TAG_ID stays, as '# EMAILER_WAITLIST_INVITE_TAG_ID=...'"},
    ("https://github.com/SwitchbackTech/compass/pull/484", "file_outside_ask",
     "packages/backend/src/__tests__/backend.test.init.js"): {
        "url": "https://github.com/KeepSoftwareSimple/compass-calendar/commit/ac20c640f3f2a80a3a079ee0f00a201fd5dae39a",
        "why": "converted to backend.test.init.ts in a feature commit; the PR's "
               "EMAILER_WAITLIST_INVITE_TAG_ID line is in the .ts file"},
    ("https://github.com/dotnet/fsharp/pull/18584", "file_outside_ask", "src/Compiler/TypedTree/TypedTreeOps.fs"): {
        "url": "https://github.com/dotnet/fsharp/blob/a274432acc830bffeede7a20b9048e34d2a200ff/"
               "src/Compiler/TypedTree/TypedTreeOps.Transforms.fs",
        "why": "TypedTreeOps.fs was split into 7 files (#19521, commit b74a9e15); the PR's CLIEventAttribute "
               "'E:' prefix line is in TypedTreeOps.Transforms.fs (GitHub code search, 1 hit)"},
    ("https://github.com/lingodotdev/lingo.dev/pull/867", "file_outside_ask", ".changeset/few-boxes-sniff.md"): {
        "url": "https://github.com/lingodotdev/lingo.dev/commit/a6e9d2c2cd65c96017434c05a6fdde501e718703",
        "why": "the changesets release bot consumed the note into the changelog ('chore: bump package version', "
               "#869), as it does with every changeset"},
}


def _json_stream(text: str) -> list:
    dec, i, out = json.JSONDecoder(), 0, []
    while i < len(text):
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            break
        value, i = dec.raw_decode(text, i)
        out.append(value)
    return out


class GH:
    """Read-only, cached `gh api` GETs, with a hard call cap."""

    def __init__(self):
        self.calls = 0
        self.errors: list[dict] = []

    def get(self, endpoint: str, params: dict | None = None, raw: bool = False,
            paginate: bool = False) -> dict:
        params = params or {}
        key = json.dumps([endpoint, sorted(params.items()), raw, paginate])
        slug = re.sub(r"[^A-Za-z0-9]+", "_", endpoint)[:90]
        f = CACHE / f"{slug}-{hashlib.sha1(key.encode()).hexdigest()[:10]}.json"
        if f.exists():
            return json.loads(f.read_text())
        if self.calls >= MAX_CALLS:
            raise RuntimeError(f"MAX_CALLS ({MAX_CALLS}) reached at {endpoint}")
        cmd = ["gh", "api", "--method", "GET", endpoint]
        if raw:
            cmd += ["-H", "Accept: application/vnd.github.raw"]
        if paginate:
            cmd += ["--paginate"]
        for k, v in params.items():
            cmd += ["-f", f"{k}={v}"]
        if endpoint.startswith("search/"):
            time.sleep(2.5)                     # search API: 30 requests a minute
        self.calls += 1
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        rec = {"endpoint": endpoint, "params": params}
        if r.returncode != 0:
            err = (r.stderr.strip().splitlines() or ["unknown"])[0][:300]
            rec.update(ok=False, error=err, status=404 if "404" in err else None)
            if rec["status"] != 404:            # transient: do not cache
                self.errors.append(rec)
                return rec
        elif raw:
            rec.update(ok=True, data=r.stdout)
        else:
            pages = _json_stream(r.stdout)
            self.calls += max(0, len(pages) - 1)
            if paginate and all(isinstance(p, list) for p in pages):
                data = [x for p in pages for x in p]
            else:
                data = pages[0] if pages else None
            rec.update(ok=True, data=data)
        CACHE.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(rec))
        return rec


def ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def iso(d: dt.datetime) -> str:
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def lines_of(patch: str | None, sign: str) -> list[str]:
    out = []
    for ln in (patch or "").splitlines():
        if ln.startswith(sign) and not ln.startswith(sign * 3):
            s = ln[1:].strip()
            if len(s) >= 4 and re.search(r"[A-Za-z0-9]", s):
                out.append(s)
    return list(dict.fromkeys(out))


def defines(name: str, text: str) -> bool:
    n = re.escape(name)
    pat = rf"^\s*(async\s+)?def\s+{n}\b|^\s*class\s+{n}\b|^\s*export\s.*\b{n}\b"
    return re.search(pat, text, re.M) is not None


def word_in(name: str, text: str) -> bool:
    return re.search(rf"(?<![\w.-]){re.escape(name)}(?![\w.-])", text) is not None


def presence(extra: dict, pr_file: dict | None, text: str | None) -> tuple[bool, str]:
    """True when the extra is still as the PR left it at the as-of commit."""
    kind, name, path = extra["kind"], extra["name"], extra["path"]
    status = (pr_file or {}).get("status")
    patch = (pr_file or {}).get("patch")
    if kind == "new_dependency":
        if text is None:
            return False, f"{path} no longer exists"
        ok = word_in(name, text)
        return ok, f"'{name}' {'still in' if ok else 'gone from'} {path}"
    if kind == "public_api_removed":
        if text is None:
            return True, f"{path} gone; '{name}' not defined there"
        ok = not defines(name, text)
        return ok, f"'{name}' {'still not defined' if ok else 'defined again'} in {path}"
    if status == "removed":                      # tests_removed, or a file the PR deleted
        ok = text is None
        return ok, f"{path} {'still absent' if ok else 'exists again'}"
    if text is None:
        return False, f"{path} no longer exists"
    adds = lines_of(patch, "+")
    if not adds:
        rems = lines_of(patch, "-")
        if not rems:
            return True, f"{path} exists (the PR's change has no text lines to trace)"
        have = {ln.strip() for ln in text.splitlines()}
        back = sum(x in have for x in rems) / len(rems)
        return back < 0.5, f"{back:.0%} of the PR's {len(rems)} removed lines are back"
    have = {ln.strip() for ln in text.splitlines()}
    frac = sum(a in have for a in adds) / len(adds)
    return frac >= 0.5, f"{frac:.0%} of the PR's {len(adds)} added lines still present"


def undoes(extra: dict, pr_file: dict | None, cfile: dict) -> float:
    """How fully one later commit's change to the file undoes the extra (0..1)."""
    kind, name = extra["kind"], extra["name"]
    status = (pr_file or {}).get("status")
    if kind == "public_api_removed":
        return 1.0 if defines(name, "\n".join(lines_of(cfile.get("patch"), "+"))) else 0.0
    if cfile.get("status") == "removed" and status != "removed":
        return 1.0
    if status == "removed" or kind == "tests_removed":
        return 1.0 if cfile.get("status") == "added" else 0.0
    c_add, c_rem = lines_of(cfile.get("patch"), "+"), lines_of(cfile.get("patch"), "-")
    if kind == "new_dependency":
        return 1.0 if any(word_in(name, x) for x in c_rem) and not any(word_in(name, x) for x in c_add) else 0.0
    adds = lines_of((pr_file or {}).get("patch"), "+")
    if not adds:
        return 0.0
    rem = set(c_rem)
    return sum(a in rem for a in adds) / len(adds)


def names_pr(msg: str, number: int, title: str, sha: str) -> bool:
    m = msg.lower()
    return (f"#{number}" in m or (title and title.lower()[:60] in m)
            or (sha and sha[:7] in m))


def pr_ids(urls: list[str]) -> dict[str, int]:
    import duckdb
    con = duckdb.connect()
    con.execute("SET memory_limit='1GB'; SET threads=2;")
    q = ", ".join("?" for _ in urls)
    rows = con.execute(f"SELECT html_url, id FROM '{DATA / 'pull_request.parquet'}' "
                       f"WHERE html_url IN ({q})", urls).fetchall()
    return {u: i for u, i in rows}


def is_bot(user: dict | None) -> bool:
    u = user or {}
    return u.get("type") == "Bot" or str(u.get("login", "")).endswith("[bot]")


def comments_of(gh: GH, o: str, r: str, n: int) -> list[dict]:
    out = []
    for kind, ep in (("review_comment", f"repos/{o}/{r}/pulls/{n}/comments"),
                     ("review", f"repos/{o}/{r}/pulls/{n}/reviews"),
                     ("issue_comment", f"repos/{o}/{r}/issues/{n}/comments")):
        rec = gh.get(ep, {"per_page": "100"}, paginate=True)
        for c in rec.get("data") or []:
            out.append({"kind": kind, "user": (c.get("user") or {}).get("login"),
                        "bot": is_bot(c.get("user")), "path": c.get("path"),
                        "url": c.get("html_url"), "state": c.get("state"),
                        "at": c.get("created_at") or c.get("submitted_at"),
                        "body": c.get("body") or ""})
    return out


def find_reverts(gh: GH, o: str, r: str, n: int, title: str, sha: str, merged: str) -> list[dict]:
    hits = []
    rec = gh.get("search/issues", {"q": f'repo:{o}/{r} is:pr in:title revert created:>={merged[:10]}',
                                   "per_page": "100"})
    for it in (rec.get("data") or {}).get("items", []):
        t = it.get("title", "")
        b = it.get("body") or ""
        if t.lower().startswith("revert") and (names_pr(t, n, title, sha) or f"#{n}" in b):
            hits.append({"url": it["html_url"], "title": t, "merged": bool((it.get("pull_request") or {}).get("merged_at"))})
    rec = gh.get("search/commits", {"q": f'repo:{o}/{r} "This reverts commit {sha}"'})
    for it in (rec.get("data") or {}).get("items", []):
        msg = (it.get("commit") or {}).get("message", "")
        if sha in msg:
            hits.append({"url": it["html_url"], "title": msg.splitlines()[0], "merged": True})
    return hits


def main() -> int:
    digest = "--digest" in sys.argv
    if hashlib.sha256(PRED.read_bytes()).hexdigest() != PRED_SHA256:
        print("predictions file changed since cf0d762; refusing to run", file=sys.stderr)
        return 2
    pred = json.loads(PRED.read_text())
    flagged = [p for p in pred["prs"] if p["extras"]]
    ids = pr_ids([p["pr_url"] for p in flagged])
    gh = GH()
    prs_out, labels = [], {}
    for p in flagged:
        parts = p["pr_url"].split("/")
        o, r, n = parts[3], parts[4], int(parts[6])
        files = json.loads((FILES_CACHE / f"{ids[p['pr_url']]}.json").read_text())["files"]
        by_path = {f["filename"]: f for f in files}
        meta = gh.get(f"repos/{o}/{r}/pulls/{n}")["data"]
        comments = comments_of(gh, o, r, n)
        merged_at = meta.get("merged_at")
        default = meta["base"]["repo"]["default_branch"]
        base_ref = meta["base"]["ref"]
        title = meta.get("title") or ""
        author = (meta.get("user") or {}).get("login")
        row = {"pr_url": p["pr_url"], "agent": p["agent"], "title": title, "author": author,
               "state": meta.get("state"), "merged_at": merged_at, "closed_at": meta.get("closed_at"),
               "base_ref": base_ref, "default_branch": default,
               "comments": {"total": len(comments), "human": sum(not c["bot"] for c in comments)},
               "extras": []}
        as_of_sha, reverts, texts, path_commits = None, [], {}, {}
        if merged_at:
            sha = meta.get("merge_commit_sha") or ""
            row["merge_commit_sha"] = sha
            as_of = min(ts(merged_at) + WINDOW, AS_OF_CAP)
            row["as_of"] = iso(as_of)
            head = gh.get(f"repos/{o}/{r}/commits", {"sha": default, "until": iso(as_of), "per_page": "1"})
            as_of_sha = (head.get("data") or [{}])[0].get("sha")
            row["as_of_sha"] = as_of_sha
            fo, fr = meta["base"]["repo"]["full_name"].split("/")   # search needs the current name
            reverts = find_reverts(gh, fo, fr, n, title, sha, merged_at)
            row["revert_hits"] = reverts
        elif p["pr_url"] in CLOSE_REASONS:
            row["close_reason"] = CLOSE_REASONS[p["pr_url"]]
        for e in p["extras"]:
            out = {"kind": e["kind"], "path": e["path"], "name": e["name"]}
            pr_file = by_path.get(e["path"])
            obj = OBJECTIONS.get((p["pr_url"], e["kind"], e["name"]))
            label = evidence = detail = None
            if merged_at and base_ref != default:
                label, evidence = "unknown", p["pr_url"]
                detail = f"merged into {base_ref}, not the default branch {default}"
            elif merged_at:
                good_revert = [h for h in reverts if h["merged"]]
                if good_revert:
                    label, evidence, detail = "reverted", good_revert[0]["url"], good_revert[0]["title"]
                else:
                    if e["path"] not in texts:
                        rec = gh.get(f"repos/{o}/{r}/contents/{e['path']}", {"ref": as_of_sha}, raw=True)
                        texts[e["path"]] = rec.get("data") if rec.get("ok") else None
                    ok, detail = presence(e, pr_file, texts[e["path"]])
                    blob = f"https://github.com/{o}/{r}/blob/{as_of_sha}/{e['path']}"
                    if ok:
                        label, evidence = "kept", blob
                    else:
                        if e["path"] not in path_commits:
                            rec = gh.get(f"repos/{o}/{r}/commits",
                                         {"sha": default, "path": e["path"], "since": merged_at,
                                          "until": row["as_of"], "per_page": "100"})
                            later = [c for c in rec.get("data") or [] if c["sha"] != sha]
                            later.reverse()                      # oldest first
                            hot = re.compile(r"revert|remov|delet|undo|restor|roll ?back|drop|"
                                             + re.escape(e["name"].split("/")[-1].lower()))
                            later.sort(key=lambda c: not hot.search(c["commit"]["message"].lower()))
                            path_commits[e["path"]] = later
                        best = (0.0, None)
                        for c in path_commits[e["path"]][:MAX_PATCHES]:
                            full = gh.get(f"repos/{o}/{r}/commits/{c['sha']}").get("data") or {}
                            for cf in full.get("files", []):
                                if e["path"] in (cf.get("filename"), cf.get("previous_filename")):
                                    score = undoes(e, pr_file, cf)
                                    if score > best[0]:
                                        best = (score, full)
                        if best[1] is not None and best[0] >= 0.5:
                            c = best[1]
                            msg = c["commit"]["message"].splitlines()[0]
                            if msg.lower().startswith("revert") and names_pr(c["commit"]["message"], n, title, sha):
                                label = "reverted"
                            else:
                                label = "removed_later"
                            evidence = c["html_url"]
                            detail = f"{detail}; {msg[:120]} ({best[0]:.0%} undone in this commit)"
                        else:
                            label, evidence = "unknown", blob
                            detail = (f"{detail}, but no single commit of the "
                                      f"{len(path_commits[e['path']])} on this path in the window undid it "
                                      f"(read {min(MAX_PATCHES, len(path_commits[e['path']]))})")
            cf = CARRIED_FORWARD.get((p["pr_url"], e["kind"], e["name"]))
            if cf and label == "removed_later":
                out["mechanical_label"], out["mechanical_evidence"] = label, evidence
                label, evidence = "kept", cf["url"]
                detail = f"hand-checked: {cf['why']} (mechanical: {detail})"
            if obj and label not in ("reverted", "removed_later"):
                out["also"] = [label] if label else []
                label, evidence, detail = "objected_in_review", obj["url"], obj["quote"]
            if label is None:
                label = "pr_not_merged"
                cr = CLOSE_REASONS.get(p["pr_url"])
                evidence = cr["url"] if cr else p["pr_url"]
                detail = (cr["quote"] if cr else "no stated reason found") + f" (state: {meta.get('state')})"
            out.update(label=label, evidence_url=evidence, detail=detail)
            labels[label] = labels.get(label, 0) + 1
            row["extras"].append(out)
        if digest:
            print(f"\n=== {p['pr_url']}  merged={bool(merged_at)} state={meta.get('state')} author={author}")
            print("    extras:", "; ".join(f"{x['kind']}:{x['name']}" for x in row["extras"]))
            for c in comments:
                if c["bot"] or c["user"] == author:
                    continue
                body = re.sub(r"\s+", " ", c["body"])[:400]
                print(f"  - [{c['kind']}] {c['user']} {c['path'] or ''} {c['url']}\n      {body}")
        prs_out.append(row)
    count = sum(labels.get(k, 0) for k in COUNTED)
    mech = sum(1 for x in prs_out for e in x["extras"]
               if e.get("mechanical_label", e["label"]) in COUNTED)
    summary = {
        "predictions": str(PRED.relative_to(REPO)), "predictions_sha256": PRED_SHA256,
        "flagged_prs": len(flagged), "extras": sum(len(p["extras"]) for p in flagged),
        "labels": dict(sorted(labels.items())),
        "kill_test_1c": {"counted_labels": list(COUNTED), "count": count, "threshold": ">= 3",
                         "pass": count >= 3,
                         "count_before_hand_check": mech},
        "failed_calls": [{"endpoint": r["endpoint"], "params": r["params"], "error": r["error"]}
                         for r in gh.errors],
        "prs_merged": sum(1 for x in prs_out if x["merged_at"]),
        "github_api_calls_this_run": gh.calls,
        "window_days": WINDOW.days, "as_of_cap": iso(AS_OF_CAP),
    }
    OUT.write_text(json.dumps({"summary": summary, "prs": prs_out}, indent=1, sort_keys=False) + "\n")
    for x in prs_out:
        for e in x["extras"]:
            print(f"{e['label']:<19} {e['kind']:<18} {e['name'][:60]:<60} {e['evidence_url']}")
    print(f"labels: {summary['labels']}")
    print(f"kill test 1c: {count} extras reverted, removed_later or objected_in_review "
          f"(pass at >= 3) -> {'PASS' if count >= 3 else 'FAIL'}; "
          f"before the hand check: {mech}")
    for r in gh.errors:
        print(f"failed call: {r['endpoint']} {r['params']} {r['error']}")
    print(f"GitHub API calls this run: {gh.calls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
