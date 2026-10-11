"""T17 replay: registry facts for the new-dependency extras that rules v4 flags in samples A, B and C.

Run once from the repository root (the output is never overwritten):
    .venv/bin/python -I eval/registry_check.py
Reads results/replay_v4_devABC.json (the v4 extras) and eval/cache (each PR's files, matched by the files_sha256 that
replay recorded). It draws no other PR and reads no dataset. Network: read-only lookups only, GETs to the three
registries and POSTs to OSV's query API, at most MAX_REQUESTS, GAP seconds apart; each answer is kept, so no request
is sent twice.

Pass 1 looks up every package name one at a time, each with the job's own budget. Pass 2 builds each extra's card
sentence exactly as the CI job does (the caps included), from the answers of pass 1.

A name that is not found is not shown to be invented: internal and workspace packages are legitimately absent from
public registries. Each needs a human or model check.
"""
from __future__ import annotations

import collections
import datetime
import hashlib
import json
import pathlib
import sys
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO)]
from itemator import ci, registry as RG  # noqa: E402
from itemator.extras import Extra  # noqa: E402

SRC = REPO / "results" / "replay_v4_devABC.json"
CACHE = REPO / "eval" / "cache"
OUT = REPO / "results" / "registry_facts_devABC.json"
MAX_REQUESTS = 150      # brief T17 item 6: a light, read-only replay
GAP = 1.0               # seconds between requests (brief T17 item 6; crates.io's crawler policy asks for at most 1 per second)
NOTE = ("A name that is not found is not shown to be invented: internal and workspace packages are legitimately absent "
        "from public registries. Each not-found name needs a human or model check.")


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Polite:
    """The real fetch, GAP seconds apart, at most MAX_REQUESTS, each answer kept for the second pass."""

    def __init__(self):
        self.answers, self.sent, self.last = {}, [], 0.0

    def __call__(self, method, url, body, timeout):
        key = (method, url, body)
        if key not in self.answers:
            if len(self.sent) >= MAX_REQUESTS:
                raise RG.LookupFailed("replay_cap")
            time.sleep(max(0.0, self.last + GAP - time.monotonic()))
            self.sent.append({"method": method, "url": url})
            try:
                self.answers[key] = ("ok", RG.fetch(method, url, body, timeout))
            except RG.LookupFailed as e:
                self.answers[key] = ("failed", e.code)
            self.last = time.monotonic()
        kind, value = self.answers[key]
        if kind == "failed":
            raise RG.LookupFailed(value)
        return value


def main() -> int:
    if OUT.exists():
        sys.exit(f"{OUT} exists; this replay runs once (move the file away to repeat it)")
    records = [r for r in json.loads(SRC.read_text())["prs"]
               if any(e["kind"] == "new_dependency" for e in r["v4"]["extras"])]
    by_sha = {}
    for f in sorted(CACHE.glob("*.json")):
        files = json.loads(f.read_text())["files"]
        by_sha[hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()] = files
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.strftime("%Y-%m-%d")
    fetch = Polite()
    packages, cards, missing = [], [], []
    for r in records:
        files = by_sha.get(r["files_sha256"])
        if files is None:
            missing.append(r["pr_url"])
            continue
        by_path = {f["filename"]: f for f in files}
        extras = [Extra(e["kind"], e["path"], e["name"], e["why"], tuple(e["detail"])) for e in r["v4"]["extras"]]
        for e in extras:
            if e.kind == "new_dependency":                               # pass 1: every name
                rec = RG.Run(fetch, today).look(RG.request_for(e, by_path))
                packages.append({"pr_url": r["pr_url"], "sample": r["sample"], "path": e.path, **rec})
        grouped = ci.group_extras(extras)                                # pass 2: the cards, as the job builds them
        for (e, items), reg in zip(grouped, RG.look_up(grouped, by_path, fetch, now)):
            if reg is not None:
                cards.append({"pr_url": r["pr_url"], "name": e.name, "registry": reg,
                              "thread_stub": ci.describe_extra(e, by_path, items, reg)["thread_stub"]})
    asked = [p for p in packages if p["lookup"] in ("ok", "unavailable") and p.get("reason") != "invalid_name"]
    summary = {
        "what": "registry facts for the new-dependency extras rules v4 flags in samples A, B and C (development set)",
        "checked": today, "source": "results/replay_v4_devABC.json", "source_sha256": sha256(SRC),
        "registry_sha256": sha256(REPO / "itemator/registry.py"), "ci_sha256": sha256(REPO / "itemator/ci.py"),
        "prs": len(records) - len(missing), "prs_without_cached_files": missing,
        "new_dependency_extras": len(packages), "card_lines": len(cards),
        "packages_looked_up": len(asked),
        "found": sum(1 for p in asked if p["lookup"] == "ok" and p["found"]),
        "not_found": sum(1 for p in asked if p["lookup"] == "ok" and not p["found"]),
        "unavailable": sum(1 for p in asked if p["lookup"] == "unavailable"),
        "unavailable_reasons": dict(collections.Counter(p["reason"] for p in asked if p["lookup"] == "unavailable")),
        "names_refused": sum(1 for p in packages if p.get("reason") == "invalid_name"),
        "not_looked_up": dict(collections.Counter(p.get("reason") or p["lookup"] for p in packages
                                                  if p["lookup"] in ("not_supported", "not_from_registry"))),
        "not_found_names": [{"name": p["name"], "ecosystem": p["ecosystem"], "pr_url": p["pr_url"]}
                            for p in asked if p["lookup"] == "ok" and not p["found"]],
        "requests_sent": len(fetch.sent), "request_cap": MAX_REQUESTS, "gap_seconds": GAP,
        "note": NOTE,
    }
    OUT.write_text(json.dumps({"summary": summary, "packages": packages, "cards": cards}, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("not_found_names",)}, indent=1))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
