"""itemator/sci.py: the SCI bracket the card adds to a weighed dependency."""
import json
import pathlib

from itemator import registry as RG, sci as SCI

RES = pathlib.Path(__file__).resolve().parent.parent / "results"


def weight(bytes_=30562008, sized=6, of=6, capped=False, pipelines=None):
    w = {"weight": "ok", "packages": 6, "direct": 4, "sized": sized, "of": of, "bytes": bytes_, "capped": capped, "largest": []}
    if pipelines:
        w["pipelines"] = pipelines
    return w


def test_the_install_seconds_are_the_studies_medians():
    med = sorted(json.loads((RES / f"install_time_{e}_v1.json").read_text())["summary"]["median_seconds_above_baseline"] for e in ("pypi", "npm"))
    assert list(SCI.SECONDS) == med


def test_the_card_words_for_the_live_case():
    assert SCI.part(weight(pipelines={"count": 936, "at_least": False, "days": 30})) == (
        "by the SCI method, a bracket from borrowed coefficients: 0.014 g to 2.0 g CO2e per fresh install "
        "and 13 g to 1.9 kg a month at those pipelines")


def test_without_pipelines_there_is_no_month():
    assert SCI.part(weight()).endswith("0.014 g to 2.0 g CO2e per fresh install")


def test_unknown_sizes_or_a_capped_graph_make_it_at_least():
    assert ": at least 0.014 g to at least" not in SCI.part(weight(sized=5))
    assert SCI.part(weight(sized=5)).startswith("by the SCI method, a bracket from borrowed coefficients: at least ")
    assert ": at least " in SCI.part(weight(capped=True))
    assert " and at least " in SCI.part(weight(pipelines={"count": 936, "at_least": True, "days": 30}))
    assert " and at least " not in SCI.part(weight(pipelines={"count": 936, "at_least": False, "days": 30}))


def test_nothing_sized_says_nothing():
    assert SCI.part(None) is None and SCI.part({"weight": "unavailable"}) is None and SCI.part(weight(sized=0)) is None


def test_two_significant_figures_and_kilograms_from_one_up():
    assert [SCI.grams(x) for x in (100000, 1500, 1000, 999.4, 2.894, 0.00241, 0, 13.4, 9.97, 0.0999, 0.00097)] == [
        "100 kg", "1.5 kg", "1.0 kg", "1.0 kg", "2.9 g", "0.0024 g", "0 g", "13 g", "10 g", "0.10 g", "0.00097 g"]


def test_the_registry_sentence_ends_with_the_weight_then_the_bracket():
    p = {"ecosystem": "PyPI", "name": "pandas", "version": "2.2.3", "checked": "2026-10-19", "lookup": "ok", "found": True,
         "first_release": "2009-12-25", "releases": 118, "yanked": 1, "license": "BSD License", "license_form": "classifier",
         "advisories": 0, "weight": weight(pipelines={"count": 936, "at_least": False, "days": 30})}
    s = RG.sentence({"count": 1, "packages": [p]})
    assert "a month if each one installs it without a cache, by the SCI method, a bracket from borrowed coefficients: 0.014 g" in s
    assert s.endswith("13 g to 1.9 kg a month at those pipelines (checked 2026-10-19).")
