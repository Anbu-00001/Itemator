"""The labelling summary follows its rubric: kappa, strict and lenient per merge request, field projects as counts only."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import label_summary as S  # noqa: E402


def test_packet_names_become_references():
    assert S.ref_of("G_flagged__gitlab-org_gitlab_242496.json") == ("G_flagged", "gitlab-org/gitlab!242496")
    assert S.ref_of("F_flagged__1566bdff_1.json") == ("F_flagged", "1566bdff!1")


def test_kappa():
    assert S.kappa([]) is None
    assert S.kappa([("real", "real"), ("not_an_extra", "not_an_extra")]) == 1.0
    pairs = [("real", "real")] * 2 + [("real", "not_an_extra")] + [("not_an_extra", "real")] + [("not_an_extra", "not_an_extra")] * 6
    assert S.kappa(pairs) == round((0.8 - (3 * 3 + 7 * 7) / 100) / (1 - (3 * 3 + 7 * 7) / 100), 3)
    assert S.kappa([("real", "real"), ("real", "not_an_extra"), ("real", "not_an_extra"), ("not_an_extra", "not_an_extra")]) == 0.2
    assert S.kappa([("real", "real")] * 3) is None


def test_strict_needs_both_on_the_same_extra_and_lenient_either_on_any():
    got = S.per_merge_request([("a", "real", "not_an_extra"), ("a", "not_an_extra", "real"),
                               ("b", "real", "real"), ("c", "not_an_extra", "borderline"), ("d", "not_an_extra", "not_an_extra")])
    assert got == {"a": {"strict": False, "lenient": True}, "b": {"strict": True, "lenient": True},
                   "c": {"strict": False, "lenient": True}, "d": {"strict": False, "lenient": False}}


def test_summary_counts_and_keeps_field_projects_to_counts():
    def ex(packet, path, kind, label):
        return {"packet": packet, "path": path, "kind": kind, "label": label}
    g, f = "G_flagged__gitlab-org_gitlab_5.json", "F_flagged__abcd1234_2.json"
    l1 = {"model": "m1", "extras": [ex(g, "a.rb", "tests_removed", "real"), ex(g, "a.rb", "tests_removed", "real"), ex(g, "a.rb", "public_api_removed", "not_an_extra"),
                         ex(f, "x.toml", "new_dependency", "real")],
          "misses": [{"packet": "G_unflagged__gitlab-org_gitlab_7.json", "answer": "yes"}, {"packet": "G_unflagged__gitlab-org_gitlab_8.json", "answer": "yes"},
                     {"packet": "G_unflagged__gitlab-org_gitlab_9.json", "answer": "unsure"}]}
    l2 = {"model": "m2", "extras": [ex(g, "a.rb", "tests_removed", "real"), ex(g, "a.rb", "public_api_removed", "not_an_extra"),
                                    ex(f, "x.toml", "new_dependency", "borderline")],
          "misses": [{"packet": "G_unflagged__gitlab-org_gitlab_7.json", "answer": "yes"}, {"packet": "G_unflagged__gitlab-org_gitlab_8.json", "answer": "yes"},
                     {"packet": "G_unflagged__gitlab-org_gitlab_9.json", "answer": "yes"}]}
    raw = [{"pop": "G", "version": "agent", "ref": "gitlab-org/gitlab!7", "issue_refs": ["#70"]},
           {"pop": "G", "version": "agent", "ref": "gitlab-org/gitlab!5", "issue_refs": ["#50"]}]
    s = S.summarize(l1, l2, raw, {"gitlab-org/gitlab!7": "Follows !70.", "gitlab-org/gitlab!5": "Relates to #50"}.get)
    assert s["agreement"]["extras"] == 3 and s["agreement"]["same_label"] == 2 and s["agreement"]["entries"] == {"L1": 4, "L2": 3}
    assert s["agreement"]["disputed"] == [{"group": "F_flagged", "kind": "new_dependency", "L1": "real", "L2": "borderline"}]
    assert s["per_merge_request"]["G_flagged"]["strict"] == 1 and s["per_merge_request"]["F_flagged"] == {
        "merge_requests": 1, "strict": 0, "lenient": 1, "strict_wilson95": S.G.wilson(0, 1), "lenient_wilson95": S.G.wilson(1, 1)}
    assert [e.get("ref") for e in s["extras"]] == ["gitlab-org/gitlab!5"] * 2 and "abcd1234" not in str(s)
    assert s["labels_by_kind"] == {"new_dependency": {"real": 1, "borderline": 1}, "public_api_removed": {"not_an_extra": 2},
                                 "tests_removed": {"real": 2}}
    assert (s["misses"]["both_yes"], s["misses"]["either_yes"], s["misses"]["both_yes_with_the_issue_not_named_in_the_description"]) == (2, 3, 1)
    assert s["misses"]["rows"][1]["issue_named_in_description"] is None
    assert s["G_flagged_issue_named_in_description"] == {"gitlab-org/gitlab!5": True}
