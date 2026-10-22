import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import repeat_objections as RO  # noqa: E402


def c(i, pr, path, repo="o/r"):
    return {"comment_id": i, "pull_request_url": f"https://api.github.com/repos/{repo}/pulls/{pr}", "path": path}


def test_a_path_counts_when_objected_to_in_two_pull_requests_of_one_repo():
    got = RO.build([c("1", 1, "a"), c("2", 2, "a"), c("3", 2, "a"), c("4", 3, "b"), c("5", 4, "a", repo="x/y")])
    assert got["objections"] == 5 and got["pairs_in_two_or_more"] == 1 and got["repeat_objections"] == 1
    assert got["pairs"][0]["repo"] == "o/r" and got["pairs"][0]["path"] == "a"
    assert [p["comments"] for p in got["pairs"][0]["pull_requests"]] == [["1"], ["2", "3"]]


def test_three_pull_requests_make_two_repeats_and_named_is_carried():
    got = RO.build([c("1", 1, "a"), c("2", 2, "a"), c("3", 3, "a")], {"2": {"itemator": True}})
    assert got["repeat_objections"] == 2 and round(got["share"], 2) == 0.67
    assert [p["named"] for p in got["pairs"][0]["pull_requests"]] == [[None], [{"itemator": True}], [None]]


def test_nothing_repeated_is_zero():
    got = RO.build([c("1", 1, "a"), c("2", 1, "a")])
    assert got["pairs_in_two_or_more"] == 0 and got["repeat_objections"] == 0 and got["pairs"] == []
