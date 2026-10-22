"""The repeat-question study's counting (eval/aidev_repeats.py, eval/aidev_repeats_rubric.json)."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import aidev_repeats as S  # noqa: E402


def pr(i, repo, when, qs, agent="Copilot"):
    return {"id": i, "repo": repo, "created_at": when, "agent": agent, "questions": qs}


def test_a_later_question_on_the_same_path_in_the_same_repo_repeats():
    s = S.tally([pr(2, "a/b", "2025-02", [["ci_change", ".gitlab-ci.yml"]]), pr(1, "a/b", "2025-01", [["ci_change", ".gitlab-ci.yml"]])])
    assert (s["questions"], s["repeats"], s["cards_not_posted"]) == (2, 1, 1)


def test_order_is_by_created_at_not_by_list_order_or_id():
    s = S.tally([pr(1, "a/b", "2025-03", [["dep", "x"], ["dep", "y"]]), pr(2, "a/b", "2025-01", [["dep", "x"]])])
    assert s["repeats"] == 1 and s["cards_not_posted"] == 0          # the later PR (id 1) repeats x but not y


def test_other_repositories_and_the_same_pull_request_never_count():
    s = S.tally([pr(1, "a/b", "2025-01", [["dep", "x"], ["dep", "x"]]), pr(2, "c/d", "2025-02", [["dep", "x"]])])
    assert s["repeats"] == 0 and s["repeats_by_kind"] == 0
    assert s["repositories_asked_twice_or_more"] == 0


def test_kind_count_is_looser_than_path_count():
    s = S.tally([pr(1, "a/b", "2025-01", [["dep", "x"]]), pr(2, "a/b", "2025-02", [["dep", "y"]])])
    assert (s["repeats"], s["repeats_by_kind"], s["repositories_asked_twice_or_more"]) == (0, 1, 1)


def test_pull_requests_without_questions_do_not_count_as_asked():
    s = S.tally([pr(1, "a/b", "2025-01", []), pr(2, "a/b", "2025-02", [["dep", "x"]])])
    assert s["questions"] == 1 and s["pull_requests_with_questions"] == 1 and s["repositories_asked_twice_or_more"] == 0


def test_the_sentence_is_picked_by_the_registered_threshold():
    rubric = json.loads((ROOT / "eval" / "aidev_repeats_rubric.json").read_text())
    low = {"repeats": 1, "questions": 100, "share": 0.01}
    high = {"repeats": 30, "questions": 100, "share": 0.3}
    assert S.sentence(low, rubric).startswith("On public agent pull requests, almost no question")
    assert "30 of 100 questions (30%)" in S.sentence(high, rubric)


def test_shards_cover_every_id_once():
    ids = list(range(10))
    parts = [S.shard_ids(ids, f"{i}/4") for i in range(4)]
    assert sorted(x for p in parts for x in p) == ids
    assert S.shard_ids(ids, None) == ids


def test_a_repository_split_across_shards_tallies_as_one_run():
    rows = [pr(1, "a/b", "2025-01", [["dep", "x"]]), pr(2, "a/b", "2025-02", [["dep", "x"]]), pr(3, "c/d", "2025-01", [["dep", "z"]])]
    parts = [{"table_rows": 9, "with_file_rows": 2, "unreadable": 1, "rows": rows[:1]},
             {"table_rows": 9, "with_file_rows": 2, "unreadable": 0, "rows": rows[1:]}]
    joined, counts, table = S.merge(parts)
    assert S.tally(joined) == S.tally(rows) and S.tally(joined)["repeats"] == 1
    assert counts == {"with_file_rows": 4, "unreadable": 1} and table == 9
