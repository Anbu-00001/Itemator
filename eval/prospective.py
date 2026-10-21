"""A prospective, registered test (eval/prospective_rubric.json): coding-agent pull requests open on GitHub now, what the
frozen rules (extras v6) list for each, sealed before any outcome exists; on 2026-10-25 the outcome is read. Read-only:
GET requests through `gh api`; nothing is posted. Comment text, issue text and patches stay in eval/cache/ (gitignored).

usage (repository root):
    python3 eval/prospective.py sample    # searches GitHub, writes results/prospective_v1_sealed.json, prints its SHA-256
    python3 eval/prospective.py read      # on 2026-10-25 only: writes results/prospective_v1_read.json"""
from __future__ import annotations

import argparse, collections, hashlib, json, pathlib, re, subprocess, sys, time, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))
from itemator import ci as CI  # noqa: E402
from itemator import extras as X  # noqa: E402
import aidev_recall as A  # noqa: E402

SEALED = ROOT / "results" / "prospective_v1_sealed.json"
READ = ROOT / "results" / "prospective_v1_read.json"
SENTENCES = ROOT / "eval" / "prospective_sentences.json"       # committed before the read; read() fills one in
SENTENCES_SEAL = ROOT / "results" / "prospective_v1_sentences_sealed.json"   # the sentences' hash, written once approved
README = ROOT / "README.md"
NOT_READ = "- **The forward test is not read yet.**"
CACHE = ROOT / "eval" / "cache" / "github"
SEED = "itemator-prospective-v1"
N, PER_AGENT, MAX_FILES = 60, 10, 300
DAYS = ("2026-10-19", "2026-10-20", "2026-10-21")
READ_ON = "2026-10-25"
RULES = 6
AGENTS = ("copilot", "devin", "jules", "cursor", "claude_code", "codex")    # the rubric's order: first match wins
QUERIES = (("copilot", "author:app/copilot-swe-agent"), ("devin", "author:app/devin-ai-integration"),
           ("jules", "author:app/google-labs-jules"), ("cursor", "author:app/cursor"), ("claude_code", "author:app/claude"),
           ("claude_code", '"Generated with Claude Code" in:body'), ("codex", '"Codex Task" in:body'))
_LOGINS = {"copilot": {"copilot", "copilot-swe-agent[bot]"}, "devin": {"devin-ai-integration[bot]"},
           "jules": {"google-labs-jules[bot]"}, "cursor": {"cursor[bot]"}, "claude_code": {"claude[bot]"}}
_CLAUDE_BODY = re.compile(r"Generated with \[?Claude Code\]?", re.I)
_CLOSING_WORD = r"\b(?:clos(?:e|es|ed|ing)|fix(?:es|ed|ing)?|resolv(?:e|es|ed|ing)|implement(?:s|ed|ing)?)\b:?\s+"
_OBJECTION = re.compile(r"\b(?:remove|removed|removing|unnecessary|unneeded|needed|necessary|why|revert|reverted|unrelated|"
                        r"delete|drop|out of scope|not needed|don't need|do not need|shouldn't be|should not be)\b", re.I)


# ---------------------------------------------------------------- pure parts (tests/test_prospective.py)

def order_key(url: str) -> str:
    return hashlib.sha256(f"{SEED}:{url}".encode()).hexdigest()


def pr_parts(url: str) -> tuple[str, str, int]:
    owner, repo, kind, num = url.rstrip("/").split("github.com/", 1)[1].split("/")[:4]
    assert kind == "pull", url
    return owner, repo, int(num)


def agent_of(item: dict) -> str | None:
    """The agent, confirmed from the item itself (author login or body phrase), first in AGENTS order; None if none."""
    login = ((item.get("user") or {}).get("login") or "").lower()
    body = item.get("body") or ""
    for a in AGENTS:
        if login in _LOGINS.get(a, ()):
            return a
        if a == "claude_code" and _CLAUDE_BODY.search(body):
            return a
        if a == "codex" and "Codex Task" in body and "chatgpt.com/codex" in body:
            return a
    return None


def issue_ref(body: str | None, owner: str, repo: str) -> int | None:
    """The first same-repository issue after a closing word, in text order: `#n`, or that repository's /issues/<n> URL."""
    body = body or ""
    url = re.compile(_CLOSING_WORD + r"https?://github\.com/" + re.escape(owner) + "/" + re.escape(repo) + r"/issues/(\d+)\b", re.I)
    found = [(m.start(), int(re.search(r"#(\d+)", m.group(1)).group(1))) for m in CI._CLOSING.finditer(body)]
    found += [(m.start(), int(m.group(1))) for m in url.finditer(body)]
    return min(found)[1] if found else None


def quick_skip(item: dict) -> str | None:
    """Reasons a search hit is out before any further request."""
    if item.get("state") != "open":
        return "not_open"
    if (item.get("title") or "").startswith("[WIP]"):
        return "wip_title"
    if agent_of(item) is None:
        return "agent_not_confirmed"
    owner, repo, _ = pr_parts(item["html_url"])
    if issue_ref(item.get("body"), owner, repo) is None:
        return "no_same_repo_closing_ref"
    return None


def select(items: list, evaluate, n: int = N, per_agent: int = PER_AGENT) -> tuple[list, collections.Counter]:
    """Walk `items` in order_key order; keep at most 1 per repository and `per_agent` per agent; stop at n. Then, if short,
    walk the hits skipped only for the agent cap, with no agent cap. `evaluate(item)` -> (record, None) or (None, reason)."""
    items = sorted({i["html_url"]: i for i in items}.values(), key=lambda i: order_key(i["html_url"]))
    kept, repos, agents, skipped, held = [], set(), collections.Counter(), collections.Counter(), []

    def walk(seq, cap):
        for it in seq:
            if len(kept) >= n:
                return
            why = quick_skip(it)
            o, r, _ = pr_parts(it["html_url"])
            if why is None and f"{o}/{r}".lower() in repos:
                why = "repo_already_kept"
            if why is None and cap and agents[agent_of(it)] >= per_agent:
                held.append(it)
                continue
            if why is None:
                rec, why = evaluate(it)
                if rec is not None:
                    kept.append(rec)
                    repos.add(f"{o}/{r}".lower())
                    agents[rec["agent"]] += 1
                    continue
            skipped[why] += 1

    walk(items, True)
    rest, held[:] = list(held), []
    walk(rest, False)
    return kept, skipped


def record(item: dict, issue_no: int, pr: dict, files: list, analysis) -> dict | None:
    """The sealed entry: no outcome, no text. None when the rules list nothing."""
    paths = [f["filename"] for f in files]
    listed = [p for p in paths if A.listed(analysis.extras, p)]
    if not listed:
        return None
    extras = []
    for e in analysis.extras:
        covers = sorted(p for p in paths if A.listed([e], p))
        extras.append({"kind": e.kind, "path": e.path, "name": e.name, "files": covers})
    return {"url": item["html_url"], "created_at": item["created_at"], "agent": agent_of(item), "issue": issue_no,
            "head_sha": (pr.get("head") or {}).get("sha"), "files": paths, "listed_paths": listed, "extras": extras}


def cases_sha256(prs: list) -> str:
    return hashlib.sha256(json.dumps(prs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _norm(c: dict) -> dict:
    """A review comment, review or conversation comment -> {login, type, created_at, body, path}."""
    u = c.get("user") or {}
    return {"login": u.get("login") or "", "type": u.get("type") or "", "body": (c.get("body") or "").replace("\u2019", "'"),
            "created_at": c.get("created_at") or c.get("submitted_at") or "", "path": c.get("path")}


def names_file(text: str, path: str, all_paths: list) -> bool:
    if path.lower() in text.lower():
        return True
    base = path.rsplit("/", 1)[-1]
    if sum(p.rsplit("/", 1)[-1] == base for p in all_paths) != 1:
        return False
    return re.search(r"(?<![\w.\-/])" + re.escape(base) + r"(?![\w\-])", text, re.I) is not None


def objected(path: str, all_paths: list, comments: list, pr_author: str, pr_created_at: str) -> bool:
    """The rubric's mechanical rule. `comments`: raw API objects (inline, reviews, conversation) in any order."""
    for c in map(_norm, comments):
        if c["type"] != "User" or c["login"].lower() == (pr_author or "").lower() or c["login"].endswith("[bot]"):
            continue
        if c["created_at"] and c["created_at"] < pr_created_at:
            continue
        if not _OBJECTION.search(c["body"]):
            continue
        if c["path"] == path or (c["path"] is None and names_file(c["body"], path, all_paths)):
            return True
    return False


def state_outcome(pr: dict, files: list, path: str) -> str:
    if pr.get("state") == "closed" and not pr.get("merged"):
        return "closed_unmerged"
    if not any(f.get("filename") == path or f.get("previous_filename") == path for f in files):
        return "removed"
    return "landed" if pr.get("merged") else "still_open_with_file"


def outcomes(sealed_pr: dict, pr: dict, files: list, comments: list) -> list[dict]:
    """One row per file recorded at sampling: listed or not, objected, state outcome."""
    paths = sealed_pr["files"]
    author = (pr.get("user") or {}).get("login") or ""
    kinds = {p: e["kind"] for e in sealed_pr["extras"] for p in e["files"]}
    out = []
    for p in paths:
        st = state_outcome(pr, files, p)
        ob = objected(p, paths, comments, author, sealed_pr["created_at"])
        out.append({"pr": sealed_pr["url"], "agent": sealed_pr["agent"], "path": p, "listed": p in sealed_pr["listed_paths"],
                    "kind": kinds.get(p), "objected": ob, "state": st, "silent_landing": st == "landed" and not ob})
    return out


def _counts(rows: list) -> dict:
    st = collections.Counter(r["state"] for r in rows)
    caught = sum(1 for r in rows if r["objected"] or r["state"] == "removed")
    return {"files": len(rows), "objected": sum(r["objected"] for r in rows), "removed": st["removed"],
            "landed": st["landed"], "closed_unmerged": st["closed_unmerged"],
            "still_open_with_file": st["still_open_with_file"], "silent_landing": sum(r["silent_landing"] for r in rows),
            "objected_or_removed": caught, "share_objected_or_removed": round(caught / len(rows), 4) if rows else None,
            "wilson95": A.G.wilson(caught, len(rows)) if rows else None}


def few_listed(rows: list) -> dict:
    """Amendment 2: listed against unlisted files inside pull requests with 1 to 10 listed files (no mass event)."""
    per = collections.Counter(r["pr"] for r in rows if r["listed"])
    keep = [r for r in rows if 1 <= per[r["pr"]] <= 10]
    return {"pull_requests": len({r["pr"] for r in keep}), "listed": _counts([r for r in keep if r["listed"]]),
            "unlisted": _counts([r for r in keep if not r["listed"]])}


def summarize(rows: list, prs: list) -> dict:
    """`prs`: per sealed pull request {url, unreadable, state?, merged?, added_after_sampling?}."""
    read = [p for p in prs if not p.get("unreadable")]
    st = collections.Counter("closed_unmerged" if p["state"] == "closed" and not p["merged"] else
                             "merged" if p["merged"] else "open" for p in read)
    listed = [r for r in rows if r["listed"]]
    in_merged = [r for r in listed if r["state"] == "landed"]
    return {"pull_requests_sealed": len(prs), "unreadable": len(prs) - len(read), "readable": len(read),
            "open": st["open"], "merged": st["merged"], "closed_unmerged": st["closed_unmerged"],
            "files_added_after_sampling": sum(p.get("added_after_sampling", 0) for p in read),
            "listed": _counts(listed), "unlisted": _counts([r for r in rows if not r["listed"]]),
            "pull_requests_with_a_listed_file_objected_or_removed":
                len({r["pr"] for r in listed if r["objected"] or r["state"] == "removed"}),   # amendment 1
            "pull_requests_with_a_listed_file": len({r["pr"] for r in listed}),
            "share_landed_silently_of_listed_landed": round(sum(r["silent_landing"] for r in in_merged) / len(in_merged), 4)
            if in_merged else None,
            "in_pull_requests_with_1_to_10_listed_files": few_listed(rows),                     # amendment 2
            "by_agent": {a: _counts([r for r in listed if r["agent"] == a]) for a in sorted({r["agent"] for r in listed})},
            "by_kind": {k: _counts([r for r in listed if r["kind"] == k]) for k in sorted({str(r["kind"]) for r in listed})}}


def _pct(k: int, n: int) -> int:
    return round(100 * k / n) if n else 0


def values(summary: dict, read_on: str) -> dict:
    """The counts the sentences are filled in with; read() stores them as `counts` so the README can cite each one."""
    listed, unlisted = summary["listed"], summary["unlisted"]
    k, n, ku, nu = listed["objected_or_removed"], listed["files"], unlisted["objected_or_removed"], unlisted["files"]
    return {"read_on": read_on, "decided": summary["merged"] + summary["closed_unmerged"], "readable": summary["readable"],
            "k": k, "n": n, "p": _pct(k, n), "ku": ku, "nu": nu, "pu": _pct(ku, nu), "landed": listed["landed"],
            "silent": listed["silent_landing"], "kp": summary["pull_requests_with_a_listed_file_objected_or_removed"],
            "np": summary["pull_requests_with_a_listed_file"]}


def fill(rules: dict, band: str, v: dict) -> str:
    text = rules["bands"][band].format(**v)
    return text if band == "early" else text + rules["misses"].format(**v)


def sentence(summary: dict, read_on: str, rules: dict) -> tuple[str, str]:
    """(band, text): the committed sentence for this result, by the committed rule, with the counts filled in."""
    listed, unlisted = summary["listed"], summary["unlisted"]
    k, n, ku, nu = listed["objected_or_removed"], listed["files"], unlisted["objected_or_removed"], unlisted["files"]
    decided = summary["merged"] + summary["closed_unmerged"]
    kp, np_ = summary["pull_requests_with_a_listed_file_objected_or_removed"], summary["pull_requests_with_a_listed_file"]
    if decided < rules["min_decided"]:
        band = "early"
    elif k == 0:
        band = "none"
    elif k < rules["min_hits"] or kp < rules["min_hit_prs"]:
        band = "too_few"
    elif k * nu > ku * n:                     # k/n > ku/nu without rounding
        band = "ahead"
    else:
        band = "not_ahead"
    return band, fill(rules, band, values(summary, read_on))


def readme_line(rules: dict, band: str, v: dict) -> str:
    """The README bullet for the read: the same sentence, each count tagged with where it comes from (hardcode audit)."""
    cite = {key: (val if key == "read_on" else f"{val} <!-- from: results/{READ.name}:counts.{key} -->") for key, val in v.items()}
    return f"- **The forward test, read on {v['read_on']}.** " + fill(rules, band, cite)


def with_read(readme: str, line: str) -> str:
    """Swap the one 'not read yet' bullet for the read's bullet; the placement rule allows no other spot."""
    rows = readme.split("\n")
    hits = [i for i, r in enumerate(rows) if r.startswith(NOT_READ)]
    if len(hits) != 1:
        raise ValueError(f"expected one '{NOT_READ}' line in the README, found {len(hits)}")
    rows[hits[0]] = line
    return "\n".join(rows)


def frozen_on(sha256: str) -> str:
    """The day the sentences were sealed; raises if they changed since, so a reworded sentence cannot be read out."""
    seal = json.loads(SENTENCES_SEAL.read_text())["summary"]
    if seal["predictions_sha256"] != sha256:
        raise ValueError("the sentences changed after they were sealed")
    return seal["frozen_on"]


def seal_sentences() -> int:
    """Pin the approved sentences: read() refuses to run if they change after this."""
    h = hashlib.sha256(SENTENCES.read_bytes()).hexdigest()
    SENTENCES_SEAL.write_text(json.dumps({"summary": {"predictions": f"eval/{SENTENCES.name}", "predictions_sha256": h,
                                                      "frozen_on": time.strftime("%Y-%m-%d", time.localtime())}}, indent=1) + "\n")
    print(h)
    return 0


# ---------------------------------------------------------------- GitHub (GET only, cached)

def gh(path: str, tag: str, retries: int = 4):
    """GET `path` through `gh api`, cached under eval/cache/github/<tag>/ (the read uses its own tag, never the sample's)."""
    f = CACHE / tag / (hashlib.sha256(path.encode()).hexdigest() + ".json")
    if f.exists():
        return json.loads(f.read_text())
    last = ""
    for i in range(retries):
        r = subprocess.run(["gh", "api", "-X", "GET", path], capture_output=True, text=True, timeout=90)
        if r.returncode == 0:
            data = json.loads(r.stdout)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(data))
            return data
        last = (r.stderr or r.stdout).strip()[:200]
        if "404" in last or "410" in last or "422" in last:
            break
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"{path}: {last}")


def all_pages(path: str, tag: str, cap: int = 30) -> list:
    out = []
    for page in range(1, cap + 1):
        chunk = gh(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}", tag)
        out += chunk
        if len(chunk) < 100:
            break
    return out


def search(tag: str) -> tuple[list, list]:
    items, log = [], []
    for agent, qual in QUERIES:
        for day in DAYS:
            q = f"is:pr is:public is:open linked:issue created:{day} {qual}"
            for page in (1, 2):
                path = "search/issues?" + urllib.parse.urlencode(
                    {"q": q, "sort": "created", "order": "desc", "per_page": 100, "page": page})
                cached = (CACHE / tag / (hashlib.sha256(path.encode()).hexdigest() + ".json")).exists()
                res = gh(path, tag)
                if not cached:
                    time.sleep(2.5)
                items += res.get("items", [])
                if page == 1:
                    log.append({"agent": agent, "query": q, "total_count": res.get("total_count")})
                if len(res.get("items", [])) < 100:
                    break
    return items, log


def evaluate(item: dict, tag: str):
    owner, repo, n = pr_parts(item["html_url"])
    no = issue_ref(item.get("body"), owner, repo)
    try:
        issue = gh(f"repos/{owner}/{repo}/issues/{no}", tag)
    except RuntimeError:
        return None, "issue_unreadable"
    if issue.get("pull_request"):
        return None, "ref_is_pull_request"
    try:
        pr = gh(f"repos/{owner}/{repo}/pulls/{n}", tag)
        if pr.get("state") != "open":
            return None, "not_open"
        if not 1 <= int(pr.get("changed_files") or 0) <= MAX_FILES:
            return None, "file_count_out_of_range"
        files = all_pages(f"repos/{owner}/{repo}/pulls/{n}/files", tag, cap=3)
    except RuntimeError:
        return None, "pr_unreadable"
    files = [{k: f.get(k) for k in ("filename", "status", "patch", "previous_filename")} for f in files]
    task = A.task_text(issue, pr)
    rec = record(item, no, pr, files, X.analyse(task[0], files, repo=f"{owner}/{repo}", version=RULES))
    return (rec, None) if rec else (None, "nothing_listed")


def prefetching(items: list, tag: str, ahead: int = 12, workers: int = 6):
    """evaluate() for the walk, with the next `ahead` candidates fetched in parallel (network latency, not CPU). The walk's
    order and decisions are those of select(); only the fetching runs ahead."""
    import concurrent.futures as cf
    order = [i for i in sorted({i["html_url"]: i for i in items}.values(), key=lambda i: order_key(i["html_url"]))
             if quick_skip(i) is None]
    pos = {it["html_url"]: k for k, it in enumerate(order)}
    pool, futs = cf.ThreadPoolExecutor(workers), {}

    def ev(it):
        k = pos[it["html_url"]]
        for j in range(k, min(k + ahead, len(order))):
            u = order[j]["html_url"]
            if u not in futs:
                futs[u] = pool.submit(evaluate, order[j], tag)
        return futs[it["html_url"]].result()
    return ev


def sample() -> int:
    tag = "prospective-sample"
    items, log = search(tag)
    first = min(f.stat().st_mtime for f in (CACHE / tag).glob("*.json"))     # the first search (the run is resumable)
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(first))
    kept, skipped = select(items, prefetching(items, tag))
    kept.sort(key=lambda r: order_key(r["url"]))
    res = {"rubric": "eval/prospective_rubric.json", "rules_version": RULES, "seed": SEED, "searched_at": started,
           "read_on": READ_ON, "searches": log, "pool": len({i["html_url"] for i in items}), "skipped": dict(sorted(skipped.items())),
           "summary": {"pull_requests": len(kept), "listed_files": sum(len(k["listed_paths"]) for k in kept),
                       "files": sum(len(k["files"]) for k in kept),
                       "by_agent": dict(sorted(collections.Counter(k["agent"] for k in kept).items())),
                       "read_on": READ_ON, "cases_sha256": cases_sha256(kept)},
           "pull_requests": kept}
    SEALED.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res["summary"]))
    print("sha256", hashlib.sha256(SEALED.read_bytes()).hexdigest(), SEALED.relative_to(ROOT))
    return 0


def read() -> int:
    sealed = json.loads(SEALED.read_text())
    assert sealed["summary"]["cases_sha256"] == cases_sha256(sealed["pull_requests"]), "the sealed list was changed"
    today = time.strftime("%Y-%m-%d", time.localtime())
    tag = f"prospective-read-{today}"
    rows, prs = [], []
    for s in sealed["pull_requests"]:
        owner, repo, n = pr_parts(s["url"])
        base = f"repos/{owner}/{repo}"
        try:
            pr = gh(f"{base}/pulls/{n}", tag)
            files = all_pages(f"{base}/pulls/{n}/files", tag)
            comments = (all_pages(f"{base}/pulls/{n}/comments", tag) + all_pages(f"{base}/pulls/{n}/reviews", tag)
                        + all_pages(f"{base}/issues/{n}/comments", tag))
        except RuntimeError as e:
            prs.append({"url": s["url"], "unreadable": True, "reason": str(e)[:160]})
            continue
        if len(files) >= 3000:
            prs.append({"url": s["url"], "unreadable": True, "reason": "file list at the API cap"})
            continue
        rows += outcomes(s, pr, files, comments)
        prs.append({"url": s["url"], "unreadable": False, "state": pr.get("state"), "merged": bool(pr.get("merged")),
                    "added_after_sampling": len({f["filename"] for f in files} - set(s["files"]))})
    res = {"rubric": "eval/prospective_rubric.json", "sealed": "results/prospective_v1_sealed.json",
           "sealed_cases_sha256": sealed["summary"]["cases_sha256"], "read_on": today,
           "summary": summarize(rows, prs), "pull_requests": prs, "files": rows}
    rules = json.loads(SENTENCES.read_text())
    res["sentences_sha256"] = hashlib.sha256(SENTENCES.read_bytes()).hexdigest()
    res["sentences_frozen_on"] = frozen_on(res["sentences_sha256"])
    res["band"], res["sentence"] = sentence(res["summary"], today, rules)
    res["counts"] = values(res["summary"], today)
    READ.write_text(json.dumps(res, indent=1) + "\n")
    README.write_text(with_read(README.read_text(), readme_line(rules, res["band"], res["counts"])))
    print(json.dumps({k: res["summary"][k] for k in ("pull_requests_sealed", "unreadable", "open", "merged", "listed")}))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=("sample", "seal-sentences", "read"))
    a = ap.parse_args(argv)
    return {"sample": sample, "seal-sentences": seal_sentences, "read": read}[a.step]()


if __name__ == "__main__":
    sys.exit(main())
