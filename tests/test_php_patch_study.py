import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "eval"))
import php_patch_study as S  # noqa: E402


def row(moved, left, state="read"):
    return {"pr": "https://github.com/o/r/pull/1", "state": state, "moved": moved, "left": left, "floating": 0}


def test_only_php_moves_count():
    r = S.php_only(row([{"path": "Dockerfile", "family": "node", "to": "22"}], []))
    assert r["state"] == "no_move" and "moved" not in r and "left" not in r


def test_only_php_copies_are_kept():
    left = [{"path": "ci.yml", "family": "php", "version": "8.3.35"}, {"path": "ci.yml", "family": "node", "version": "20"}]
    r = S.php_only(row([{"path": "Dockerfile", "family": "php", "to": "8.3.36"}], left))
    assert r["state"] == "read" and [c["family"] for c in r["left"]] == ["php"]


def test_unread_rows_pass_through():
    r = {"pr": "x", "state": "unreadable", "why": "files: HTTP 404"}
    assert S.php_only(r) is r


def test_search_item_fields():
    item = {"number": 7, "title": "Bump PHP to 8.3.36", "body": None, "html_url": "https://github.com/o/r/pull/7",
            "repository_url": "https://api.github.com/repos/o/r", "user": {"login": "renovate[bot]", "type": "Bot"},
            "pull_request": {"merged_at": "2026-10-22T01:00:00Z"}}
    pr = S.as_pr(item)
    assert pr["agent"] == "renovate[bot]" and pr["author_type"] == "Bot" and pr["merged_at"] == "2026-10-22T01:00:00Z"
    assert pr["repo_url"].split("/repos/", 1)[1] == "o/r"


class FakeGh:
    def __init__(self, routes):
        self.routes = routes

    def get(self, path, raw=False):
        return self.routes.get(path, (404, None))


def test_named_reads_review_and_conversation_comments():
    prs = {"https://github.com/o/r/pull/1": {"repo_url": "https://api.github.com/repos/o/r", "number": 1}}
    rows = [row([{"family": "php"}], [{"path": "docker/staging/Dockerfile"}, {"path": "compose.yml"}])]
    gh = FakeGh({"/repos/o/r/pulls/1/comments?per_page=100": (200, [{"body": "looks fine", "path": "compose.yml"}]),
                 "/repos/o/r/issues/1/comments?per_page=100": (200, [{"body": "staging still uses an old Dockerfile"}])})
    S.named(gh, rows, prs)
    assert [c["named"] for c in rows[0]["left"]] == [True, True]


def test_not_named_when_no_comment_mentions_the_file():
    prs = {"https://github.com/o/r/pull/1": {"repo_url": "https://api.github.com/repos/o/r", "number": 1}}
    rows = [row([{"family": "php"}], [{"path": ".github/workflows/ci.yml"}])]
    S.named(FakeGh({"/repos/o/r/issues/1/comments?per_page=100": (200, [{"body": "lgtm"}])}), rows, prs)
    assert rows[0]["left"][0]["named"] is False


def test_fewer_than_30_read_moves_are_listed_not_shared():
    rows = [row([{"family": "php"}], [{"path": "a", "family": "php"}]) | {"merged": False, "author_type": "User"}] * 3
    s = S.summarise(rows, 3)
    assert s["list_instead_of_share"] is True and s["left_behind"]["prs"] == 3
    assert s["left_behind"]["by_author_type"] == {"User": 3}
    rows = [row([{"family": "php"}], []) | {"merged": False}] * 30
    assert S.summarise(rows, 30)["list_instead_of_share"] is False
