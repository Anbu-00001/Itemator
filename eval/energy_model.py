"""Modelled energy of the model calls the v1.1 prompt avoids. Run: python3 eval/energy_model.py (writes results/energy_modelled_v1.json).

Measured: model calls per card run, from results/card_model_calls.json (Duo session records). Modelled: energy per call, from outside
papers that disagree by about 300 times; Duo's model per call is not disclosed, so no single figure is given, only the range.
Nothing here measures energy: the output says so."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CALLS = ROOT / "results" / "card_model_calls.json"
OUT = ROOT / "results" / "energy_modelled_v1.json"

# Per agent-sized call (about 10k tokens in, 1.5k out), watt-hours. Ends of the range come from different methods and are not averaged.
LOW_WH, HIGH_WH = 0.1, 30
SOURCES = {
    "low": "EcoLogits method (ecologits.ai, as read 2026-10-18), 24 to 400 billion active parameters: about 0.08 to 0.4 Wh for 1.5k output tokens; Jegham et al. arXiv 2505.09598v6, most efficient of 30 models",
    "high": "Jegham et al. arXiv 2505.09598v6: over 29 Wh for 10k in and 1.5k out, most energy-hungry of 30 models",
    "middle_reading": "Epoch AI (7 Feb 2025): about 2.5 Wh for 10k input tokens of GPT-4o",
    "short_chat_reference": "Google, 22 Aug 2025: 0.24 Wh for a median Gemini text prompt, a company figure not independently verified, short replies",
}


def mean(xs):
    return sum(xs) / len(xs)


def compute(data: dict) -> dict:
    before = [r["model_calls"] for r in data["before"]]
    three = [r["model_calls"] for r in data["after"] if r["extras"] == 3]
    assert len(before) == 3 and len(three) == 1, "like for like: the three before-runs and the one after-run with three extras"
    b, a = mean(before), mean(three)
    saved = b - a
    return {"model_calls_before_mean": round(b, 2), "model_calls_after": a, "model_calls_avoided_per_run": round(saved, 2),
            "share_avoided": round(saved / b, 3),
            "wh_per_run_avoided_low": round(saved * LOW_WH, 2), "wh_per_run_avoided_high": round(saved * HIGH_WH, 1)}


def main():
    data = json.loads(CALLS.read_text())
    out = {"what": "Calls the v1.1 prompt avoids on a three-extras card run (measured), times a per-call energy range from outside papers (modelled). Energy is not measured here.",
           "wh_per_call": {"low": LOW_WH, "high": HIGH_WH, "sources": SOURCES, "spread": HIGH_WH / LOW_WH},
           **{"summary": compute(data)},
           "limits": "Three runs before, one comparable run after; the prompt changed, not the facts (results/fact_file_ablation_v1.json: the facts alone did not cut calls). The model behind a Duo call is not disclosed. No carbon figure: the data-centre grid is unknown. The range is about 300-fold, so it shows that the answer is small or large depending on the method, not a saving to quote in kWh."}
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(out["summary"])


if __name__ == "__main__":
    main()
