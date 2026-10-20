"""How often the card's feature-flag fact (itemator/ci.py flag_cleanup, T65) appears on the public replay's G flags (Developer
Flow merge requests, the agent's own version). Written after eval/flag_tests.py found the pattern, so this is in-sample: it
shows the sentence fires where that study counted, not that it generalises. Reads only the replay's cache (eval/cache/gitlab/).

usage: python3 eval/flag_fact_replay.py            (writes results/flag_fact_replay_v1.json)"""
from __future__ import annotations

import json, pathlib, sys, types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import replay_gitlab as G  # noqa: E402
from itemator import ci  # noqa: E402

OUT = G.ROOT / "results" / "flag_fact_replay_v1.json"


def count(rows, files_of) -> dict:
    out = {"merge_requests": 0, "tests_removed": 0, "with_the_flag_fact": 0, "merge_requests_where_every_extra_has_it": 0}
    for r in rows:
        by = {f["filename"]: f for f in files_of(r)}
        hits = [ci.flag_cleanup(types.SimpleNamespace(kind=e["kind"], path=e["path"]), by) for e in r["extras"]]
        out["merge_requests"] += 1
        out["tests_removed"] += sum(e["kind"] == "tests_removed" for e in r["extras"])
        out["with_the_flag_fact"] += sum(bool(h) for h in hits)
        out["merge_requests_where_every_extra_has_it"] += all(hits)
    return out


def main() -> int:
    G.AMENDMENT = 1
    raw = json.loads((G.ROOT / "results" / "public_replay_a1_raw.json").read_text())
    rows = sorted((r for r in raw if r["pop"] == "G" and r["version"] == "agent" and not r.get("excluded") and r.get("extras")),
                  key=lambda r: r["ref"])
    s = count(rows, lambda r: G.to_files(G.agent_version(G.versions_oldest_first(G.GITLAB, int(r["ref"].split("!")[1])))["diffs"]))
    OUT.write_text(json.dumps({"what": __doc__.split("\n\n")[0].replace("\n", " "), "G_agent_flagged": s}, indent=1) + "\n")
    print(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
