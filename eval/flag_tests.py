"""How many of the public replay's G flags (Developer Flow merge requests, the agent's own version) are tests deleted
together with a feature flag: a `tests_removed` extra whose removed lines name a flag whose definition
(config/feature_flags/**/<name>.yml) the same diff deletes. Found after labelling (fleet 8, P1), not pre-registered;
the rules are not changed by it. Reads only the replay's cache (eval/cache/gitlab/).

usage: python3 eval/flag_tests.py            (writes results/public_replay_flag_tests.json)"""
from __future__ import annotations

import json, pathlib, re, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import replay_gitlab as G

FLAG = re.compile(r"(?:^|/)config/feature_flags/(?:.+/)?([^/]+)\.yml$")
OUT = G.ROOT / "results" / "public_replay_flag_tests.json"


def deleted_flags(files: list) -> set:
    return {m.group(1) for f in files if f.get("status") == "removed" and (m := FLAG.search(f["filename"]))}


def removed_text(f: dict | None) -> str:
    return "\n".join(l for l in ((f or {}).get("patch") or "").split("\n") if l.startswith("-") and not l.startswith("---"))


def flag_tests(files: list, extras: list) -> list:
    """The listed `tests_removed` extras whose removed lines name a flag the same diff deletes."""
    flags, by = deleted_flags(files), {f["filename"]: f for f in files}
    return [e for e in extras if e["kind"] == "tests_removed" and flags
            and any(re.search(rf"\b{re.escape(n)}\b", removed_text(by.get(e["path"]))) for n in flags)]


def summarize(rows: list, files_of) -> dict:
    out = {"merge_requests": 0, "deletes_a_flag_definition": 0, "extras": 0, "tests_removed": 0, "tests_naming_a_deleted_flag": 0}
    for r in rows:
        files = files_of(r)
        out["merge_requests"] += 1
        out["deletes_a_flag_definition"] += bool(deleted_flags(files))
        out["extras"] += len(r["extras"])
        out["tests_removed"] += sum(e["kind"] == "tests_removed" for e in r["extras"])
        out["tests_naming_a_deleted_flag"] += len(flag_tests(files, r["extras"]))
    return out


def main() -> int:
    G.AMENDMENT = 1
    raw = json.loads((G.ROOT / "results" / "public_replay_a1_raw.json").read_text())
    rows = sorted((r for r in raw if r["pop"] == "G" and r["version"] == "agent" and not r.get("excluded") and r.get("extras")),
                  key=lambda r: r["ref"])
    def files_of(r):
        return G.to_files(G.agent_version(G.versions_oldest_first(G.GITLAB, int(r["ref"].split("!")[1])))["diffs"])
    s = summarize(rows, files_of)
    OUT.write_text(json.dumps({"what": __doc__.split("\n\n")[0].replace("\n", " "), "G_agent_flagged": s}, indent=1) + "\n")
    print(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
