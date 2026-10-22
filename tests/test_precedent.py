"""Decided before: itemator/precedent.py and its place in the CI job."""
from itemator import answerlog as A
from itemator import precedent as PRE


def entry(iid, items, at="2026-10-20T10:00:00Z"):
    return {"iid": iid, "note": iid * 10, "at": at, "commit": "c" * 40, "items": items, "body_sha256": "x",
            "url": f"https://gitlab.example/mr/{iid}#note_{iid * 10}"}


def item(name, decision, who="pat"):
    return {"name": name, "decision": decision, "who": who, "ref": None}


LOG = {"entries": A.chain([entry(10, [item("pandas", "kept", "ann")]),
                           entry(11, [item("pandas", "removed", "bo"), item(".gitlab-ci.yml", "moved")], at="2026-10-21T09:00:00Z"),
                           entry(12, [item("left-pad", "dismissed")])])}


def test_the_newest_decision_on_another_merge_request_wins():
    got = PRE.find(LOG, ["pandas", ".gitlab-ci.yml", "requests"], mr_iid=99)
    assert got["pandas"] == {"decision": "removed", "iid": 11, "who": "bo", "on": "2026-10-21",
                             "url": "https://gitlab.example/mr/11#note_110", "differ": [{"decision": "kept", "iid": 10}]}
    assert got[".gitlab-ci.yml"]["decision"] == "moved" and "requests" not in got


def test_its_own_merge_request_does_not_count():
    assert PRE.find(LOG, ["pandas"], mr_iid=11)["pandas"]["iid"] == 10


def test_a_broken_or_missing_chain_adds_nothing():
    bad = {"entries": [dict(e) for e in LOG["entries"]]}
    bad["entries"][1]["items"] = [item("pandas", "kept", "mallory")]       # edited after it was chained
    assert PRE.find(bad, ["pandas"], 99) == {}
    assert PRE.find(None, ["pandas"], 99) == {} and PRE.find({"entries": []}, ["pandas"], 99) == {}
    assert PRE.find({"entries": "x"}, ["pandas"], 99) == {}


def test_the_sentence_names_no_one_with_an_at_sign():
    s = PRE.sentence({"decision": "moved", "iid": 11, "who": "bo", "on": "2026-10-21"})
    assert s == "Decided before: moved to its own merge request on !11 by bo on 2026-10-21 (public answer log)."
    assert "@" not in s
    assert PRE.sentence({"decision": "dismissed", "iid": 12, "who": None, "on": "2026-10-20"}) == \
        "Decided before: called not an extra on !12 on 2026-10-20 (public answer log)."


def test_where_the_log_is_read_from():
    assert PRE.url_of({"ITEMATOR_ANSWERS_URL": "https://x/a.json", "CI_PAGES_URL": "https://p"}) == "https://x/a.json"
    assert PRE.url_of({"CI_PAGES_URL": "https://p/"}) == "https://p/answers/answers.json"
    assert PRE.url_of({}) is None


def test_apply_adds_the_sentence_after_the_thread_text_and_keeps_the_name_first():
    report = {"extras": [{"name": "pandas", "thread_stub": "`pandas` (new dependency): ...", "plain_facts": {}},
                         {"name": "requests", "thread_stub": "`requests` (new dependency): ...", "plain_facts": {}}]}
    seen = []
    n = PRE.apply(report, {"CI_PAGES_URL": "https://p"}, 99, get=lambda u: seen.append(u) or LOG)
    assert n == 1 and seen == ["https://p/answers/answers.json"]
    pandas, requests = report["extras"]
    assert pandas["thread_stub"].startswith("`pandas`")
    assert pandas["thread_stub"].endswith("\n\nDecided before: removed on !11 by bo on 2026-10-21 (public answer log). Earlier answers differ: kept on !10.")
    assert pandas["plain_facts"]["decided_before"]["iid"] == 11
    assert requests["thread_stub"] == "`requests` (new dependency): ..." and "decided_before" not in requests["plain_facts"]
    assert report["decided_before"] == {"read": True, "matched": 1}


def test_apply_reads_nothing_without_extras_or_a_place_to_read():
    calls = []
    r = {"extras": []}
    assert PRE.apply(r, {"CI_PAGES_URL": "https://p"}, 1, get=lambda u: calls.append(u)) == 0 and calls == []
    r = {"extras": [{"name": "a", "thread_stub": "`a`", "plain_facts": {}}]}
    assert PRE.apply(r, {}, 1, get=lambda u: calls.append(u)) == 0 and calls == [] and r["decided_before"]["read"] is False


def test_an_unreadable_log_never_stops_the_job(monkeypatch):
    import urllib.request

    def boom(*a, **k):
        raise OSError("down")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert PRE.fetch("https://p/answers/answers.json") is None


def test_a_decision_word_it_does_not_know_is_left_out():
    log = {"entries": A.chain([entry(10, [item("pandas", "kept")]), entry(11, [item("pandas", "approved")])])}
    assert PRE.find(log, ["pandas"], 99)["pandas"]["iid"] == 10              # never a sentence with an unknown word


def test_earlier_answers_that_differ_are_named_and_agreeing_ones_are_not():
    log = {"entries": A.chain([entry(1, [item("ci", "kept")]), entry(2, [item("ci", "removed")]), entry(3, [item("ci", "kept")]),
                               entry(4, [item("ci", "moved")]), entry(5, [item("ci", "kept")])])}
    p = PRE.find(log, ["ci"], mr_iid=99)["ci"]
    assert p["differ"] == [{"decision": "removed", "iid": 2}, {"decision": "moved", "iid": 4}]
    assert PRE.sentence(p) == ("Decided before: kept on !5 by pat on 2026-10-20 (public answer log). "
                               "Earlier answers differ: removed on !2; moved to its own merge request on !4.")


def test_answers_that_all_agree_keep_the_short_line():
    log = {"entries": A.chain([entry(1, [item("ci", "kept")]), entry(2, [item("ci", "kept")])])}
    p = PRE.find(log, ["ci"], mr_iid=99)["ci"]
    assert p["differ"] == [] and PRE.sentence(p).endswith("(public answer log).")


def test_this_merge_requests_own_earlier_answer_is_not_an_earlier_answer():
    log = {"entries": A.chain([entry(99, [item("ci", "removed")]), entry(2, [item("ci", "kept")])])}
    assert PRE.find(log, ["ci"], mr_iid=99)["ci"]["differ"] == []


def test_many_merge_requests_are_cut_to_three_and_a_count():
    assert PRE._listed(["!1"]) == "!1"
    assert PRE._listed(["!1", "!2"]) == "!1 and !2"
    assert PRE._listed(["!1", "!2", "!3"]) == "!1, !2 and !3"
    assert PRE._listed(["!1", "!2", "!3", "!4", "!5"]) == "!1, !2, !3 and 2 more"
