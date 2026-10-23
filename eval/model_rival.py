"""The model-rival study (eval/model_rival_rubric.json, pushed before any model call): a general model asked the
ticket-compliance question on a fixed sample of the head-to-head's snapshots, scored as the head-to-head scores its rivals.

usage: python3 eval/model_rival.py export [--per-batch 20]    # writes eval/cache/model_rival/batch_*.json
       (agents write answer_*.json beside each batch)
       python3 eval/model_rival.py score                      # writes results/model_rival_v1.json"""
from __future__ import annotations

import argparse, json, pathlib, random, statistics, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

DIR = ROOT / "eval" / "cache" / "model_rival"
OUT = ROOT / "results" / "model_rival_v1.json"
RUBRIC = ROOT / "eval" / "model_rival_rubric.json"
SEED, SAMPLE, PER_FILE, WHOLE = 20261023, 100, 600, 14000
LOOK_MAX = 5      # flows/itemator_card.yml step e2: "At most 5 paths, in DIFFS order"


# ---------------------------------------------------------------- pure parts (tests/test_model_rival.py)

def draw(keys: list) -> list:
    return random.Random(SEED).sample(keys, SAMPLE) if len(keys) > SAMPLE else list(keys)


def cut_diff(files: list, unified_diff) -> str:
    short = [dict(f, patch=(f.get("patch") or "")[:PER_FILE]) for f in files]
    return unified_diff(short)[:WHOLE]


def parse(answer) -> set | None:
    """The model's answer, as a set of paths; None when it is not the JSON the prompt asks for."""
    if isinstance(answer, str):
        try:
            answer = json.loads(answer)
        except ValueError:
            return None
    if not isinstance(answer, dict) or not isinstance(answer.get("out_of_scope"), list):
        return None
    return {p for p in answer["out_of_scope"] if isinstance(p, str)}


def second_look(files: list, item: set, model: set) -> list:
    """What the card's second look shows: the model's files the rules did not list, in diff order, at most LOOK_MAX."""
    return [f["filename"] for f in files if f["filename"] in model and f["filename"] not in item][:LOOK_MAX]


def summarise(rows: list, snaps: list, rubric: dict, wilson) -> dict:
    n = len(rows)
    s = {"cases": n, "snapshots": len(snaps), "invalid_answers": sum(x["invalid"] for x in snaps), "tools": {}}
    for t in ("itemator", "model"):
        k = sum(r["named"][t] for r in rows)
        s["tools"][t] = {"cases_named": k, "wilson95": wilson(k, n), "files_named": sum(x["named"][t] for x in snaps),
                         "median_named_per_snapshot": statistics.median([x["named"][t] for x in snaps]) if snaps else 0}
    s["model_not_itemator"] = sum(r["named"]["model"] and not r["named"]["itemator"] for r in rows)
    s["itemator_not_model"] = sum(r["named"]["itemator"] and not r["named"]["model"] for r in rows)
    s["either_named"] = sum(r["named"]["itemator"] or r["named"]["model"] for r in rows)     # rules or the model's whole list
    s["card_named"] = sum(r["named"].get("card", False) for r in rows)                     # the card as shipped: rules + capped second look
    s["second_look_files"] = sum(x["named"].get("look", 0) for x in snaps)
    m, i = s["tools"]["model"], s["tools"]["itemator"]
    s["sentence"] = rubric["sentence"].format(snapshots=s["snapshots"], cases=n, model_cases=m["cases_named"], model_files=m["files_named"],
                                              itemator_cases=i["cases_named"], itemator_files=i["files_named"])
    return s


# ---------------------------------------------------------------- the run (local cache, agents in between)

def export(per_batch: int) -> int:
    import head_to_head as H
    snaps = H.snapshots()
    keys = draw(list(snaps))
    DIR.mkdir(parents=True, exist_ok=True)
    rubric = json.loads(RUBRIC.read_text())
    items = [{"id": f"{url}@{sha}", "ticket": snaps[(url, sha)]["task"], "diff": cut_diff(snaps[(url, sha)]["files"], H.unified_diff)}
             for url, sha in keys]
    for b in range(0, len(items), per_batch):
        (DIR / f"batch_{b // per_batch:02d}.json").write_text(json.dumps({"prompt": rubric["prompt"], "items": items[b:b + per_batch]}, indent=1))
    (DIR / "sample.json").write_text(json.dumps([list(k) for k in keys]))
    print(f"{len(items)} snapshots in {-(-len(items) // per_batch)} batches")
    return 0


def score() -> int:
    import head_to_head as H
    snaps = H.snapshots()
    keys = [tuple(k) for k in json.loads((DIR / "sample.json").read_text())]
    answers = {}
    for f in sorted(DIR.glob("answer_*.json")):
        answers.update(json.loads(f.read_text()))
    rows, out_snaps = [], []
    for url, sha in keys:
        s = snaps[(url, sha)]
        got = parse(answers.get(f"{url}@{sha}"))
        model = got or set()
        item = H.itemator_named(s["task"], s["files"], s["repo"])
        look = second_look(s["files"], item, model)
        out_snaps.append({"pr": url, "sha": sha, "invalid": got is None, "named": {"itemator": len(item), "model": len(model), "look": len(look)}})
        for c in s["cases"]:
            rows.append({"comment_id": c["comment_id"], "pr": url, "path": c["path"],
                         "named": {"itemator": c["path"] in item, "model": c["path"] in model, "card": c["path"] in item or c["path"] in look}})
    summary = summarise(rows, out_snaps, json.loads(RUBRIC.read_text()), H.wilson)
    old = json.loads(OUT.read_text())["summary"] if OUT.exists() else {}
    summary.update({k: v for k, v in old.items() if k.startswith("note_")})                 # dated notes stay
    OUT.write_text(json.dumps({"rubric": "eval/model_rival_rubric.json", "summary": summary, "snapshots": out_snaps, "rows": rows}, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=("export", "score"))
    ap.add_argument("--per-batch", type=int, default=20)
    a = ap.parse_args(argv)
    return export(a.per_batch) if a.step == "export" else score()


if __name__ == "__main__":
    sys.exit(main())
