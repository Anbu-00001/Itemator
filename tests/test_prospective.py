"""The prospective test's own parts (eval/prospective.py, eval/prospective_rubric.json): which hits are sampled, in what
order, and how the outcome reader decides 'objected', 'removed', 'landed' and the counts. Fixtures only; no network."""
import pytest
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import prospective as P  # noqa: E402

CREATED = "2026-10-20T10:00:00Z"


def hit(n, repo="o/r", login="Copilot", body="Fixes #1", state="open", title="Add x"):
    return {"html_url": f"https://github.com/{repo}/pull/{n}", "user": {"login": login}, "body": body, "state": state,
            "title": title, "created_at": CREATED}


def comment(body, login="rev", kind="User", path=None, at="2026-10-21T00:00:00Z"):
    return {"user": {"login": login, "type": kind}, "body": body, "created_at": at, "path": path}


# ---------------------------------------------------------------- sampling

def test_the_agent_is_confirmed_from_the_item_in_the_rubric_order():
    assert P.agent_of({"user": {"login": "Copilot"}}) == "copilot"
    assert P.agent_of({"user": {"login": "devin-ai-integration[bot]"}}) == "devin"
    assert P.agent_of({"user": {"login": "x"}, "body": "🤖 Generated with [Claude Code](https://claude.com)"}) == "claude_code"
    assert P.agent_of({"user": {"login": "x"}, "body": "Codex Task https://chatgpt.com/codex/tasks/1"}) == "codex"
    assert P.agent_of({"user": {"login": "x"}, "body": "Codex Task"}) is None
    assert P.agent_of({"user": {"login": "Copilot"}, "body": "Generated with Claude Code"}) == "copilot"


def test_the_issue_is_the_first_same_repository_closing_reference():
    assert P.issue_ref("Closes #33", "o", "r") == 33
    assert P.issue_ref("see #4, fixes #5", "o", "r") == 5
    assert P.issue_ref("Fixes https://github.com/o/r/issues/9 and closes #3", "o", "r") == 9
    assert P.issue_ref("Closes #3. Fixes https://github.com/o/r/issues/9", "o", "r") == 3
    assert P.issue_ref("Fixes https://github.com/other/r/issues/9", "o", "r") is None
    assert P.issue_ref("Related to #4", "o", "r") is None
    assert P.issue_ref(None, "o", "r") is None


def test_quick_skip_reasons():
    assert P.quick_skip(hit(1)) is None
    assert P.quick_skip(hit(1, state="closed")) == "not_open"
    assert P.quick_skip(hit(1, title="[WIP] Add x")) == "wip_title"
    assert P.quick_skip(hit(1, login="someone")) == "agent_not_confirmed"
    assert P.quick_skip(hit(1, body="Adds x")) == "no_same_repo_closing_ref"


def _rec(it):
    return {"url": it["html_url"], "agent": P.agent_of(it)}, None


def test_select_walks_the_seeded_order_with_one_per_repository():
    items = [hit(n, repo=f"o/r{n % 3}") for n in range(1, 10)]
    kept, skipped = P.select(items, _rec, n=60, per_agent=60)
    by_order = sorted(items, key=lambda i: P.order_key(i["html_url"]))
    first = {}
    for it in by_order:
        first.setdefault(it["html_url"].split("/pull/")[0], it["html_url"])
    assert sorted(k["url"] for k in kept) == sorted(first.values())
    assert [k["url"] for k in kept] == [u for u in (i["html_url"] for i in by_order) if u in first.values()]
    assert skipped["repo_already_kept"] == 6


def test_select_caps_each_agent_then_fills_without_the_cap_and_stops_at_n():
    items = [hit(n, repo=f"o/c{n}") for n in range(6)] + [hit(n, repo=f"o/d{n}", login="devin-ai-integration[bot]")
                                                         for n in range(2)]
    kept, _ = P.select(items, _rec, n=5, per_agent=2)
    agents = [k["agent"] for k in kept]
    assert len(kept) == 5 and agents.count("devin") == 2 and agents.count("copilot") == 3
    assert agents[:4].count("copilot") == 2   # the first pass took only two copilot hits


def test_select_counts_the_evaluator_reasons():
    kept, skipped = P.select([hit(1), hit(2, repo="o/s")], lambda it: (None, "nothing_listed"))
    assert kept == [] and skipped["nothing_listed"] == 2


def test_cases_hash_is_order_of_keys_independent_and_changes_with_content():
    a = [{"url": "u", "files": ["a"]}]
    assert P.cases_sha256(a) == P.cases_sha256([{"files": ["a"], "url": "u"}])
    assert P.cases_sha256(a) != P.cases_sha256([{"url": "u", "files": ["b"]}])


# ---------------------------------------------------------------- the reader

PATHS = ["package.json", "src/app.py", "docs/a/README.md", "lib/README.md"]


def test_an_inline_objection_on_the_file_counts():
    assert P.objected("package.json", PATHS, [comment("Why is this needed?", path="package.json")], "agent", CREATED)
    assert not P.objected("package.json", PATHS, [comment("Why is this needed?", path="src/app.py")], "agent", CREATED)


def test_an_objection_needs_a_listed_word():
    assert not P.objected("package.json", PATHS, [comment("Looks good", path="package.json")], "agent", CREATED)
    assert P.objected("package.json", PATHS, [comment("This is out of scope", path="package.json")], "agent", CREATED)
    assert P.objected("package.json", PATHS, [comment("We don’t need this", path="package.json")], "agent", CREATED)


def test_whole_words_only():
    assert not P.objected("package.json", PATHS, [comment("removes the dropdown, whyever", path="package.json")], "agent",
                          CREATED)
    assert not P.objected("package.json", PATHS, [comment("an eavesdrop", path="package.json")], "agent", CREATED)


def test_the_author_bots_and_earlier_comments_do_not_count():
    c = [comment("remove package.json", login="agent")]
    assert not P.objected("package.json", PATHS, c, "agent", CREATED)
    assert not P.objected("package.json", PATHS, [comment("remove package.json", kind="Bot")], "agent", CREATED)
    assert not P.objected("package.json", PATHS, [comment("remove package.json", login="x[bot]")], "agent", CREATED)
    assert not P.objected("package.json", PATHS, [comment("remove package.json", at="2026-10-19T00:00:00Z")], "agent",
                          CREATED)
    assert P.objected("package.json", PATHS, [comment("remove package.json")], "agent", CREATED)


def test_a_review_body_names_the_file_by_path_or_by_a_unique_basename():
    assert P.objected("src/app.py", PATHS, [comment("please revert src/app.py")], "agent", CREATED)
    assert P.objected("src/app.py", PATHS, [comment("please revert app.py")], "agent", CREATED)
    assert not P.objected("src/app.py", PATHS, [comment("please revert myapp.py")], "agent", CREATED)
    assert not P.objected("lib/README.md", PATHS, [comment("remove the README.md change")], "agent", CREATED)
    assert P.objected("lib/README.md", PATHS, [comment("remove lib/README.md")], "agent", CREATED)


def test_reviews_use_submitted_at():
    r = {"user": {"login": "rev", "type": "User"}, "body": "revert package.json", "submitted_at": "2026-10-21T00:00:00Z"}
    assert P.objected("package.json", PATHS, [r], "agent", CREATED)
    r["submitted_at"] = "2026-10-01T00:00:00Z"
    assert not P.objected("package.json", PATHS, [r], "agent", CREATED)


def test_state_outcome_precedence():
    files = [{"filename": "a"}, {"filename": "c", "previous_filename": "b"}]
    assert P.state_outcome({"state": "closed", "merged": False}, files, "a") == "closed_unmerged"
    assert P.state_outcome({"state": "closed", "merged": True}, files, "a") == "landed"
    assert P.state_outcome({"state": "closed", "merged": True}, files, "x") == "removed"
    assert P.state_outcome({"state": "open", "merged": False}, files, "a") == "still_open_with_file"
    assert P.state_outcome({"state": "open", "merged": False}, files, "b") == "still_open_with_file"


SEALED_PR = {"url": "https://github.com/o/r/pull/1", "agent": "copilot", "created_at": CREATED,
             "files": ["package.json", "src/app.py", ".github/ci.yml"], "listed_paths": ["package.json", ".github/ci.yml"],
             "extras": [{"kind": "new_dependency", "path": "package.json", "name": "x", "files": ["package.json"]},
                        {"kind": "ci_or_config", "path": ".github/ci.yml", "name": "ci", "files": [".github/ci.yml"]}]}


def test_outcomes_and_summary_on_a_merged_pull_request():
    pr = {"state": "closed", "merged": True, "user": {"login": "Copilot"}}
    files = [{"filename": "package.json"}, {"filename": "src/app.py"}]
    rows = P.outcomes(SEALED_PR, pr, files, [comment("remove package.json please")])
    by = {r["path"]: r for r in rows}
    assert by["package.json"]["objected"] and by["package.json"]["state"] == "landed"
    assert not by["package.json"]["silent_landing"]
    assert by[".github/ci.yml"]["state"] == "removed" and by[".github/ci.yml"]["kind"] == "ci_or_config"
    assert not by["src/app.py"]["listed"] and by["src/app.py"]["silent_landing"]
    s = P.summarize(rows, [{"url": SEALED_PR["url"], "unreadable": False, "state": "closed", "merged": True,
                            "added_after_sampling": 1}, {"url": "u2", "unreadable": True}])
    assert (s["pull_requests_sealed"], s["unreadable"], s["merged"], s["files_added_after_sampling"]) == (2, 1, 1, 1)
    assert s["listed"]["files"] == 2 and s["listed"]["objected"] == 1 and s["listed"]["removed"] == 1
    assert s["listed"]["objected_or_removed"] == 2 and s["listed"]["share_objected_or_removed"] == 1.0
    assert s["unlisted"]["files"] == 1 and s["unlisted"]["objected_or_removed"] == 0
    assert s["share_landed_silently_of_listed_landed"] == 0.0
    assert s["pull_requests_with_a_listed_file_objected_or_removed"] == 1
    assert s["by_kind"]["new_dependency"]["objected"] == 1


def test_summary_of_an_open_unreviewed_pull_request():
    pr = {"state": "open", "merged": False, "user": {"login": "Copilot"}}
    rows = P.outcomes(SEALED_PR, pr, [{"filename": p} for p in SEALED_PR["files"]], [])
    s = P.summarize(rows, [{"url": SEALED_PR["url"], "unreadable": False, "state": "open", "merged": False}])
    assert s["open"] == 1 and s["listed"]["still_open_with_file"] == 2 and s["listed"]["objected_or_removed"] == 0
    assert s["share_landed_silently_of_listed_landed"] is None
    assert s["pull_requests_with_a_listed_file_objected_or_removed"] == 0


def test_the_sealed_file_matches_its_own_hash_and_holds_no_outcome():
    import json
    d = json.loads((ROOT / "results" / "prospective_v1_sealed.json").read_text())
    assert d["summary"]["cases_sha256"] == P.cases_sha256(d["pull_requests"])
    assert d["summary"]["pull_requests"] == len(d["pull_requests"])
    banned = {"state", "merged", "objected", "removed", "landed", "outcome", "comments"}
    assert all(not banned & set(p) for p in d["pull_requests"])


def test_the_readme_shows_the_sealed_hash():
    import json
    d = json.loads((ROOT / "results" / "prospective_v1_sealed.json").read_text())
    assert f"`{d['summary']['cases_sha256']}`" in (ROOT / "README.md").read_text()


def _summary(k=3, n=10, ku=2, nu=40, merged=15, closed=6, landed=5, silent=4, readable=58, kp=2, np_=7):
    return {"merged": merged, "closed_unmerged": closed, "readable": readable, "pull_requests_with_a_listed_file_objected_or_removed": kp,
            "pull_requests_with_a_listed_file": np_, "listed": {"objected_or_removed": k, "files": n, "landed": landed,
            "silent_landing": silent}, "unlisted": {"objected_or_removed": ku, "files": nu}}


RULES = json.loads(P.SENTENCES.read_text())


def test_the_band_follows_the_committed_order():
    assert P.sentence(_summary(merged=10, closed=9), "2026-10-25", RULES)[0] == "early"
    assert P.sentence(_summary(k=0), "2026-10-25", RULES)[0] == "none"
    assert P.sentence(_summary(k=3, n=10, ku=2, nu=40), "2026-10-25", RULES)[0] == "ahead"
    assert P.sentence(_summary(k=3, n=10, ku=12, nu=40), "2026-10-25", RULES)[0] == "not_ahead"     # equal shares are not ahead
    assert P.sentence(_summary(k=0, merged=1, closed=0), "2026-10-25", RULES)[0] == "early"           # early before none
    assert P.sentence(_summary(merged=14, closed=6), "2026-10-25", RULES)[0] == "ahead"                # 20 decided is enough
    assert P.sentence(_summary(k=2, n=10, ku=0, nu=40), "2026-10-25", RULES)[0] == "too_few"           # under 3 hits is not ranked
    assert P.sentence(_summary(k=5, n=10, ku=0, nu=40, kp=1), "2026-10-25", RULES)[0] == "too_few"     # all in one pull request
    assert P.sentence(_summary(k=0, kp=0), "2026-10-25", RULES)[0] == "none"                           # none before too_few
    assert P.sentence(_summary(k=1, n=10, ku=9, nu=40, kp=1), "2026-10-25", RULES)[0] == "too_few"     # too_few before not_ahead


def test_the_sentence_carries_the_counts_and_the_misses():
    band, text = P.sentence(_summary(), "2026-10-25", RULES)
    assert text == ("By 2026-10-25, reviewers objected to or removed 3 of the 10 files the rules listed (30%), against 2 of the 40 files "
                    "they did not list (5%). The listed files acted on came from 2 of the 7 pull requests with a listed file. Of the 5 listed files in merged pull requests, 4 landed with nobody objecting.")
    early = P.sentence(_summary(merged=3, closed=2), "2026-10-25", RULES)[1]
    assert "only 5 of the 58 pull requests" in early and "landed with nobody objecting" not in early
    few = P.sentence(_summary(k=2, ku=1), "2026-10-25", RULES)[1]
    assert few.startswith("By 2026-10-25, reviewers objected to or removed 2 of the 10 files the rules listed, in 2 pull request(s), "
                          "against 1 of the 40 files they did not list: too few to say") and "4 landed with nobody objecting" in few


def test_the_sentences_never_use_a_banned_word():
    text = json.dumps(RULES).lower()
    for w in ("guardian", "gate", "proof", "receipt", "evidence", "ledger", "witness", "canary", "trust", "earned", "calibrated",
              "autopilot", "sentinel", "verdict", "risk score"):
        assert w not in text, w


def test_the_placement_is_the_same_for_every_band():
    assert "Whatever the band" in RULES["placement"] and "No band moves it" in RULES["placement"]
    rows = (ROOT / "README.md").read_text().split("\n")
    assert sum(r.startswith((P.NOT_READ, "- **The forward test, read on ")) for r in rows) == 1


def _audit():
    import importlib.util
    spec = importlib.util.spec_from_file_location("hardcode_audit", ROOT / "tools" / "hardcode_audit.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


@pytest.mark.parametrize("kw", [dict(merged=3, closed=2), dict(k=0), dict(k=2, ku=1), dict(), dict(k=3, n=10, ku=12, nu=40)])
def test_the_readme_line_cites_every_number(tmp_path, kw):
    s = _summary(**kw)
    band = P.sentence(s, "2026-10-25", RULES)[0]
    v = P.values(s, "2026-10-25")
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / P.READ.name).write_text(json.dumps({"counts": v}))
    line = P.readme_line(RULES, band, v)
    (tmp_path / "README.md").write_text(f"# x\n\n{line}\n")
    assert _audit().check_numbers(tmp_path) == []
    assert line.startswith("- **The forward test, read on 2026-10-25.** ")
    import re
    assert re.sub(r"\s*<!--.*?-->", "", line).endswith(P.sentence(s, "2026-10-25", RULES)[1])


def test_the_read_replaces_only_the_not_read_line():
    readme = f"a\n{P.NOT_READ} old words\nb\n"
    assert P.with_read(readme, "- new") == "a\n- new\nb\n"
    quoted = f"see '{P.NOT_READ}' below\n{readme}"
    assert P.with_read(quoted, "- new") == f"see '{P.NOT_READ}' below\na\n- new\nb\n"           # only a line that starts with it
    for bad in ("a\nb\n", f"{P.NOT_READ} x\n{P.NOT_READ} y\n"):
        with pytest.raises(ValueError):
            P.with_read(bad, "- new")
    assert P.with_read((ROOT / "README.md").read_text(), "- new").count("- new") == 1


def test_a_changed_sentence_file_cannot_be_read_out(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "SENTENCES", tmp_path / "s.json")
    monkeypatch.setattr(P, "SENTENCES_SEAL", tmp_path / "seal.json")
    P.SENTENCES.write_text('{"a": 1}\n')
    P.seal_sentences()
    import hashlib
    h = hashlib.sha256(P.SENTENCES.read_bytes()).hexdigest()
    assert P.frozen_on(h) == json.loads(P.SENTENCES_SEAL.read_text())["summary"]["frozen_on"]
    with pytest.raises(ValueError):
        P.frozen_on(hashlib.sha256(b'{"a": 2}\n').hexdigest())


def test_the_committed_sentences_match_their_seal():
    import hashlib
    assert P.frozen_on(hashlib.sha256(P.SENTENCES.read_bytes()).hexdigest()) == "2026-10-21"
